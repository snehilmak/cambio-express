"""PosImport module — Controllers (FastAPI router).

Mounts at `/api/v2/posimport/*`:

  POST /naxml/preview   parse an upload (one PJR XML or a ZIP of
                        many), return per-(day, register)
                        aggregates + mapping status. In-memory
                        only — nothing is persisted.
  GET  /mapping         the store's merchandise-code → department
                        mappings.
  PUT  /mapping         upsert mappings (admin).
  POST /naxml/commit    re-parse the upload server-side and book
                        ONE business day into DayClose
                        (source="gilbarco"). Blocks with 422
                        while any code in the data is unmapped.

Imports write day-close data, so every route requires
day_close.update (admin) — the same surface that owns the
Department catalog. Every mutation records an operator-audit row
(invariant #7).
"""
import base64
import binascii
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Core.RateLimit import limiter as _rate_limiter
from api.Modules.Auth.Controllers import get_principal
from api.Modules.Auth.Services.principal import (
    require_permission,
    resolve_store_scope,
)
from api.Modules.PosImport.Requests import (
    AgentKeyIssueRequest,
    AgentKeyIssueResponse,
    AgentKeyListResponse,
    AgentKeyRow,
    AgentUploadRequest,
    AgentUploadResponse,
    FuelGradeRow,
    ImportDepartmentRow,
    ImportRegisterRow,
    MappingListResponse,
    MappingRow,
    MappingWriteRequest,
    NaxmlCommitRequest,
    NaxmlCommitResponse,
    NaxmlPreviewResponse,
    NaxmlUploadRequest,
    StagedCommitRequest,
    StagedDayRow,
    StagedDaysResponse,
)
from api.Modules.PosImport.Services import (
    LoadedPayload,
    PosImportError,
    aggregate_events,
    authenticate_agent,
    commit_business_day,
    issue_agent_key,
    list_agent_keys,
    list_mappings,
    load_pjr_payload,
    mapping_status,
    register_label_for,
    revoke_agent_key,
    set_mappings,
    stage_journal_file,
    staged_days,
    staged_events_for_day,
)

router = APIRouter(prefix="/posimport", tags=["posimport"])


def _audit(
    db: Session, *, claims: dict[str, Any], action: str,
    target_type: str, target_id: str, summary: str,
) -> None:
    """Operator-audit emitter — CLAUDE.md invariant #7."""
    from api.Modules.Audit.Services import record_operator_action
    record_operator_action(
        db,
        store_id=int(claims["store_id"]),
        user_id=int(claims["sub"]),
        user_name=claims.get("name") or claims.get("username") or "",
        user_role=claims.get("role") or "",
        target_type=target_type,
        action=action,
        target_id=target_id,
        summary=summary[:255],
    )


def _decode_payload(content_base64: str) -> bytes:
    try:
        return base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(
            status_code=422, detail="content_base64 is not valid base64.",
        )


def _load_or_422(data: bytes) -> LoadedPayload:
    try:
        return load_pjr_payload(data)
    except PosImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/naxml/preview", response_model=NaxmlPreviewResponse)
