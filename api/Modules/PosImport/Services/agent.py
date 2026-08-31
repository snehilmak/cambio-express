"""PosImport — site-agent credentials + journal staging.

Phase B of the Gilbarco wedge: a thin watcher installed at the
store pushes each new journal file to the API the moment Passport
writes it. The agent is deliberately dumb (HANDOFF.md §2 — parse
stays server-side so fleet agents never need updates for parser
work): it authenticates with a per-store key, sends the raw file,
and the server does everything else.

* Keys: "pak_…" shown once, stored as sha256 (invariant #10
  contract). Revoke + re-issue; ``last_used_at`` doubles as the
  agent heartbeat.
* Staging: one ``PosJournalFile`` row per pushed file, unique on
  (store, filename) so agent retries are idempotent. Raw XML is
  kept gzipped so day commits re-parse originals and parser fixes
  can re-book history.
* Commit: the operator books a staged business day through the
  same ``commit_business_day`` path as manual uploads — same
  mapping gate, same audit, same idempotent day replacement.
"""
from __future__ import annotations

import gzip
import hashlib
import secrets
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from api.Modules.DayClose.Models import RegisterClose
from api.Modules.PosImport.Models import (
    PosAgentCredential,
    PosJournalFile,
)
from api.Modules.PosImport.Services.ingest import (
    IMPORT_SOURCE,
    PosImportError,
)
from api.Modules.PosImport.Services.naxml import (
    PjrEvent,
    PosJournalParseError,
    parse_pjr,
)

KEY_PREFIX = "pak_"
MAX_AGENT_FILE_BYTES = 4 * 1024 * 1024


