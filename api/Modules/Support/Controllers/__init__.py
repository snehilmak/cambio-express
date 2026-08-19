"""Support module — Controllers (FastAPI router).

User-facing:
  POST /tickets                — submit a new ticket
  GET  /tickets                — list my tickets (scoped to store)
  GET  /tickets/{id}           — ticket detail
  GET  /tickets/{id}/messages  — the conversation thread
  POST /tickets/{id}/messages  — reply into the thread
  POST /tickets/{id}/reopen    — reopen a closed ticket

Superadmin:
  GET  /tickets/all      — every ticket across all stores
  PUT  /tickets/{id}     — update status / priority / reply

Thread rules (see the ticket-status lifecycle):
  - Replies are allowed while the ticket is open / in_progress /
    resolved. A CLOSED ticket returns 409 — the store side gets a
    "Reopen" action instead.
  - A store-side reply to a RESOLVED ticket auto-reopens it to
    "open" (replying means it wasn't actually resolved).
"""
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Auth.Controllers import get_principal
from api.Modules.Auth.Services import resolve_store_scope
from api.Modules.Support.Models import SupportMessage, SupportTicket
from api.Modules.Support.Requests import (
    CreateMessageRequest,
    CreateTicketRequest,
    MessageListResponse,
    MessageRow,
    TICKET_CATEGORIES,
    TICKET_PRIORITIES,
    TICKET_STATUSES,
    TicketListResponse,
    TicketResponse,
    TicketRow,
    UpdateTicketRequest,
)
from api.Core.Clock import utc_now

router = APIRouter()


def _to_row(t: SupportTicket, store_name: str | None = None) -> TicketRow:
    return TicketRow(
        id=t.id,
        store_id=t.store_id,
        user_id=t.user_id,
        submitted_by=t.submitted_by or "",
        category=t.category or "question",
        priority=t.priority,
        subject=t.subject or "",
        body=t.body or "",
        status=t.status or "open",
        admin_reply=t.admin_reply,
        replied_at=t.replied_at.isoformat() if t.replied_at else None,
        replied_by=t.replied_by,
        created_at=t.created_at.isoformat() if t.created_at else "",
        updated_at=t.updated_at.isoformat() if t.updated_at else "",
        closed_at=t.closed_at.isoformat() if t.closed_at else None,
        store_name=store_name,
    )


# ── User-facing ──────────────────────────────────────────────