def preview_naxml_route(
    body: NaxmlUploadRequest,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> NaxmlPreviewResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "day_close", "update")
    loaded = _load_or_422(_decode_payload(body.content_base64))
    days = aggregate_events(loaded.events)
    mapped, unmapped = mapping_status(db, sid, days)
    dept_names = {
        m.department_id: (m.department.name or "")
        for m in list_mappings(db, sid)
    }
    registers = [
        ImportRegisterRow(
            business_date=a.business_date.isoformat(),
            register_label=register_label_for(a.register_id),
            net_sales=a.net_sales_cents / 100.0,
            sales_tax=a.tax_cents / 100.0,
            refunds=a.refunds_cents / 100.0,
            cash_total=a.cash_cents / 100.0,
            card_total=a.card_cents / 100.0,
            other_total=a.other_tender_cents / 100.0,
            sale_count=a.sale_count,
            refund_count=a.refund_count,
            opening_cash=(
                None if a.opening_cash_cents is None
                else a.opening_cash_cents / 100.0
            ),
            departments=[
                ImportDepartmentRow(
                    merchandise_code=code,
                    amount=cents / 100.0,
                    department_id=mapped.get(code),
                    department_name=dept_names.get(mapped.get(code, -1), ""),
                )
                for code, cents in sorted(a.departments.items())
            ],
            fuel=[
                FuelGradeRow(
                    grade_id=g.grade_id,
                    description=g.description,
                    gallons=round(g.gallons, 3),
                    amount=g.amount_cents / 100.0,
                )
                for g in sorted(a.fuel.values(), key=lambda g: g.grade_id)
            ],
        )
        for a in days
    ]
    return NaxmlPreviewResponse(
        file_count=loaded.file_count,
        event_count=len(loaded.events),
        parse_errors=loaded.parse_errors[:50],
        business_dates=sorted({
            a.business_date.isoformat() for a in days
        }),
        registers=registers,
        unmapped_codes=unmapped,
    )


@router.get("/mapping", response_model=MappingListResponse)
def list_mapping_route(
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> MappingListResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "day_close", "update")
    return MappingListResponse(mappings=[
        MappingRow(
            merchandise_code=m.merchandise_code,
            department_id=int(m.department_id),
            department_name=m.department.name or "",
        )
        for m in list_mappings(db, sid)
    ])


@router.put("/mapping", response_model=MappingListResponse)
def set_mapping_route(
    body: MappingWriteRequest,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> MappingListResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "day_close", "update")
    mappings = {
        row.merchandise_code.strip(): row.department_id
        for row in body.mappings
    }
    try:
        rows = set_mappings(db, sid, mappings)
    except PosImportError:
        raise HTTPException(status_code=404, detail="Department not found")
    _audit(
        db, claims=claims, action="set_pos_merchandise_mapping",
        target_type="pos_merchandise_map", target_id=str(sid),
        summary=f"{len(mappings)} code mapping(s) set",
    )
    db.commit()
    return MappingListResponse(mappings=[
        MappingRow(
            merchandise_code=m.merchandise_code,
            department_id=int(m.department_id),
            department_name=m.department.name or "",
        )
        for m in rows
    ])


@router.post("/naxml/commit", response_model=NaxmlCommitResponse)
def commit_naxml_route(
    body: NaxmlCommitRequest,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> NaxmlCommitResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "day_close", "update")
    try:
        day = datetime.strptime(body.day, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=422, detail="day must be YYYY-MM-DD")
    loaded = _load_or_422(_decode_payload(body.content_base64))
    try:
        result = commit_business_day(
            db, sid, day,
            events=loaded.events,
            created_by=int(claims["sub"]),
        )
    except PosImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    _audit(
        db, claims=claims, action="commit_pos_import",
        target_type="register_close", target_id=day.isoformat(),
        summary=(
            f"Gilbarco import {day.isoformat()}: "
            f"{result.closes_written} register close(s) "
            f"({', '.join(result.registers)})"
        ),
    )
    db.commit()
    return NaxmlCommitResponse(
        day=result.day.isoformat(),
        closes_written=result.closes_written,
        registers=result.registers,
    )


# ── Site agent (Phase B) ───────────────────────────────────


def _key_row(c) -> AgentKeyRow:
    return AgentKeyRow(
        id=c.id,
        label=c.label or "",
        created_at=c.created_at.isoformat() if c.created_at else "",
        last_used_at=(
            c.last_used_at.isoformat() if c.last_used_at else None
        ),
        revoked=c.revoked_at is not None,
    )


@router.get("/agent-keys", response_model=AgentKeyListResponse)
def list_agent_keys_route(
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> AgentKeyListResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "day_close", "update")
    return AgentKeyListResponse(
        keys=[_key_row(c) for c in list_agent_keys(db, sid)],
    )


