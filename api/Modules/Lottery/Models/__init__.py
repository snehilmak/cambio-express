"""Lottery — Models.

The c-store lottery workflow (P1-6, HANDOFF.md §2 — the wedge
feature). Three tables mirror how scratch-off lottery actually
runs at a counter:

* ``LotteryGame``     — one row per game the store sells ($1 / $5 /
                        $20 scratchers…): state game number, ticket
                        price, tickets per pack.
* ``LotteryPack``     — one physical pack of tickets through its
                        lifecycle: received → active (in a display
                        bin, selling) → settled (sold out /
                        deactivated) or returned (sent back to the
                        state).
* ``LotteryDayCount`` — the day-close count for one active pack:
                        the next-to-sell ticket number at close.
                        Tickets sold that day = today's count minus
                        the previous reference (yesterday's count,
                        or the pack's opening ticket on its first
                        counted day).

Ticket numbering v1 assumes ASCENDING sell order (packs print
000..N-1 and sell upward — the common Texas layout). A per-game
direction flag can be added later without schema change to the
counts themselves.

Money is integer cents from day one (P0-3 convention) — no Float
columns in this module, ever.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Integer,
    String, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from api.Core.Database import Base
from api.Core.Money import DollarView


# Pack lifecycle. Not a DB enum so a future state ("stolen",
# "damaged") lands without a migration.
PACK_STATUSES = ("received", "active", "settled", "returned")


class LotteryGame(Base):
    __tablename__ = "retail_lottery_game"
    id                 = Column(Integer, primary_key=True)
    store_id           = Column(Integer, ForeignKey("tenancy_store.id"), nullable=False, index=True)
    # The state's game number as printed on the pack — the key the
    # operator actually knows ("game 2417").
    game_number        = Column(String(20), nullable=False)
    name               = Column(String(120), nullable=False)
    ticket_price_cents = Column(BigInteger, nullable=False, default=0)
    ticket_price       = DollarView("ticket_price_cents")
    tickets_per_pack   = Column(Integer, nullable=False, default=0)
    # Deactivate instead of delete when the state retires a game —
    # historical packs/counts keep their FK.
    is_active          = Column(Boolean, default=True, nullable=False)
    created_at         = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("store_id", "game_number"),)

    packs = relationship("LotteryPack", backref="game")


class LotteryPack(Base):
    __tablename__ = "retail_lottery_pack"
    id           = Column(Integer, primary_key=True)
    store_id     = Column(Integer, ForeignKey("tenancy_store.id"), nullable=False, index=True)
    game_id      = Column(Integer, ForeignKey("retail_lottery_game.id"), nullable=False, index=True)
    # The pack number printed on the pack — unique per game per store.
    pack_number  = Column(String(40), nullable=False)
    status       = Column(String(16), nullable=False, default="received")
    # Display slot / bin where the pack sells from ("3", "12B") —
    # free-form, purely for the operator's orientation.
    bin_number   = Column(String(10), default="")
    received_on  = Column(Date, nullable=True)
    activated_on = Column(Date, nullable=True)
    settled_on   = Column(Date, nullable=True)
    # First sellable ticket number when the pack went on sale — the
    # baseline for the first day's sold-count delta. 0 for a fresh
    # pack; non-zero when a partially-sold pack moves stores/bins.
    opening_ticket = Column(Integer, nullable=False, default=0)
    created_by   = Column(Integer, ForeignKey("tenancy_user.id"), nullable=True)
    created_at   = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("store_id", "game_id", "pack_number"),)

    counts = relationship(
        "LotteryDayCount", backref="pack",
        cascade="all, delete-orphan",
        order_by="LotteryDayCount.report_date",
    )


class LotteryDayCount(Base):
    """One pack's day-close count: ``closing_ticket`` is the
    next-to-sell ticket number when the day ended. One row per
    (store, date, pack) — re-submitting the same day's count
    updates in place rather than stacking rows."""

    __tablename__ = "retail_lottery_day_count"
    id             = Column(Integer, primary_key=True)
    store_id       = Column(Integer, ForeignKey("tenancy_store.id"), nullable=False, index=True)
    report_date    = Column(Date, nullable=False)
    pack_id        = Column(Integer, ForeignKey("retail_lottery_pack.id"), nullable=False, index=True)
    closing_ticket = Column(Integer, nullable=False)
    created_by     = Column(Integer, ForeignKey("tenancy_user.id"), nullable=True)
    created_at     = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("store_id", "report_date", "pack_id"),
    )


__all__ = [
    "PACK_STATUSES", "LotteryDayCount", "LotteryGame", "LotteryPack",
]