def _hash(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


# ── Credentials ────────────────────────────────────────────


def issue_agent_key(
    db: Session, store_id: int, *, label: str = "",
) -> tuple[PosAgentCredential, str]:
    """Mint a new agent key. The raw value is returned exactly
    once — only the hash is stored."""
    raw = KEY_PREFIX + secrets.token_urlsafe(32)
    cred = PosAgentCredential(
        store_id=store_id, key_hash=_hash(raw), label=label.strip(),
    )
    db.add(cred)
    db.flush()
    return cred, raw


def list_agent_keys(
    db: Session, store_id: int,
) -> list[PosAgentCredential]:
    return (
        db.query(PosAgentCredential)
        .filter_by(store_id=store_id)
        .order_by(PosAgentCredential.created_at.desc())
        .all()
    )


def revoke_agent_key(
    db: Session, store_id: int, key_id: int,
) -> PosAgentCredential:
    cred = db.get(PosAgentCredential, key_id)
    if cred is None or cred.store_id != store_id:
        raise PosImportError("Agent key not found")
    if cred.revoked_at is None:
        cred.revoked_at = datetime.utcnow()
        db.flush()
    return cred


def authenticate_agent(
    db: Session, raw_key: str,
) -> PosAgentCredential | None:
    """Resolve a presented key to its live credential, stamping the
    heartbeat. None for unknown/revoked (caller returns an opaque
    401 — no enumeration hints)."""
    if not raw_key or not raw_key.startswith(KEY_PREFIX):
        return None
    cred = (
        db.query(PosAgentCredential)
        .filter_by(key_hash=_hash(raw_key))
        .first()
    )
    if cred is None or cred.revoked_at is not None:
        return None
    cred.last_used_at = datetime.utcnow()
    db.flush()
    return cred


# ── Staging ────────────────────────────────────────────────


@dataclass
class StageResult:
    file: PosJournalFile
    duplicate: bool


def stage_journal_file(
    db: Session, store_id: int, *, filename: str, content: bytes,
) -> StageResult:
    """Store one pushed journal file. Idempotent on (store,
    filename) — the agent can retry safely. Files that fail to
    parse are staged anyway with the error recorded (a future
    parser fix re-parses them at commit time)."""
    filename = filename.strip().rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if not filename:
        raise PosImportError("Filename is required.")
    if len(content) > MAX_AGENT_FILE_BYTES:
        raise PosImportError("File too large.")

    existing = (
        db.query(PosJournalFile)
        .filter_by(store_id=store_id, filename=filename)
        .first()
    )
    if existing is not None:
        return StageResult(file=existing, duplicate=True)

    business_date: date | None = None
    event_kind = ""
    parse_error = ""
    event = None
    try:
        event = parse_pjr(content)
        business_date = event.business_date
        event_kind = event.kind
    except PosJournalParseError as exc:
        parse_error = str(exc)[:255]

    # G-3 live hourly preview: increment the hour bucket as each
    # sale/refund arrives so the dashboard's hourly chart tracks
    # the CURRENT business day in near-real-time. Commit rebuilds
    # the day from the staged originals, self-healing any drift
    # (e.g. an upload that raced or a later parser fix). Runs
    # only for brand-new files — the duplicate short-circuit above
    # already returned, so retries never double-count.
    if (
        event is not None
        and event.kind in ("sale", "refund")
        and business_date is not None
        and event.event_hour is not None
    ):
        from api.Modules.DayClose.Models import HourlySale
        from api.Modules.PosImport.Services.ingest import IMPORT_SOURCE
        bucket = (
            db.query(HourlySale)
            .filter_by(
                store_id=store_id, report_date=business_date,
                hour=event.event_hour, source=IMPORT_SOURCE,
            )
            .first()
        )
        if bucket is None:
            db.add(HourlySale(
                store_id=store_id, report_date=business_date,
                hour=event.event_hour,
                amount_cents=event.net_cents,
                source=IMPORT_SOURCE,
            ))
        else:
            bucket.amount_cents = (
                int(bucket.amount_cents or 0) + event.net_cents
            )

    row = PosJournalFile(
        store_id=store_id,
        filename=filename,
        business_date=business_date,
        event_kind=event_kind,
        parse_error=parse_error,
        content_gz=gzip.compress(content),
    )
    db.add(row)
    db.flush()
    return StageResult(file=row, duplicate=False)


@dataclass
class StagedDay:
    business_date: date
    file_count: int
    error_count: int
    committed: bool


def staged_days(db: Session, store_id: int) -> list[StagedDay]:
    """Business days with staged files, newest first, flagged when
    the day already has imported closes (i.e. was committed —
    possibly before more files arrived)."""
    rows = (
        db.query(
            PosJournalFile.business_date,
            func.count(PosJournalFile.id),
        )
        .filter(
            PosJournalFile.store_id == store_id,
            PosJournalFile.business_date.isnot(None),
        )
        .group_by(PosJournalFile.business_date)
        .order_by(PosJournalFile.business_date.desc())
        .all()
    )
    error_days = {
        d for (d,) in db.query(PosJournalFile.business_date)
        .filter(
            PosJournalFile.store_id == store_id,
            PosJournalFile.parse_error != "",
            PosJournalFile.business_date.isnot(None),
        )
        .distinct()
        .all()
    }
    committed_days = {
        d for (d,) in db.query(RegisterClose.report_date)
        .filter(
            RegisterClose.store_id == store_id,
            RegisterClose.source == IMPORT_SOURCE,
        )
        .distinct()
        .all()
    }
    out = []
    for day, count in rows:
        errors = 0
        if day in error_days:
            errors = (
                db.query(func.count(PosJournalFile.id))
                .filter_by(
                    store_id=store_id, business_date=day,
                )
                .filter(PosJournalFile.parse_error != "")
                .scalar()
            ) or 0
        out.append(StagedDay(
            business_date=day,
            file_count=int(count),
            error_count=int(errors),
            committed=day in committed_days,
        ))
    return out


AUTO_COMMIT_LOOKBACK_DAYS = 3


def auto_commit_rolled_days(db: Session, store_id: int) -> list:
    """Auto-book recently ROLLED business days (G-1 — the
    hands-off ingestion loop). Called after each agent upload; a
    day D is booked only when every gate passes:

      * a staged file with a NEWER business date exists — the
        site's day has rolled (Passport's BusinessDate advances at
        the site day close, so this is the authoritative "day D is
        complete" signal),
      * D has NO RegisterClose rows from ANY source — manual
        entries are never doubled up, and late files for an
        already-booked day stay a manual re-commit (which replaces
        idempotently),
      * no file for D has a parse error (a parser fix re-parses
        history — don't book a known-partial day),
      * D is inside a short lookback window — the backlog from a
        fresh agent install stays a reviewed, manual warm start,
      * every merchandise code is mapped (commit_business_day's
        gate) — an unmapped day is skipped silently and retried on
        the next upload, so mapping completion is all an operator
        needs to do.

    Each booked day writes a system operator-audit row. Caller
    commits. Returns the CommitDayResult list (empty = nothing was
    ready)."""
    from datetime import timedelta

    from api.Modules.Audit.Services import record_operator_action
    from api.Modules.PosImport.Services.ingest import (
        PosImportError,
        commit_business_day,
    )

    latest = (
        db.query(func.max(PosJournalFile.business_date))
        .filter(
            PosJournalFile.store_id == store_id,
            PosJournalFile.business_date.isnot(None),
        )
        .scalar()
    )
    if latest is None:
        return []
    window_start = latest - timedelta(days=AUTO_COMMIT_LOOKBACK_DAYS)
    candidates = [
        d for (d,) in db.query(PosJournalFile.business_date)
        .filter(
            PosJournalFile.store_id == store_id,
            PosJournalFile.business_date.isnot(None),
            PosJournalFile.business_date < latest,
            PosJournalFile.business_date >= window_start,
        )
        .distinct()
        .all()
    ]
    if not candidates:
        return []
    booked_dates = {
        d for (d,) in db.query(RegisterClose.report_date)
        .filter(
            RegisterClose.store_id == store_id,
            RegisterClose.report_date.in_(candidates),
        )
        .distinct()
        .all()
    }
    error_dates = {
        d for (d,) in db.query(PosJournalFile.business_date)
        .filter(
            PosJournalFile.store_id == store_id,
            PosJournalFile.business_date.in_(candidates),
            PosJournalFile.parse_error != "",
        )
        .distinct()
        .all()
    }
    results = []
    for day in sorted(candidates):
        if day in booked_dates or day in error_dates:
            continue
        events = staged_events_for_day(db, store_id, day)
        try:
            result = commit_business_day(
                db, store_id, day, events=events, created_by=None,
            )
        except PosImportError:
            # Unmapped codes (or an empty day) — leave it staged;
            # the next upload retries after the operator maps.
            continue
        record_operator_action(
            db,
            store_id=store_id,
            user_id=None,
            user_name="Gilbarco site agent",
            user_role="system",
            target_type="register_close",
            target_id=day.isoformat(),
            action="commit_pos_import_auto",
            summary=(
                f"auto-booked rolled day {day.isoformat()}: "
                f"{result.closes_written} register close(s)"
            ),
        )
        results.append(result)
    return results


def staged_events_for_day(
    db: Session, store_id: int, day: date,
) -> list[PjrEvent]:
    """Re-parse the staged originals for one business day. Files
    whose stored parse_error persists are skipped (they were never
    counted toward the day either)."""
    files = (
        db.query(PosJournalFile)
        .filter_by(store_id=store_id, business_date=day)
        .all()
    )
    events: list[PjrEvent] = []
    for f in files:
        try:
            event = parse_pjr(gzip.decompress(f.content_gz))
        except (PosJournalParseError, OSError):
            continue
        # Carry the filename through so the persisted transaction
        # (G-5) can key on it and stay idempotent across re-commits.
        event.source_file = f.filename
        events.append(event)
    return events


__all__ = [
    "KEY_PREFIX", "MAX_AGENT_FILE_BYTES", "StageResult", "StagedDay",
    "authenticate_agent", "issue_agent_key", "list_agent_keys",
    "revoke_agent_key", "stage_journal_file", "staged_days",
    "staged_events_for_day",
]