@router.post("", response_model=TicketResponse, status_code=201)
def create_ticket(
    body: CreateTicketRequest = Body(...),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> TicketResponse:
    """Submit a new support ticket."""
    sid = resolve_store_scope(claims)
    if body.category not in TICKET_CATEGORIES:
        raise HTTPException(422, f"Invalid category: {body.category}")
    ticket = SupportTicket(
        store_id=sid,
        user_id=int(claims["sub"]),
        submitted_by=claims.get("name") or claims.get("username") or "",
        category=body.category,
        subject=body.subject.strip()[:200],
        body=body.body.strip()[:5000],
        status="open",
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return TicketResponse(ticket=_to_row(ticket))


@router.get("", response_model=TicketListResponse)
def list_my_tickets(
    status: str | None = Query(None),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> TicketListResponse:
    """List tickets submitted by users in the caller's store.
    Superadmin sees all tickets (same as /all) since they have no store."""
    if claims.get("role") == "superadmin":
        return list_all_tickets(status=status, category=None, db=db, claims=claims)
    sid = resolve_store_scope(claims)
    q = db.query(SupportTicket).filter(
        SupportTicket.store_id == sid,
    )
    if status:
        q = q.filter(SupportTicket.status == status)
    q = q.order_by(SupportTicket.created_at.desc())
    rows = q.all()
    return TicketListResponse(
        tickets=[_to_row(t) for t in rows],
        total=len(rows),
    )


@router.get("/all", response_model=TicketListResponse)
def list_all_tickets(
    status: str | None = Query(None),
    category: str | None = Query(None),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> TicketListResponse:
    """Superadmin: list every ticket across all stores."""
    if claims.get("role") != "superadmin":
        raise HTTPException(403, "Superadmin only")
    q = db.query(SupportTicket)
    if status:
        q = q.filter(SupportTicket.status == status)
    if category:
        q = q.filter(SupportTicket.category == category)
    q = q.order_by(SupportTicket.created_at.desc())
    rows = q.all()
    # Batch-fetch store names for the admin view
    store_ids = {t.store_id for t in rows}
    store_names: dict[int, str] = {}
    if store_ids:
        from api.Modules.Tenancy.Models import Store
        stores = db.query(Store.id, Store.name).filter(
            Store.id.in_(store_ids),
        ).all()
        store_names = {s.id: s.name or "" for s in stores}
    return TicketListResponse(
        tickets=[_to_row(t, store_names.get(t.store_id)) for t in rows],
        total=len(rows),
    )


@router.get("/{ticket_id}", response_model=TicketResponse)
def get_ticket(
    ticket_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> TicketResponse:
    """View a single ticket. Scoped: user sees own store's
    tickets; superadmin sees any."""
    ticket = db.get(SupportTicket, ticket_id)
    if ticket is None:
        raise HTTPException(404, "Ticket not found")
    if claims.get("role") != "superadmin":
        sid = resolve_store_scope(claims)
        if ticket.store_id != sid:
            raise HTTPException(404, "Ticket not found")
    return TicketResponse(ticket=_to_row(ticket))


# ── Conversation thread ──────────────────────────────────────


def _message_row(m: SupportMessage) -> MessageRow:
    return MessageRow(
        id=m.id,
        ticket_id=m.ticket_id,
        author_name=m.author_name or "",
        author_kind=m.author_kind or "user",
        body=m.body or "",
        created_at=m.created_at.isoformat() if m.created_at else "",
    )


def _load_scoped_ticket(
    db: Session, claims: dict[str, Any], ticket_id: int,
) -> SupportTicket:
    """Ticket by id, with the same opaque-404 tenancy scoping as
    ``get_ticket``: store principals only reach their own store's
    tickets; superadmin reaches any."""
    ticket = db.get(SupportTicket, ticket_id)
    if ticket is None:
        raise HTTPException(404, "Ticket not found")
    if claims.get("role") != "superadmin":
        sid = resolve_store_scope(claims)
        if ticket.store_id != sid:
            raise HTTPException(404, "Ticket not found")
    return ticket


def _audit_ticket_action(
    db: Session, claims: dict[str, Any], ticket: SupportTicket,
    *, action: str, summary: str,
) -> None:
    """Audit a ticket mutation into the right sink for the caller
    (invariant #7): superadmin → superadmin log, store principal →
    that store's operator log."""
    if claims.get("role") == "superadmin":
        from api.Core.Audit import audit_superadmin
        from api.Modules.Tenancy.Models import User
        sa_user = db.get(User, int(claims["sub"]))
        if sa_user is not None:
            audit_superadmin(
                db, sa_user, action=action,
                target_type="support_ticket", target_id=str(ticket.id),
                details=f"{summary} store_id={ticket.store_id}",
            )
    else:
        from api.Core.Audit import audit_operator
        audit_operator(
            db, claims, action=action,
            target_type="support_ticket", target_id=str(ticket.id),
            target_label=(ticket.subject or "")[:160],
            summary=summary, store_id=ticket.store_id,
        )


@router.get("/{ticket_id}/messages", response_model=MessageListResponse)
def list_ticket_messages(
    ticket_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> MessageListResponse:
    """The ticket's conversation thread, oldest first. Same scoping
    as the ticket detail."""
    ticket = _load_scoped_ticket(db, claims, ticket_id)
    rows = (
        db.query(SupportMessage)
          .filter(SupportMessage.ticket_id == ticket.id)
          .order_by(SupportMessage.created_at.asc(), SupportMessage.id.asc())
          .all()
    )
    return MessageListResponse(
        messages=[_message_row(m) for m in rows],
        total=len(rows),
    )


@router.post(
    "/{ticket_id}/messages",
    response_model=TicketResponse, status_code=201,
)
def create_ticket_message(
    ticket_id: int = Path(..., ge=1),
    body: CreateMessageRequest = Body(...),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> TicketResponse:
    """Reply into the thread. Any principal in the ticket's store
    (or superadmin). Closed tickets are read-only — 409, the UI
    offers Reopen instead. A store-side reply to a resolved ticket
    auto-reopens it (replying means it wasn't resolved). Returns the
    ticket so the client sees any status flip without a second
    fetch."""
    ticket = _load_scoped_ticket(db, claims, ticket_id)
    if (ticket.status or "open") == "closed":
        raise HTTPException(
            409, "Ticket is closed — reopen it to continue the conversation.",
        )
    is_staff = claims.get("role") == "superadmin"
    author_name = claims.get("name") or claims.get("username") or ""
    text = body.body.strip()[:5000]
    if not text:
        raise HTTPException(422, "Message cannot be empty.")
    msg = SupportMessage(
        ticket_id=ticket.id,
        store_id=ticket.store_id,
        author_user_id=int(claims["sub"]),
        author_name=author_name,
        author_kind="staff" if is_staff else "user",
        body=text,
        created_at=utc_now(),
    )
    db.add(msg)
    reopened = False
    if not is_staff and (ticket.status or "") == "resolved":
        # The user is telling us it isn't actually resolved.
        ticket.status = "open"
        ticket.closed_at = None
        reopened = True
    if is_staff:
        # Dual-write the legacy single-reply column so anything still
        # reading it (older clients, exports) sees the latest staff
        # reply. The thread is the source of truth.
        ticket.admin_reply = text
        ticket.replied_at = utc_now()
        ticket.replied_by = author_name
    ticket.updated_at = utc_now()
    _audit_ticket_action(
        db, claims, ticket,
        action="reply_support_ticket",
        summary=(
            f"reply ({'staff' if is_staff else 'user'})"
            + (" auto-reopened" if reopened else "")
        ),
    )
    db.commit()
    db.refresh(ticket)
    return TicketResponse(ticket=_to_row(ticket))


@router.post("/{ticket_id}/reopen", response_model=TicketResponse)
def reopen_ticket(
    ticket_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> TicketResponse:
    """Reopen a CLOSED ticket (the store side's one action on a
    closed ticket — e.g. the issue came back). Open/in-progress/
    resolved tickets don't need this: 409."""
    ticket = _load_scoped_ticket(db, claims, ticket_id)
    if (ticket.status or "open") != "closed":
        raise HTTPException(409, "Ticket is not closed.")
    ticket.status = "open"
    ticket.closed_at = None
    ticket.updated_at = utc_now()
    _audit_ticket_action(
        db, claims, ticket,
        action="reopen_support_ticket", summary="reopened",
    )
    db.commit()
    db.refresh(ticket)
    return TicketResponse(ticket=_to_row(ticket))


@router.put("/{ticket_id}", response_model=TicketResponse)
def update_ticket(
    ticket_id: int = Path(..., ge=1),
    body: UpdateTicketRequest = Body(...),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> TicketResponse:
    """Update a ticket's status, priority, or admin reply.
    Admin role required (store admin for own store, superadmin
    for any)."""
    role = claims.get("role", "")
    if role not in ("admin", "owner", "superadmin"):
        raise HTTPException(403, "Admin role required")
    ticket = db.get(SupportTicket, ticket_id)
    if ticket is None:
        raise HTTPException(404, "Ticket not found")
    if role != "superadmin":
        sid = resolve_store_scope(claims)
        if ticket.store_id != sid:
            raise HTTPException(404, "Ticket not found")
    if body.status is not None:
        if body.status not in TICKET_STATUSES:
            raise HTTPException(422, f"Invalid status: {body.status}")
        ticket.status = body.status
        if body.status in ("resolved", "closed"):
            ticket.closed_at = utc_now()
        else:
            ticket.closed_at = None
    if body.priority is not None:
        if body.priority not in TICKET_PRIORITIES:
            raise HTTPException(422, f"Invalid priority: {body.priority}")
        ticket.priority = body.priority
    if body.admin_reply is not None:
        reply_text = body.admin_reply.strip()[:5000]
        replier = claims.get("name") or claims.get("username") or ""
        ticket.admin_reply = reply_text
        ticket.replied_at = utc_now()
        ticket.replied_by = replier
        # The thread is the source of truth — a legacy single-reply
        # write also lands there as a staff message (only when it
        # actually says something; clearing the field appends nothing).
        if reply_text:
            db.add(SupportMessage(
                ticket_id=ticket.id,
                store_id=ticket.store_id,
                author_user_id=int(claims["sub"]),
                author_name=replier,
                author_kind="staff" if role == "superadmin" else "user",
                body=reply_text,
                created_at=utc_now(),
            ))
    ticket.updated_at = utc_now()
    # CLAUDE.md invariant #7 — every admin/superadmin mutation records
    # an audit row. Superadmin edits any store's ticket and carries no
    # store_id claim, so it lands in the superadmin log; a store admin
    # lands in that store's operator log (store_id pinned to the
    # ticket, which the guard above already proved matches the claim).
    _summary = (
        f"status={ticket.status} priority={ticket.priority} "
        f"reply={'yes' if body.admin_reply is not None else 'no'}"
    )
    if role == "superadmin":
        from api.Core.Audit import audit_superadmin
        from api.Modules.Tenancy.Models import User
        sa_user = db.get(User, int(claims["sub"]))
        if sa_user is not None:
            audit_superadmin(
                db, sa_user, action="update_support_ticket",
                target_type="support_ticket", target_id=str(ticket.id),
                details=f"{_summary} store_id={ticket.store_id}",
            )
    else:
        from api.Core.Audit import audit_operator
        audit_operator(
            db, claims, action="update_support_ticket",
            target_type="support_ticket", target_id=str(ticket.id),
            target_label=(ticket.subject or "")[:160],
            summary=_summary, store_id=ticket.store_id,
        )
    db.commit()
    db.refresh(ticket)
    return TicketResponse(ticket=_to_row(ticket))
