"""TimeClock — Controllers (FastAPI router).

Mounts at ``/api/v2/timeclock/*`` (employee-facing) and
``/api/v2/admin/timeclock`` (admin payroll view).

  POST  /timeclock/clock-in    — open a shift for a roster member
  POST  /timeclock/clock-out   — close the open shift
  GET   /timeclock/status      — currently-open shifts at the store
  GET   /admin/timeclock       — payroll history (admin / owner)

Tenancy: every endpoint reads ``store_id`` from
``resolve_store_scope(claims)``. The admin view filters on the
same store; cross-store / owner-umbrella consolidation is a
separate roadmap item.

Audit: every clock-in / clock-out writes an
``OperatorAuditLog`` row so a tampered shift surfaces in the
admin audit-log view.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Auth.Controllers import get_principal
from api.Modules.Auth.Services import resolve_store_scope
from api.Modules.TimeClock.Models import TimeClockEntry
from api.Modules.TimeClock.Requests import (
    AdminCreateEntryRequest,
    AdminUpdateEntryRequest,
    ClockPunchRequest,
    PunchChallengeRequest,
    PunchChallengeResponse,
    TimeClockCredentialList,
    TimeClockCredentialRow,
    TimeClockEntryList,
    TimeClockEntryRow,
    TimeClockHistoryResponse,
    TimeClockHistoryRow,
    TimeClockPunchResponse,
    TimeClockStatusResponse,
)
from api.Modules.TimeClock.Services import (
    AlreadyClockedInError,
    EntryNotFoundError,
    NotClockedInError,
    RosterEmployeeNotFoundError,
    admin_create_entry,
    admin_delete_entry,
    admin_update_entry,
    clock_in,
    clock_out,
    entries_for_period,
    open_entries_for_store,
)


router = APIRouter()

# Mounted separately at /api/v2/admin/timeclock for symmetry
# with the rest of the admin payroll surface.
admin_router = APIRouter()


# ── Adapters ────────────────────────────────────────────────


def _to_row(
    entry: TimeClockEntry, name_lookup: dict[int, str],
) -> TimeClockEntryRow:
    # Default-coerce ``status`` / ``adjusted`` so a row that
    # predates the migration (column-NULL on legacy data) still
    # renders consistently in the SPA.
    status = entry.status if entry.status in ("pending", "approved", "rejected") else "pending"
    return TimeClockEntryRow(
        id=entry.id,
        store_employee_id=entry.store_employee_id,
        employee_name=name_lookup.get(entry.store_employee_id, ""),
        clock_in_at=(
            entry.clock_in_at.isoformat() if entry.clock_in_at else ""
        ),
        clock_out_at=(
            entry.clock_out_at.isoformat() if entry.clock_out_at else None
        ),
        hours_worked=entry.hours_worked,
        notes=entry.notes or "",
        status=status,
        adjusted=bool(entry.adjusted),
    )


def _names_for(
    db: Session, entries: list[TimeClockEntry],
) -> dict[int, str]:
    """Single batch query for every employee name referenced
    by ``entries`` — avoids N+1."""
    from api.Modules.Tenancy.Models import StoreEmployee
    ids = {e.store_employee_id for e in entries}
    if not ids:
        return {}
    rows = (
        db.query(StoreEmployee.id, StoreEmployee.name)
          .filter(StoreEmployee.id.in_(ids))
          .all()
    )
    return {sid: name for sid, name in rows}


# ── Employee-facing endpoints ───────────────────────────────


@router.post(
    "/clock-in", response_model=TimeClockPunchResponse, status_code=201,
)
def clock_in_route(
    body: ClockPunchRequest,
    request: Request,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> TimeClockPunchResponse:
    """Open a new shift for the picked roster member at the
    current user's store. 409 when the employee already has an
    open shift; 404 when the roster id doesn't belong to this
    store; 401 when the store requires a passkey and the
    assertion is missing / invalid."""
    store_id = resolve_store_scope(claims)
    user_id = _user_id_from(claims)
    _enforce_passkey_gate(
        request, db,
        store_id=store_id,
        store_employee_id=body.store_employee_id,
        assert_token=body.assert_token,
        assertion=body.assertion,
    )
    try:
        entry = clock_in(
            db,
            store_id=store_id,
            store_employee_id=body.store_employee_id,
            user_id=user_id,
            notes=body.notes,
        )
    except RosterEmployeeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except AlreadyClockedInError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    _audit_punch(
        db,
        store_id=store_id, user_id=user_id, claims=claims,
        entry_id=entry.id,
        store_employee_id=body.store_employee_id,
        action="clock_in",
    )
    db.commit()
    return TimeClockPunchResponse(
        entry=_to_row(entry, _names_for(db, [entry])),
    )


@router.post(
    "/clock-out", response_model=TimeClockPunchResponse,
)
def clock_out_route(
    body: ClockPunchRequest,
    request: Request,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> TimeClockPunchResponse:
    """Close the picked roster member's open shift. 409 when
    nobody's clocked in for that name; 404 when the roster id
    doesn't belong to this store; 401 when the store requires
    a passkey and the assertion is missing / invalid."""
    store_id = resolve_store_scope(claims)
    user_id = _user_id_from(claims)
    _enforce_passkey_gate(
        request, db,
        store_id=store_id,
        store_employee_id=body.store_employee_id,
        assert_token=body.assert_token,
        assertion=body.assertion,
    )
    try:
        entry = clock_out(
            db,
            store_id=store_id,
            store_employee_id=body.store_employee_id,
            user_id=user_id,
            notes_append=body.notes,
        )
    except RosterEmployeeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except NotClockedInError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    _audit_punch(
        db,
        store_id=store_id, user_id=user_id, claims=claims,
        entry_id=entry.id,
        store_employee_id=body.store_employee_id,
        action="clock_out",
    )
    db.commit()
    return TimeClockPunchResponse(
        entry=_to_row(entry, _names_for(db, [entry])),
    )


@router.get(
    "/status", response_model=TimeClockStatusResponse,
)
def status_route(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> TimeClockStatusResponse:
    """Currently-open shifts at the principal's store — feeds
    the live "who's on the clock?" panel + powers the
    Clock-in/Clock-out button toggle."""
    store_id = resolve_store_scope(claims)
    open_entries = open_entries_for_store(db, store_id)
    names = _names_for(db, open_entries)
    return TimeClockStatusResponse(
        open_entries=[_to_row(e, names) for e in open_entries],
    )


# ── Admin payroll view ──────────────────────────────────────


@admin_router.get(
    "/timeclock", response_model=TimeClockEntryList,
)
def admin_entries_route(
    from_: date = Query(..., alias="from"),
    to: date = Query(...),
    store_employee_id: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> TimeClockEntryList:
    """Shifts that started inside ``[from, to)`` for the
    current user's store. ``to`` is half-open — pass the day
    AFTER the period end (a "May 1 – May 14" biweekly window
    is ``from=2026-05-01&to=2026-05-15``).

    Admin / owner only. The window is required to keep a
    runaway query from pulling the whole history.
    """
    if claims.get("role") not in ("admin", "owner", "superadmin"):
        raise HTTPException(
            status_code=403,
            detail="Only store admins can view the payroll history.",
        )
    store_id = resolve_store_scope(claims)
    if to <= from_:
        raise HTTPException(
            status_code=422, detail="'to' must be after 'from'.",
        )
    if (to - from_) > timedelta(days=370):
        raise HTTPException(
            status_code=422,
            detail="Date window cannot exceed 370 days.",
        )
    start_dt = datetime.combine(from_, datetime.min.time())
    end_dt   = datetime.combine(to,   datetime.min.time())
    rows = entries_for_period(
        db,
        store_id=store_id,
        start=start_dt,
        end=end_dt,
        store_employee_id=store_employee_id,
    )
    # Closed rows only; the split lets the SPA show distinct
    # "Approved" + "Pending" headline KPIs.
    closed_rows = [r for r in rows if r.clock_out_at is not None]
    total_hours = round(
        sum((r.hours_worked or 0.0) for r in closed_rows), 2,
    )
    approved_hours = round(
        sum((r.hours_worked or 0.0) for r in closed_rows
            if r.status == "approved"),
        2,
    )
    pending_hours = round(
        sum((r.hours_worked or 0.0) for r in closed_rows
            if (r.status or "pending") == "pending"),
        2,
    )
    names = _names_for(db, rows)
    return TimeClockEntryList(
        rows=[_to_row(r, names) for r in rows],
        total_hours=total_hours,
        approved_hours=approved_hours,
        pending_hours=pending_hours,
    )


# ── Admin CRUD (back-fill / edit / delete) ──────────────────


def _require_admin_role(claims: dict) -> None:
    if claims.get("role") not in ("admin", "owner", "superadmin"):
        raise HTTPException(
            status_code=403,
            detail="Only store admins can edit time-clock entries.",
        )


def _parse_iso(value: str, field: str) -> datetime:
    """Accept SPA-friendly ISO-8601 strings (``2026-05-18T14:30``
    or with trailing ``Z``). Raises 422 on parse failure with a
    helpful field name."""
    raw = (value or "").strip()
    if not raw:
        raise HTTPException(
            status_code=422, detail=f"{field} is required.",
        )
    # Normalize trailing 'Z' to '+00:00' so fromisoformat accepts it.
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"{field} is not a valid ISO-8601 datetime.",
        )
    # Drop tzinfo for comparison with the (naive UTC) column —
    # matches the storage convention used by the normal punch
    # endpoints.
    if dt.tzinfo is not None:
        dt = dt.astimezone(tz=None).replace(tzinfo=None)
    return dt


@admin_router.post(
    "/timeclock", response_model=TimeClockPunchResponse, status_code=201,
)
def admin_create_route(
    body: AdminCreateEntryRequest,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> TimeClockPunchResponse:
    """Admin back-fill: create a TimeClockEntry from scratch.
    Use case: cashier forgot to punch and the admin reconstructs
    the shift from memory / camera footage / a paper sign-in."""
    _require_admin_role(claims)
    store_id = resolve_store_scope(claims)
    clock_in_at  = _parse_iso(body.clock_in_at, "clock_in_at")
    clock_out_at = (
        _parse_iso(body.clock_out_at, "clock_out_at")
        if body.clock_out_at else None
    )
    try:
        entry, audit_summary = admin_create_entry(
            db,
            store_id=store_id,
            store_employee_id=body.store_employee_id,
            clock_in_at=clock_in_at,
            clock_out_at=clock_out_at,
            notes=body.notes,
        )
    except RosterEmployeeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    _write_audit(
        db,
        store_id=store_id, claims=claims,
        entry_id=entry.id,
        store_employee_id=body.store_employee_id,
        action="admin_create",
        summary=audit_summary,
    )
    db.commit()
    return TimeClockPunchResponse(
        entry=_to_row(entry, _names_for(db, [entry])),
    )


@admin_router.put(
    "/timeclock/{entry_id}", response_model=TimeClockPunchResponse,
)
def admin_update_route(
    body: AdminUpdateEntryRequest,
    entry_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> TimeClockPunchResponse:
    """Admin edit: replace timestamps / notes on an existing
    entry. Hours are recomputed. Field-level diff lands in the
    audit summary."""
    _require_admin_role(claims)
    store_id = resolve_store_scope(claims)
    patch: dict = {}
    set_fields = body.model_fields_set
    if "clock_in_at" in set_fields:
        if body.clock_in_at is None:
            raise HTTPException(
                status_code=422,
                detail="clock_in_at cannot be null — every shift has a start.",
            )
        patch["clock_in_at"] = _parse_iso(body.clock_in_at, "clock_in_at")
    if "clock_out_at" in set_fields:
        patch["clock_out_at"] = (
            _parse_iso(body.clock_out_at, "clock_out_at")
            if body.clock_out_at else None
        )
    if "notes" in set_fields:
        patch["notes"] = (body.notes or "")[:500]
    if "status" in set_fields:
        if body.status is None:
            raise HTTPException(
                status_code=422,
                detail="status cannot be null — pick pending / approved / rejected.",
            )
        patch["status"] = body.status
    try:
        entry, audit_summary = admin_update_entry(
            db,
            entry_id=entry_id, store_id=store_id, patch=patch,
        )
    except EntryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    _write_audit(
        db,
        store_id=store_id, claims=claims,
        entry_id=entry.id,
        store_employee_id=entry.store_employee_id,
        action="admin_update",
        summary=audit_summary,
    )
    db.commit()
    return TimeClockPunchResponse(
        entry=_to_row(entry, _names_for(db, [entry])),
    )


@admin_router.delete(
    "/timeclock/{entry_id}", status_code=204,
)
def admin_delete_route(
    entry_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> None:
    """Admin remove. Rare — typically only for entries that
    were back-filled in error. The audit chain still surfaces
    the deletion."""
    _require_admin_role(claims)
    store_id = resolve_store_scope(claims)
    try:
        store_employee_id, audit_summary = admin_delete_entry(
            db, entry_id=entry_id, store_id=store_id,
        )
    except EntryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    _write_audit(
        db,
        store_id=store_id, claims=claims,
        entry_id=entry_id,
        store_employee_id=store_employee_id,
        action="admin_delete",
        summary=audit_summary,
    )
    db.commit()
    return None


@admin_router.get(
    "/timeclock/{entry_id}/history",
    response_model=TimeClockHistoryResponse,
)
def admin_entry_history_route(
    entry_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> TimeClockHistoryResponse:
    """Per-entry audit chain — every clock-in, clock-out, and
    admin mutation that touched this row. Reverse-chronological."""
    _require_admin_role(claims)
    store_id = resolve_store_scope(claims)
    # Verify the entry belongs to this store before exposing the
    # chain — keeps a cross-tenant probe from leaking history.
    entry = db.get(TimeClockEntry, entry_id)
    if entry is None or entry.store_id != store_id:
        raise HTTPException(
            status_code=404,
            detail="That time-clock entry does not belong to this store.",
        )
    from api.Modules.Audit.Models import OperatorAuditLog
    rows = (
        db.query(OperatorAuditLog)
          .filter(
              OperatorAuditLog.store_id == store_id,
              OperatorAuditLog.target_type == "time_clock_entry",
              OperatorAuditLog.target_id == str(entry_id),
          )
          .order_by(OperatorAuditLog.id.desc())
          .all()
    )
    return TimeClockHistoryResponse(rows=[
        TimeClockHistoryRow(
            id=r.id,
            at=r.created_at.isoformat() if r.created_at else "",
            actor=r.user_name or "",
            actor_role=r.user_role or "",
            action=r.action or "",
            summary=r.summary or "",
        )
        for r in rows
    ])


# ── Internal helpers ────────────────────────────────────────


def _user_id_from(claims: dict) -> int | None:
    sub = claims.get("sub")
    if sub is None:
        return None
    try:
        return int(sub)
    except (TypeError, ValueError):
        return None


def _audit_punch(
    db: Session,
    *,
    store_id: int,
    user_id: int | None,
    claims: dict,
    entry_id: int,
    store_employee_id: int,
    action: str,
) -> None:
    """Audit a clock-in or clock-out. Summary is auto-generated
    from the action + roster name."""
    from api.Modules.Tenancy.Models import StoreEmployee
    emp = db.get(StoreEmployee, store_employee_id)
    emp_name = emp.name if emp else f"#{store_employee_id}"
    _write_audit(
        db,
        store_id=store_id, claims=claims,
        entry_id=entry_id,
        store_employee_id=store_employee_id,
        action=action,
        summary=f"{action.replace('_', ' ').title()}: {emp_name}",
        explicit_user_id=user_id,
    )


def _write_audit(
    db: Session,
    *,
    store_id: int,
    claims: dict,
    entry_id: int,
    store_employee_id: int,
    action: str,
    summary: str,
    explicit_user_id: int | None = None,
) -> None:
    """Write a single ``OperatorAuditLog`` row tagged
    ``target_type=time_clock_entry``. Reused by every endpoint
    that mutates an entry — the per-entry history view replays
    these rows."""
    from api.Modules.Audit.Services import record_operator_action
    from api.Modules.Tenancy.Models import StoreEmployee
    emp = db.get(StoreEmployee, store_employee_id)
    emp_name = emp.name if emp else f"#{store_employee_id}"
    user_id = (
        explicit_user_id
        if explicit_user_id is not None
        else _user_id_from(claims)
    )
    record_operator_action(
        db,
        store_id=store_id,
        user_id=user_id,
        user_name=str(claims.get("username") or ""),
        user_role=str(claims.get("role") or ""),
        target_type="time_clock_entry",
        target_id=str(entry_id),
        target_label=emp_name,
        action=action,
        summary=summary,
    )


# ── Passkey-gated punch (anti-buddy-punching) ───────────────


def _enforce_passkey_gate(
    request: Request,
    db: Session,
    *,
    store_id: int,
    store_employee_id: int,
    assert_token: str | None,
    assertion: dict | None,
) -> None:
    """When the store has ``timeclock_require_passkey=True``,
    refuse the punch unless a fresh WebAuthn assertion lands
    alongside the body. No-op for stores with the toggle off
    (the SPA omits the assertion fields entirely in that
    mode)."""
    from api.Modules.Tenancy.Models import Store
    store = db.get(Store, store_id)
    if store is None or not getattr(store, "timeclock_require_passkey", False):
        return
    if not assert_token or assertion is None:
        raise HTTPException(
            status_code=401,
            detail=(
                "This store requires a passkey on every punch. "
                "Use the Time-clock punch page (which prompts the "
                "OS-level authenticator) instead of a direct API call."
            ),
        )
    import jwt as _jwt
    from webauthn import verify_authentication_response
    from webauthn.helpers import base64url_to_bytes
    from api.Modules.Auth.Services.passkey import rp_id as _rp_id, origin as _origin
    from api.Modules.TimeClock.Models import StoreEmployeePasskey
    from api.Modules.TimeClock.Services.passkey import (
        PasskeyNotRegisteredError,
        decode_assert_token,
        passkey_for_employee,
    )
    try:
        claims = decode_assert_token(assert_token)
    except _jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=401,
            detail=f"Punch challenge expired or invalid: {exc}",
        )
    # Pin the assertion to the exact roster + store the SPA
    # picked — a token reissued for a different employee can't
    # be replayed against this one.
    if (
        int(claims.get("store_id") or 0) != store_id
        or int(claims.get("store_employee_id") or 0) != store_employee_id
    ):
        raise HTTPException(
            status_code=401,
            detail="Punch challenge does not match this punch.",
        )
    expected_challenge = base64url_to_bytes(claims["challenge"])
    pk = passkey_for_employee(db, store_id, store_employee_id)
    if pk is None:
        raise PasskeyNotRegisteredError  # turned into 422 below
    host   = request.url.netloc
    scheme = request.url.scheme
    try:
        verification = verify_authentication_response(
            credential=assertion,
            expected_challenge=expected_challenge,
            expected_rp_id=_rp_id(host),
            expected_origin=_origin(scheme, host),
            credential_public_key=pk.public_key,
            credential_current_sign_count=pk.sign_count,
            require_user_verification=False,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail=f"Passkey assertion did not verify: {exc}",
        )
    # Accept equal-or-greater sign counts — cloned authenticator
    # detection (cf. WebAuthn §6.1.2). Reject backwards counts.
    new_count = int(getattr(verification, "new_sign_count", pk.sign_count))
    if new_count < pk.sign_count:
        raise HTTPException(
            status_code=401,
            detail="Authenticator clone suspected (sign count reset).",
        )
    pk.sign_count   = new_count
    pk.last_used_at = datetime.utcnow()
    db.flush()


@router.post(
    "/passkey/challenge", response_model=PunchChallengeResponse,
)
def punch_challenge_route(
    body: PunchChallengeRequest,
    request: Request,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> PunchChallengeResponse:
    """Mint a WebAuthn assertion challenge for the picked
    roster member. The SPA passes ``options_json`` to
    ``navigator.credentials.get()`` and echoes ``assert_token``
    back on the clock-in / clock-out call.

    422 when the roster member doesn't have a passkey
    registered yet — the SPA surfaces a "ask the admin to
    enroll your device" message."""
    store_id = resolve_store_scope(claims)
    from api.Modules.Tenancy.Models import StoreEmployee
    emp = db.get(StoreEmployee, body.store_employee_id)
    if emp is None or emp.store_id != store_id:
        raise HTTPException(
            status_code=404,
            detail="That roster member doesn't belong to this store.",
        )
    from webauthn import generate_authentication_options, options_to_json
    from webauthn.helpers import bytes_to_base64url
    from api.Modules.Auth.Services.passkey import rp_id as _rp_id
    from api.Modules.TimeClock.Services.passkey import (
        allow_credentials_for, issue_assert_token,
    )
    creds = allow_credentials_for(db, store_id, body.store_employee_id)
    if not creds:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{emp.name} has no passkey registered yet. "
                "Ask an admin to enroll their device on "
                "/app/admin/timeclock/credentials before requiring "
                "passkey punches."
            ),
        )
    options = generate_authentication_options(
        rp_id=_rp_id(request.url.netloc),
        allow_credentials=creds,
    )
    return PunchChallengeResponse(
        options_json=options_to_json(options),
        assert_token=issue_assert_token(
            store_id=store_id,
            store_employee_id=body.store_employee_id,
            challenge_b64=bytes_to_base64url(options.challenge),
        ),
    )