@router.post(
    "/agent-keys", response_model=AgentKeyIssueResponse, status_code=201,
)
def issue_agent_key_route(
    body: AgentKeyIssueRequest,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> AgentKeyIssueResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "day_close", "update")
    cred, raw = issue_agent_key(db, sid, label=body.label)
    _audit(
        db, claims=claims, action="issue_pos_agent_key",
        target_type="pos_agent_credential", target_id=str(cred.id),
        summary=f"agent key issued ({cred.label or 'unlabeled'})",
    )
    db.commit()
    # The raw key crosses the wire exactly once, here.
    return AgentKeyIssueResponse(id=cred.id, label=cred.label or "", key=raw)


@router.post(
    "/agent-keys/{key_id}/revoke", response_model=AgentKeyListResponse,
)
def revoke_agent_key_route(
    key_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> AgentKeyListResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "day_close", "update")
    try:
        cred = revoke_agent_key(db, sid, key_id)
    except PosImportError:
        raise HTTPException(status_code=404, detail="Agent key not found")
    _audit(
        db, claims=claims, action="revoke_pos_agent_key",
        target_type="pos_agent_credential", target_id=str(cred.id),
        summary=f"agent key revoked ({cred.label or 'unlabeled'})",
    )
    db.commit()
    return AgentKeyListResponse(
        keys=[_key_row(c) for c in list_agent_keys(db, sid)],
    )


@router.post("/agent/upload", response_model=AgentUploadResponse)
@_rate_limiter.limit("120/minute;6000/hour")
def agent_upload_route(
    request: Request,
    body: AgentUploadRequest,
    x_agent_key: str = Header(""),
    db: Session = Depends(get_db),
) -> AgentUploadResponse:
    """Site-agent push: one journal file per call, authenticated by
    the per-store agent key (opaque 401 on any failure — no
    enumeration hints). Idempotent per filename so retries are
    free. Commits its own transaction: staging isn't an operator
    mutation, so there's no audit row to co-commit."""
    cred = authenticate_agent(db, x_agent_key)
    if cred is None:
        raise HTTPException(status_code=401, detail="Invalid agent key.")
    try:
        result = stage_journal_file(
            db, int(cred.store_id),
            filename=body.filename,
            content=_decode_payload(body.content_base64),
        )
    except PosImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    return AgentUploadResponse(
        staged=not result.duplicate,
        duplicate=result.duplicate,
        business_date=(
            result.file.business_date.isoformat()
            if result.file.business_date else None
        ),
        parse_error=result.file.parse_error or "",
    )


@router.get("/staged", response_model=StagedDaysResponse)
def staged_days_route(
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> StagedDaysResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "day_close", "update")
    return StagedDaysResponse(days=[
        StagedDayRow(
            business_date=d.business_date.isoformat(),
            file_count=d.file_count,
            error_count=d.error_count,
            committed=d.committed,
        )
        for d in staged_days(db, sid)
    ])


@router.post("/staged/commit", response_model=NaxmlCommitResponse)
def commit_staged_route(
    body: StagedCommitRequest,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> NaxmlCommitResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "day_close", "update")
    try:
        day = datetime.strptime(body.day, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=422, detail="day must be YYYY-MM-DD")
    events = staged_events_for_day(db, sid, day)
    try:
        result = commit_business_day(
            db, sid, day, events=events,
            created_by=int(claims["sub"]),
        )
    except PosImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    _audit(
        db, claims=claims, action="commit_pos_import",
        target_type="register_close", target_id=day.isoformat(),
        summary=(
            f"Gilbarco staged import {day.isoformat()}: "
            f"{result.closes_written} register close(s)"
        ),
    )
    db.commit()
    return NaxmlCommitResponse(
        day=result.day.isoformat(),
        closes_written=result.closes_written,
        registers=result.registers,
    )
