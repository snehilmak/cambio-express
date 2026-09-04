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
    BigInteger, Boolean, Column, Date, DateTime, Float, ForeignKey,
    Integer, LargeBinary, String, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from api.Core.Database import Base


class PosMerchandiseMap(Base):
    __tablename__ = "retail_pos_merchandise_map"
    id                = Column(Integer, primary_key=True)
    store_id          = Column(Integer, ForeignKey("tenancy_store.id"), nullable=False, index=True)
    merchandise_code  = Column(String(20), nullable=False)
    department_id     = Column(
        Integer, ForeignKey("retail_department.id"), nullable=False,
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

    __tablename__ = "retail_pos_agent_credential"
    id           = Column(Integer, primary_key=True)
    store_id     = Column(Integer, ForeignKey("tenancy_store.id"), nullable=False, index=True)
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

    __tablename__ = "retail_pos_journal_file"
    id            = Column(Integer, primary_key=True)
    store_id      = Column(Integer, ForeignKey("tenancy_store.id"), nullable=False, index=True)
    filename      = Column(String(120), nullable=False)
    business_date = Column(Date, nullable=True, index=True)
    event_kind    = Column(String(16), nullable=False, default="")
    parse_error   = Column(String(255), nullable=False, default="")
    content_gz    = Column(LargeBinary, nullable=False)
    received_at   = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("store_id", "filename"),
    )


class PosItemDaySale(Base):
    """Per-item net sales for one business day (G-2 — item
    movement). Rebuilt from the staged journal originals at every
    day (re)commit, same self-healing posture as HourlySale.
    ``pos_code`` is the scan code as sold; rows exist whether or
    not the code is in the price book yet (the movement report
    joins opportunistically). Fuel lines are excluded — fuel is
    grade-level volume, not shelf movement."""

    __tablename__ = "retail_pos_item_day_sale"
    id               = Column(Integer, primary_key=True)
    store_id         = Column(Integer, ForeignKey("tenancy_store.id"), nullable=False, index=True)
    business_date    = Column(Date, nullable=False, index=True)
    pos_code         = Column(String(30), nullable=False)
    description      = Column(String(160), nullable=False, default="")
    merchandise_code = Column(String(20), nullable=False, default="")
    quantity         = Column(Float, nullable=False, default=0.0)
    amount_cents     = Column(BigInteger, nullable=False, default=0)
    __table_args__ = (
        UniqueConstraint("store_id", "business_date", "pos_code"),
    )


class PosTransaction(Base):
    """One register event, kept as its own row so an operator can
    actually look at a transaction (G-5).

    Until now a PJR file was parsed, rolled into the day's
    aggregates, and the detail discarded — the raw XML stayed in
    ``PosJournalFile`` but nothing could query it. Owners need to
    see what sold on a single ticket, and which tickets were
    refunded or voided, so events are now persisted alongside the
    aggregates they feed.

    These rows are DERIVED, never authored: every (re)commit of a
    business day rebuilds them from the staged originals, the same
    self-healing posture as ``PosItemDaySale`` and ``HourlySale``.
    ``source_file`` is what makes that idempotent — one event per
    file, so re-parsing replaces rather than duplicates.

    Deliberately NOT stored: ``TransmissionHeader``
    (StoreLocationID / VendorName / VendorModelVersion) and the
    report-period header fields. Verified constant across every
    file a live site sends, so they'd be the same value on every
    row forever; the store is already known from ``store_id``.
    """

    __tablename__ = "retail_pos_transaction"
    id            = Column(Integer, primary_key=True)
    store_id      = Column(Integer, ForeignKey("tenancy_store.id"), nullable=False, index=True)
    business_date = Column(Date, nullable=False, index=True)
    source_file   = Column(String(120), nullable=False)
    # sale | refund | void | other | financial
    kind          = Column(String(16), nullable=False, default="")
    register_id   = Column(String(20), nullable=False, default="")
    cashier_id    = Column(String(20), nullable=False, default="")
    till_id       = Column(String(20), nullable=False, default="")
    transaction_no = Column(String(30), nullable=False, default="")
    event_sequence_id = Column(String(20), nullable=False, default="")
    started_at    = Column(DateTime, nullable=True)
    ended_at      = Column(DateTime, nullable=True)
    receipt_at    = Column(DateTime, nullable=True)
    event_hour    = Column(Integer, nullable=True)
    outside       = Column(Boolean, nullable=False, default=False)
    training_mode = Column(Boolean, nullable=False, default=False)
    offline       = Column(Boolean, nullable=False, default=False)
    suspended     = Column(Boolean, nullable=False, default=False)
    gross_cents   = Column(BigInteger, nullable=False, default=0)
    net_cents     = Column(BigInteger, nullable=False, default=0)
    tax_cents     = Column(BigInteger, nullable=False, default=0)
    grand_total_cents = Column(BigInteger, nullable=False, default=0)
    # True when ANY line on the event is status="cancel" — lets the
    # list flag "has a voided item" without joining the lines.
    has_voided_line = Column(Boolean, nullable=False, default=False)
    __table_args__ = (
        UniqueConstraint("store_id", "source_file"),
    )

    lines = relationship(
        "PosTransactionLine", back_populates="transaction",
        cascade="all, delete-orphan",
    )
    tenders = relationship(
        "PosTransactionTender", back_populates="transaction",
        cascade="all, delete-orphan",
    )


