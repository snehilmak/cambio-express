"""Transfers module — Controllers (FastAPI router).

Mounts at `/api/v2/transfers/*` (the parent router in `api/main.py`
adds `/transfers`; the FastAPI app's `root_path="/api/v2"` carries
the version prefix).

PR 12 ships the read-side only:

  GET /transfers → paginated list with the same filter shape as the
                   legacy /transfers route's query string.

PR 13 will flip the legacy /transfers route to call the same Service
this Controller does. PR 14+ will add the write-side
(POST /transfers, PUT /transfers/{id}) once the create/edit business
logic moves into Services.

Auth gating intentionally NOT here yet — auth migration is module 5
of 6 in the ADR.

Layer rules:
    Controller → Service     ✓
    Controller → Repository  ✗
    Controller → DB session  ✓ (only via Depends(get_db))
"""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Auth.Controllers import get_principal
from api.Modules.Transfers.Repositories import (
    TransferFilters,
    get_by_id_in_stores,
)
from api.Modules.Transfers.Requests import (
    CreateTransferRequest,
    EmployeeRow,
    ReceiptStore,
    ReceiptTransfer,
    RosterResponse,
    TransferListResponse,
    TransferReceiptResponse,
    TransferResponse,
    TransferRow,
)
from api.Modules.Transfers.Services import (
    CreateTransferInput,
    TransferNotFoundError,
    active_roster,
    create_transfer,
    delete_transfer,
    list_transfers,
    normalize_service_type,
    parse_dob,
    update_transfer,
)


router = APIRouter()


def _parse_store_ids(store_ids: str) -> list[int]:
    """Comma-separated → list[int] parser. Multi-store admin /
    owner views pass several IDs in a single query param;
    matches the Reports controllers' shape so the parsing stays
    consistent across the API."""
    try:
        ids = [int(s.strip()) for s in store_ids.split(",") if s.strip()]
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail=f"store_ids must be comma-separated integers: {e}",
        )
    if not ids:
        raise HTTPException(
            status_code=422, detail="store_ids must include at least one ID",
        )
    return ids


def _to_row(t) -> TransferRow:
    return TransferRow(
        id=t.id,
        send_date=t.send_date.isoformat() if t.send_date else "",
        company=t.company or "",
        service_type=t.service_type or "Money Transfer",
        sender_name=t.sender_name or "",
        recipient_name=t.recipient_name or "",
        country=t.country or "",
        confirm_number=t.confirm_number or "",
        send_amount=float(t.send_amount or 0),
        fee=float(t.fee or 0),
        federal_tax=float(t.federal_tax or 0),
        total_collected=float(t.total_collected),
        status=t.status or "Sent",
        batch_id=t.batch_id or "",
        employee_name=t.employee_name or "",
    )


