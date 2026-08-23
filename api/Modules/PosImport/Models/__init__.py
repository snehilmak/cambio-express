"""PosImport — Models.

``PosMerchandiseMap`` is the operator's one-time mapping from the
POS's numeric merchandise (department) codes to the store's own
Department catalog. Gilbarco journals identify departments only
by number ("4", "1024"); what those numbers MEAN is site
configuration the operator owns — same product principle as the
catalogs themselves (HANDOFF.md §2). Commit refuses to book a day
while any code present in the data is unmapped, so the mapping
review is a hard gate, not a silent default.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column, Date, DateTime, ForeignKey, Integer, LargeBinary, String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from api.Core.Database import Base


class PosMerchandiseMap(Base):
    __tablename__ = "pos_merchandise_map"
    id                = Column(Integer, primary_key=True)
    store_id          = Column(Integer, ForeignKey("store.id"), nullable=False, index=True)
    merchandise_code  = Column(String(20), nullable=False)
    department_id     = Column(
        Integer, ForeignKey("department.id"), nullable=False,
    )
    created_at        = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("store_id", "merchandise_code"),
    )

    department = relationship("Department")


class PosAgentCredential(Base):
    """API key for a site agent (the folder watcher installed at
    the store). The raw key ("pak_…") is shown exactly once at
    creation and stored only as sha256 — same contract as
    password-reset tokens (CLAUDE.md invariant #10). Revoke +
    re-issue instead of editing; ``last_used_at`` powers an
    "agent is alive" indicator."""

    __tablename__ = "pos_agent_credential"
    id           = Column(Integer, primary_key=True)
    store_id     = Column(Integer, ForeignKey("store.id"), nullable=False, index=True)
    key_hash     = Column(String(64), unique=True, nullable=False)
    label        = Column(String(80), nullable=False, default="")
    created_at   = Column(DateTime, default=datetime.utcnow)
    revoked_at   = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)


class PosJournalFile(Base):
    """One journal file pushed by a site agent, staged until the
    business day is committed. ``filename`` is unique per store so
    agent retries are idempotent. The gzipped raw XML is kept so
    commits re-parse the original (and future parser fixes can
    re-book history); ~2KB per transaction at c-store volume."""

    __tablename__ = "pos_journal_file"
    id            = Column(Integer, primary_key=True)
    store_id      = Column(Integer, ForeignKey("store.id"), nullable=False, index=True)
    filename      = Column(String(120), nullable=False)
    business_date = Column(Date, nullable=True, index=True)
    event_kind    = Column(String(16), nullable=False, default="")
    parse_error   = Column(String(255), nullable=False, default="")
    content_gz    = Column(LargeBinary, nullable=False)
    received_at   = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("store_id", "filename"),
    )


__all__ = ["PosAgentCredential", "PosJournalFile", "PosMerchandiseMap"]