class PosTransactionLine(Base):
    """One item or fuel line on a transaction.

    ``status`` carries the register's own TransactionLine status:
    ``normal`` or ``cancel``. Cancelled lines are STORED — a voided
    item is exactly what an owner wants to see — and every money
    rollup filters them out. Reading these rows for a total without
    filtering on status would inflate it.
    """

    __tablename__ = "retail_pos_transaction_line"
    id             = Column(Integer, primary_key=True)
    transaction_id = Column(
        Integer, ForeignKey("retail_pos_transaction.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    store_id       = Column(Integer, nullable=False, index=True)
    business_date  = Column(Date, nullable=False, index=True)
    line_seq       = Column(Integer, nullable=False, default=0)
    status         = Column(String(10), nullable=False, default="normal")
    pos_code       = Column(String(30), nullable=False, default="")
    pos_code_format = Column(String(20), nullable=False, default="")
    description    = Column(String(160), nullable=False, default="")
    entry_method   = Column(String(20), nullable=False, default="")
    merchandise_code = Column(String(20), nullable=False, default="")
    selling_units  = Column(String(20), nullable=False, default="")
    tax_level_id   = Column(String(20), nullable=False, default="")
    quantity       = Column(Float, nullable=False, default=0.0)
    amount_cents   = Column(BigInteger, nullable=False, default=0)
    actual_price_cents  = Column(BigInteger, nullable=False, default=0)
    regular_price_cents = Column(BigInteger, nullable=False, default=0)
    is_fuel        = Column(Boolean, nullable=False, default=False)
    fuel_grade_id  = Column(String(10), nullable=False, default="")
    fuel_position  = Column(String(10), nullable=False, default="")
    gallons        = Column(Float, nullable=False, default=0.0)

    transaction = relationship("PosTransaction", back_populates="lines")


class PosTransactionTender(Base):
    """How a transaction was paid. Change back to the customer is a
    negative row with ``is_change`` set, so summing yields net money
    taken in — the same convention the day aggregates use."""

    __tablename__ = "retail_pos_transaction_tender"
    id             = Column(Integer, primary_key=True)
    transaction_id = Column(
        Integer, ForeignKey("retail_pos_transaction.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    store_id      = Column(Integer, nullable=False, index=True)
    business_date = Column(Date, nullable=False, index=True)
    status        = Column(String(10), nullable=False, default="normal")
    code          = Column(String(30), nullable=False, default="")
    sub_code      = Column(String(30), nullable=False, default="")
    amount_cents  = Column(BigInteger, nullable=False, default=0)
    is_change     = Column(Boolean, nullable=False, default=False)

    transaction = relationship("PosTransaction", back_populates="tenders")


__all__ = [
    "PosAgentCredential", "PosItemDaySale", "PosJournalFile",
    "PosMerchandiseMap", "PosTransaction", "PosTransactionLine",
    "PosTransactionTender",
]