# ── Admin: roster passkey enrollment ────────────────────────


@admin_router.get(
    "/timeclock/credentials", response_model=TimeClockCredentialList,
)
def admin_credentials_list_route(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> TimeClockCredentialList:
    """List every active roster member at the store with a
    has_passkey flag. Powers the admin enrollment page so the
    operator sees who's pending vs registered."""
    _require_admin_role(claims)
    store_id = resolve_store_scope(claims)
    from api.Modules.Tenancy.Models import StoreEmployee
    from api.Modules.TimeClock.Services.passkey import list_passkeys_for_store
    employees = (
        db.query(StoreEmployee)
          .filter(
              StoreEmployee.store_id == store_id,
              StoreEmployee.is_active == True,  # noqa: E712
          )
          .order_by(StoreEmployee.name.asc())
          .all()
    )
    passkeys_by_emp = {
        pk.store_employee_id: pk
        for pk in list_passkeys_for_store(db, store_id)
    }
    rows = []
    for emp in employees:
        pk = passkeys_by_emp.get(emp.id)
        rows.append(TimeClockCredentialRow(
            store_employee_id=emp.id,
            employee_name=emp.name,
            has_passkey=pk is not None,
            name=(pk.name if pk else ""),
            registered_at=(
                pk.registered_at.isoformat()
                if pk and pk.registered_at else ""
            ),
            last_used_at=(
                pk.last_used_at.isoformat()
                if pk and pk.last_used_at else ""
            ),
        ))
    return TimeClockCredentialList(rows=rows)


@admin_router.post("/timeclock/credentials/{store_employee_id}/register/begin")
def admin_credentials_register_begin_route(
    request: Request,
    store_employee_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> dict:
    """Start a WebAuthn registration ceremony for the picked
    roster member. The admin walks the cashier through the
    OS-level prompt; the SPA passes ``options_json`` to
    ``navigator.credentials.create()`` and echoes
    ``register_token`` back on /register/finish."""
    _require_admin_role(claims)
    store_id = resolve_store_scope(claims)
    from api.Modules.Tenancy.Models import StoreEmployee
    emp = db.get(StoreEmployee, store_employee_id)
    if emp is None or emp.store_id != store_id:
        raise HTTPException(
            status_code=404,
            detail="That roster member doesn't belong to this store.",
        )
    from webauthn import generate_registration_options, options_to_json
    from webauthn.helpers import bytes_to_base64url
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        UserVerificationRequirement,
    )
    from api.Modules.Auth.Services.passkey import (
        rp_id as _rp_id, rp_name as _rp_name,
    )
    from api.Modules.TimeClock.Services.passkey import (
        emp_handle, issue_register_token, passkey_for_employee,
    )
    # Surface existing registration as an excludeCredentials
    # entry so the OS picker offers a fresh authenticator
    # (the v1 cap is one passkey per roster row, but seeing
    # the existing one in the picker prevents accidental
    # duplicate-create flows).
    existing = passkey_for_employee(db, store_id, store_employee_id)
    from webauthn.helpers.structs import PublicKeyCredentialDescriptor
    exclude = (
        [PublicKeyCredentialDescriptor(id=existing.credential_id)]
        if existing else []
    )
    options = generate_registration_options(
        rp_id=_rp_id(request.url.netloc),
        rp_name=_rp_name(),
        user_id=emp_handle(store_employee_id),
        user_name=emp.name,
        user_display_name=emp.name,
        exclude_credentials=exclude,
        authenticator_selection=AuthenticatorSelectionCriteria(
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    return {
        "options_json":   options_to_json(options),
        "register_token": issue_register_token(
            store_id=store_id,
            store_employee_id=store_employee_id,
            challenge_b64=bytes_to_base64url(options.challenge),
        ),
    }


@admin_router.post(
    "/timeclock/credentials/{store_employee_id}/register/finish",
    response_model=TimeClockCredentialRow,
)
def admin_credentials_register_finish_route(
    body: dict,
    request: Request,
    store_employee_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> TimeClockCredentialRow:
    """Verify the authenticator's attestation + persist the new
    StoreEmployeePasskey row. Replaces any existing row for the
    same roster member (v1 caps at one passkey per cashier)."""
    _require_admin_role(claims)
    store_id = resolve_store_scope(claims)
    from api.Modules.Tenancy.Models import StoreEmployee
    emp = db.get(StoreEmployee, store_employee_id)
    if emp is None or emp.store_id != store_id:
        raise HTTPException(
            status_code=404,
            detail="That roster member doesn't belong to this store.",
        )
    register_token = (body or {}).get("register_token") or ""
    credential = (body or {}).get("credential")
    name = ((body or {}).get("name") or "").strip()[:120] or emp.name
    if not register_token or credential is None:
        raise HTTPException(
            status_code=400,
            detail="Missing register_token or credential.",
        )
    import jwt as _jwt
    from webauthn import verify_registration_response
    from webauthn.helpers import base64url_to_bytes
    from api.Modules.Auth.Services.passkey import rp_id as _rp_id, origin as _origin
    from api.Modules.TimeClock.Models import StoreEmployeePasskey
    from api.Modules.TimeClock.Services.passkey import (
        decode_register_token, passkey_for_employee,
    )
    try:
        token_claims = decode_register_token(register_token)
    except _jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=401,
            detail=f"Registration challenge expired or invalid: {exc}",
        )
    if (
        int(token_claims.get("store_id") or 0) != store_id
        or int(token_claims.get("store_employee_id") or 0) != store_employee_id
    ):
        raise HTTPException(
            status_code=401,
            detail="Registration challenge does not match this roster member.",
        )
    expected_challenge = base64url_to_bytes(token_claims["challenge"])
    host   = request.url.netloc
    scheme = request.url.scheme
    try:
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_rp_id=_rp_id(host),
            expected_origin=_origin(scheme, host),
            require_user_verification=False,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Passkey registration did not verify: {exc}",
        )
    # Replace any existing row — v1 keeps one passkey per
    # roster member. The unique constraint on
    # ``store_employee_id`` would 500 otherwise.
    existing = passkey_for_employee(db, store_id, store_employee_id)
    if existing is not None:
        db.delete(existing)
        db.flush()
    aaguid = getattr(verification, "aaguid", "") or ""
    pk = StoreEmployeePasskey(
        store_id=store_id,
        store_employee_id=store_employee_id,
        credential_id=verification.credential_id,
        public_key=verification.credential_public_key,
        sign_count=int(getattr(verification, "sign_count", 0) or 0),
        aaguid=str(aaguid)[:64],
        name=name,
        registered_at=datetime.utcnow(),
        registered_by_user_id=_user_id_from(claims),
    )
    db.add(pk)
    db.commit()
    return TimeClockCredentialRow(
        store_employee_id=store_employee_id,
        employee_name=emp.name,
        has_passkey=True,
        name=pk.name or emp.name,
        registered_at=pk.registered_at.isoformat() if pk.registered_at else "",
        last_used_at="",
    )


@admin_router.delete(
    "/timeclock/credentials/{store_employee_id}", status_code=204,
)
def admin_credentials_delete_route(
    store_employee_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> None:
    """Remove the roster member's passkey. Used when the
    cashier swaps devices or leaves."""
    _require_admin_role(claims)
    store_id = resolve_store_scope(claims)
    from api.Modules.TimeClock.Services.passkey import passkey_for_employee
    pk = passkey_for_employee(db, store_id, store_employee_id)
    if pk is None:
        raise HTTPException(
            status_code=404,
            detail="That roster member has no passkey to remove.",
        )
    db.delete(pk)
    db.commit()
    return None