@router.get("/employees", response_model=RosterResponse)
def employees_route(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> RosterResponse:
    """Active store-employee roster for the JWT principal's store.
    Powers the "Processed by" dropdown on the SPA's create + edit
    transfer forms. Inactive employees are filtered out so cashiers
    can't credit new transfers to former employees.

    Returns 403 when the JWT has no store scope (superadmin) — the
    roster is store-specific.
    """
    store_id = claims.get("store_id")
    if store_id is None:
        raise HTTPException(
            status_code=403,
            detail=(
                "JWT does not carry a store scope. Sign in as a store "
                "admin or owner to load the roster."
            ),
        )
    rows = active_roster(db, int(store_id))
    return RosterResponse(
        employees=[EmployeeRow(id=r.id, name=r.name or "") for r in rows],
    )


@router.get("", response_model=TransferListResponse)
def list_route(
    store_ids: str = Query(
        ...,
        description=(
            "Comma-separated store IDs, e.g. `1,2`. Single-store "
            "admins pass one; multi-store owners pass every store "
            "in their umbrella."
        ),
    ),
    company: str = Query(""),
    status: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
    sender: str = Query(""),
    recipient: str = Query(""),
    country: str = Query(""),
    confirm: str = Query(""),
    batch: str = Query(""),
    q: str = Query("", description="Global search across sender/recipient/confirm/country/batch."),
    sort: str = Query("", description="Column slug to sort by; empty falls back to send_date desc."),
    dir: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> TransferListResponse:
    ids = _parse_store_ids(store_ids)
    filters = TransferFilters.from_query({
        "company": company, "status": status,
        "date_from": date_from, "date_to": date_to,
        "sender": sender, "recipient": recipient,
        "country": country, "confirm": confirm, "batch": batch,
        "q": q, "sort": sort, "dir": dir,
    })
    page_obj = list_transfers(
        db, ids, filters, page=page, per_page=per_page,
    )
    return TransferListResponse(
        rows=[_to_row(r) for r in page_obj.rows],
        total=page_obj.total,
        page=page_obj.page,
        per_page=page_obj.per_page,
        total_pages=page_obj.total_pages,
        page_amount=page_obj.page_amount,
    )


@router.post("", response_model=TransferResponse, status_code=201)
def create_route(
    body: CreateTransferRequest,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> TransferResponse:
    """Create a transfer in the JWT principal's store. Server
    recomputes federal_tax server-side from
    `(send_amount, service_type, country, store)` so the client
    can't lie about the rate. Audited in the same transaction
    via `record_transfer_audit`.
    """
    store_id_claim = claims.get("store_id")
    if store_id_claim is None:
        raise HTTPException(
            status_code=403,
            detail=(
                "JWT does not carry a store scope. Sign in as a "
                "store admin or owner to create transfers."
            ),
        )
    user_id = int(claims["sub"])

    try:
        send_date = datetime.strptime(body.send_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=422, detail="send_date must be YYYY-MM-DD",
        )
    sender_dob = parse_dob(body.sender_dob)

    payload = CreateTransferInput(
        store_id=int(store_id_claim),
        created_by_user_id=user_id,
        send_date=send_date,
        company=body.company,
        # Always pass through the same normalize_service_type the
        # legacy form uses — anything unrecognized falls back to
        # "Money Transfer" and the tax math runs on that.
        service_type=normalize_service_type(body.service_type),
        sender_name=body.sender_name,
        send_amount=float(body.send_amount or 0),
        fee=float(body.fee or 0),
        commission=float(body.commission or 0),
        recipient_name=body.recipient_name,
        country=body.country,
        recipient_phone=body.recipient_phone,
        sender_phone=body.sender_phone,
        sender_phone_country=body.sender_phone_country or "+1",
        sender_address=body.sender_address,
        sender_dob=sender_dob,
        confirm_number=body.confirm_number,
        status=body.status or "Sent",
        status_notes=body.status_notes,
        batch_id=body.batch_id,
        internal_notes=body.internal_notes,
        employee_id=body.employee_id,
        customer_id=body.customer_id,
    )
    try:
        transfer = create_transfer(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    return TransferResponse(transfer=_to_row(transfer))


@router.get(
    "/{transfer_id}/receipt",
    response_model=TransferReceiptResponse,
)
def get_receipt_route(
    transfer_id: int = Path(..., ge=1),
    store_ids: str = Query(
        ...,
        description=(
            "Caller's store scope, comma-separated. Cross-tenant "
            "lookups 404."
        ),
    ),
    db: Session = Depends(get_db),
) -> TransferReceiptResponse:
    """Printable-receipt payload — transfer fields + the store's
    branding metadata (logo URL, footer copy, tax ID) merged into
    one response so the SPA's ``/app/transfers/{id}/receipt``
    route doesn't have to chain two fetches.

    Tenancy: ``store_ids`` is the caller's owner umbrella (comma
    separated). The transfer must live inside one of those
    stores. Returns 404 (never 403) to keep store boundaries
    opaque.
    """
    from api.Modules.Tenancy.Models import Store
    ids = _parse_store_ids(store_ids)
    transfer = get_by_id_in_stores(db, transfer_id, ids)
    if transfer is None:
        raise HTTPException(status_code=404, detail="Transfer not found")
    store = db.get(Store, transfer.store_id)
    if store is None:
        # The transfer's FK target vanished — exceedingly rare but
        # 404 is still the right answer ("can't render the receipt").
        raise HTTPException(status_code=404, detail="Store not found")
    return TransferReceiptResponse(
        store=ReceiptStore(
            name=store.name or "",
            address=store.address or "",
            phone=store.phone or "",
            email=store.email or "",
            receipt_logo_url=store.receipt_logo_url or "",
            receipt_footer=store.receipt_footer or "",
            receipt_tax_id=store.receipt_tax_id or "",
            legal_name=store.legal_name or "",
            ein=store.ein or "",
            legal_address=store.legal_address or "",
        ),
        transfer=ReceiptTransfer(
            id=transfer.id,
            send_date=(
                transfer.send_date.isoformat() if transfer.send_date else ""
            ),
            created_at=(
                transfer.created_at.isoformat() if transfer.created_at else ""
            ),
            company=transfer.company or "",
            service_type=transfer.service_type or "Money Transfer",
            sender_name=transfer.sender_name or "",
            sender_phone=transfer.sender_phone or "",
            sender_phone_country=transfer.sender_phone_country or "",
            sender_address=transfer.sender_address or "",
            recipient_name=transfer.recipient_name or "",
            recipient_phone=transfer.recipient_phone or "",
            country=transfer.country or "",
            confirm_number=transfer.confirm_number or "",
            send_amount=float(transfer.send_amount or 0),
            fee=float(transfer.fee or 0),
            federal_tax=float(transfer.federal_tax or 0),
            total_collected=float(transfer.total_collected),
            status=transfer.status or "Sent",
            employee_name=transfer.employee_name or "",
        ),
    )


@router.get("/{transfer_id}", response_model=TransferResponse)
def get_route(
    transfer_id: int = Path(..., ge=1),
    store_ids: str = Query(
        ...,
        description=(
            "Caller's store scope, comma-separated. Cross-tenant "
            "lookups return 404 (never 403 — keeps tenancy "
            "boundaries opaque)."
        ),
    ),
    db: Session = Depends(get_db),
) -> TransferResponse:
    ids = _parse_store_ids(store_ids)
    transfer = get_by_id_in_stores(db, transfer_id, ids)
    if transfer is None:
        raise HTTPException(status_code=404, detail="Transfer not found")
    return TransferResponse(transfer=_to_row(transfer))


@router.put("/{transfer_id}", response_model=TransferResponse)
def update_route(
    transfer_id: int = Path(..., ge=1),
    body: CreateTransferRequest = ...,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> TransferResponse:
    """Update an existing transfer in the JWT principal's store.
    Same body shape as POST /transfers — every field is replaceable
    (no PATCH semantics). Server recomputes federal_tax just like
    create. Audit log captures the diff via summarize_transfer_changes.
    Cross-tenant updates return 404 to keep tenancy opaque.
    """
    store_id_claim = claims.get("store_id")
    if store_id_claim is None:
        raise HTTPException(
            status_code=403,
            detail=(
                "JWT does not carry a store scope. Sign in as a "
                "store admin or owner to edit transfers."
            ),
        )
    user_id = int(claims["sub"])

    try:
        send_date = datetime.strptime(body.send_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=422, detail="send_date must be YYYY-MM-DD",
        )
    sender_dob = parse_dob(body.sender_dob)

    payload = CreateTransferInput(
        store_id=int(store_id_claim),
        created_by_user_id=user_id,
        send_date=send_date,
        company=body.company,
        service_type=normalize_service_type(body.service_type),
        sender_name=body.sender_name,
        send_amount=float(body.send_amount or 0),
        fee=float(body.fee or 0),
        commission=float(body.commission or 0),
        recipient_name=body.recipient_name,
        country=body.country,
        recipient_phone=body.recipient_phone,
        sender_phone=body.sender_phone,
        sender_phone_country=body.sender_phone_country or "+1",
        sender_address=body.sender_address,
        sender_dob=sender_dob,
        confirm_number=body.confirm_number,
        status=body.status or "Sent",
        status_notes=body.status_notes,
        batch_id=body.batch_id,
        internal_notes=body.internal_notes,
        employee_id=body.employee_id,
        customer_id=body.customer_id,
    )
    try:
        transfer = update_transfer(
            db,
            transfer_id=transfer_id,
            store_id=int(store_id_claim),
            payload=payload,
        )
    except TransferNotFoundError:
        raise HTTPException(status_code=404, detail="Transfer not found")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    return TransferResponse(transfer=_to_row(transfer))


@router.delete("/{transfer_id}", status_code=204)
def delete_transfer_route(
    transfer_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> None:
    """Hard-delete a transfer + cascade its TransferAudit history.

    Mirrors the legacy /transfers/<tid>/delete POST: admin role +
    store scope required, cross-store IDs return 404 (opaque
    tenancy), and an OperatorAuditLog row gets appended on the way
    out so the activity log keeps the same trail it had before
    the SPA cutover (PR #404). Audit fields mirror the legacy
    label / summary format ("sender → recipient — $amount" /
    "confirm=… company=… status=…").
    """
    if claims.get("role") not in ("admin", "owner", "superadmin"):
        raise HTTPException(
            status_code=403,
            detail="Only store admins can delete transfers.",
        )
    sid = claims.get("store_id")
    if sid is None:
        raise HTTPException(
            status_code=403,
            detail="JWT does not carry a store scope.",
        )
    try:
        transfer = delete_transfer(db, transfer_id, int(sid))
    except TransferNotFoundError:
        raise HTTPException(status_code=404, detail="Transfer not found")
    # Snapshot identity-bearing fields BEFORE commit — once delete
    # commits, the row is gone and the audit row would have to
    # rebuild this from the void.
    label = (
        f"{transfer.sender_name or '?'} → "
        f"{transfer.recipient_name or '?'}"
        f" — ${(transfer.send_amount or 0):,.2f}"
    )
    summary = (
        f"confirm={transfer.confirm_number or ''} "
        f"company={transfer.company or ''} "
        f"status={transfer.status or ''}"
    )
    from api.Modules.Audit.Services import record_operator_action
    record_operator_action(
        db,
        store_id=int(sid),
        user_id=int(claims["sub"]),
        user_name=claims.get("name") or claims.get("username") or "",
        user_role=claims.get("role") or "",
        target_type="transfer",
        target_id=transfer.id,
        target_label=label,
        action="delete",
        summary=summary,
    )
    db.commit()
