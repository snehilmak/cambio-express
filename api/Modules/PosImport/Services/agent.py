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
    try:
        event = parse_pjr(content)
        business_date = event.business_date
        event_kind = event.kind
    except PosJournalParseError as exc:
        parse_error = str(exc)[:255]

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
            events.append(parse_pjr(gzip.decompress(f.content_gz)))
        except (PosJournalParseError, OSError):
            continue
    return events


__all__ = [
    "KEY_PREFIX", "MAX_AGENT_FILE_BYTES", "StageResult", "StagedDay",
    "authenticate_agent", "issue_agent_key", "list_agent_keys",
    "revoke_agent_key", "stage_journal_file", "staged_days",
    "staged_events_for_day",
]
