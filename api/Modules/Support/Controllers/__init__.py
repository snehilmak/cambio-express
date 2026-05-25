"""Support module — Controllers (FastAPI router).

User-facing:
  POST /tickets          — submit a new ticket
  GET  /tickets          — list my tickets (scoped to store)
  GET  /tickets/{id}     — ticket detail

Superadmin:
  GET  /tickets/all      — every ticket across all stores
  PUT  /tickets/{id}     — update status / priority / reply
"""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Auth.Controllers import get_principal
from api.Modules.Auth.Services import resolve_store_scope
from api.Modules.Support.Models import SupportTicket
from api.Modules.Support.Requests import (
    CreateTicketRequest,
    TICKET_CATEGORIES,
    TICKET_PRIORITIES,
    TICKET_STATUSES,
    TicketListResponse,
    TicketResponse,
    TicketRow,
    UpdateTicketRequest,
)

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
        return list_all_tickets(status=status, db=db, claims=claims)
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
            ticket.closed_at = datetime.utcnow()
        else:
            ticket.closed_at = None
    if body.priority is not None:
        if body.priority not in TICKET_PRIORITIES:
            raise HTTPException(422, f"Invalid priority: {body.priority}")
        ticket.priority = body.priority
    if body.admin_reply is not None:
        ticket.admin_reply = body.admin_reply.strip()[:5000]
        ticket.replied_at = datetime.utcnow()
        ticket.replied_by = (
            claims.get("name") or claims.get("username") or ""
        )
    ticket.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(ticket)
    return TicketResponse(ticket=_to_row(ticket))
