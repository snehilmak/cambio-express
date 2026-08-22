"""Lottery — Services.

Business rules for the lottery workflow. All money in integer
cents (P0-3); all writes leave commit to the Controller so the
audit row lands in the same transaction (CLAUDE.md invariant #7
pattern).

The core arithmetic — the reason this module exists — is the
day-close sold-count:

    sold(pack, day) = closing_ticket(day) − previous_reference
    previous_reference = the most recent EARLIER count for the
                         pack, else pack.opening_ticket
    value_cents(pack, day) = sold × game.ticket_price_cents

Ascending sell-order v1 (see Models docstring).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from api.Modules.Lottery.Models import (
    LotteryDayCount,
    LotteryGame,
    LotteryPack,
    PACK_STATUSES,
)


class LotteryError(Exception):
    """Base for lottery domain errors — Controllers map to 4xx."""


class LotteryNotFoundError(LotteryError):
    pass


class LotteryStateError(LotteryError):
    """Illegal lifecycle transition or count (message is user-safe)."""


# ── Games ──────────────────────────────────────────────────


def list_games(
    db: Session, store_id: int, include_inactive: bool = False,
) -> list[LotteryGame]:
    q = db.query(LotteryGame).filter_by(store_id=store_id)
    if not include_inactive:
        q = q.filter(LotteryGame.is_active == True)  # noqa: E712
    return q.order_by(LotteryGame.game_number).all()


def create_game(
    db: Session, store_id: int, *, game_number: str, name: str,
    ticket_price: float, tickets_per_pack: int,
) -> LotteryGame:
    dup = (
        db.query(LotteryGame)
        .filter_by(store_id=store_id, game_number=game_number)
        .first()
    )
    if dup is not None:
        raise LotteryStateError(
            f"Game #{game_number} already exists for this store.",
        )
    game = LotteryGame(
        store_id=store_id, game_number=game_number, name=name,
        ticket_price=ticket_price, tickets_per_pack=tickets_per_pack,
    )
    db.add(game)
    db.flush()
    return game


def update_game(
    db: Session, store_id: int, game_id: int, *, name: str | None = None,
    ticket_price: float | None = None, tickets_per_pack: int | None = None,
    is_active: bool | None = None,
) -> LotteryGame:
    game = db.get(LotteryGame, game_id)
    if game is None or game.store_id != store_id:
        raise LotteryNotFoundError("Game not found")
    if name is not None:
        game.name = name
    if ticket_price is not None:
        game.ticket_price = ticket_price
    if tickets_per_pack is not None:
        game.tickets_per_pack = tickets_per_pack
    if is_active is not None:
        game.is_active = bool(is_active)
    db.flush()
    return game


# ── Packs ──────────────────────────────────────────────────


def list_packs(
    db: Session, store_id: int, status: str | None = None,
) -> list[LotteryPack]:
    q = db.query(LotteryPack).filter_by(store_id=store_id)
    if status:
        q = q.filter(LotteryPack.status == status)
    return q.order_by(LotteryPack.status, LotteryPack.created_at).all()


def receive_pack(
    db: Session, store_id: int, *, game_id: int, pack_number: str,
    received_on: date, created_by: int | None,
) -> LotteryPack:
    game = db.get(LotteryGame, game_id)
    if game is None or game.store_id != store_id:
        raise LotteryNotFoundError("Game not found")
    dup = (
        db.query(LotteryPack)
        .filter_by(store_id=store_id, game_id=game_id, pack_number=pack_number)
        .first()
    )
    if dup is not None:
        raise LotteryStateError(
            f"Pack {pack_number} of game #{game.game_number} is already logged.",
        )
    pack = LotteryPack(
        store_id=store_id, game_id=game_id, pack_number=pack_number,
        status="received", received_on=received_on, created_by=created_by,
    )
    db.add(pack)
    db.flush()
    return pack


def _load_pack(db: Session, store_id: int, pack_id: int) -> LotteryPack:
    pack = db.get(LotteryPack, pack_id)
    if pack is None or pack.store_id != store_id:
        raise LotteryNotFoundError("Pack not found")
    return pack


def activate_pack(
    db: Session, store_id: int, pack_id: int, *,
    activated_on: date, opening_ticket: int = 0, bin_number: str = "",
) -> LotteryPack:
    pack = _load_pack(db, store_id, pack_id)
    if pack.status not in ("received",):
        raise LotteryStateError(
            f"Only a received pack can be activated (this one is {pack.status}).",
        )
    if opening_ticket < 0:
        raise LotteryStateError("Opening ticket cannot be negative.")
    tickets_per_pack = int(pack.game.tickets_per_pack or 0)
    if tickets_per_pack and opening_ticket >= tickets_per_pack:
        raise LotteryStateError(
            "Opening ticket is past the end of the pack "
            f"({tickets_per_pack} tickets).",
        )
    pack.status = "active"
    pack.activated_on = activated_on
    pack.opening_ticket = int(opening_ticket)
    pack.bin_number = bin_number or ""
    db.flush()
    return pack


def settle_pack(
    db: Session, store_id: int, pack_id: int, *, settled_on: date,
) -> LotteryPack:
    pack = _load_pack(db, store_id, pack_id)
    if pack.status != "active":
        raise LotteryStateError(
            f"Only an active pack can be settled (this one is {pack.status}).",
        )
    pack.status = "settled"
    pack.settled_on = settled_on
    db.flush()
    return pack


def return_pack(
    db: Session, store_id: int, pack_id: int, *, returned_on: date,
) -> LotteryPack:
    pack = _load_pack(db, store_id, pack_id)
    if pack.status not in ("received", "active"):
        raise LotteryStateError(
            f"A {pack.status} pack cannot be returned to the state.",
        )
    pack.status = "returned"
    pack.settled_on = returned_on
    db.flush()
    return pack


# ── Day counts ─────────────────────────────────────────────


def previous_reference(
    db: Session, pack: LotteryPack, day: date,
) -> int:
    """The baseline the day's sold-count is measured against: the
    most recent count STRICTLY BEFORE ``day``, else the pack's
    opening ticket."""
    prev = (
        db.query(LotteryDayCount)
        .filter(
            LotteryDayCount.pack_id == pack.id,
            LotteryDayCount.report_date < day,
        )
        .order_by(LotteryDayCount.report_date.desc())
        .first()
    )
    if prev is not None:
        return int(prev.closing_ticket)
    return int(pack.opening_ticket or 0)


def record_day_count(
    db: Session, store_id: int, *, pack_id: int, day: date,
    closing_ticket: int, created_by: int | None,
) -> LotteryDayCount:
    """Upsert the (store, date, pack) count with validation:

    * pack must be active,
    * the count can't go backwards vs the previous reference,
    * the count can't exceed the pack size,
    * a LATER count for the pack must not become inconsistent
      (recording history out of order below an existing later
      count is rejected).
    """
    pack = _load_pack(db, store_id, pack_id)
    if pack.status != "active":
        raise LotteryStateError(
            f"Counts can only be recorded for active packs (this one is {pack.status}).",
        )
    if closing_ticket < 0:
        raise LotteryStateError("Ticket count cannot be negative.")
    ref = previous_reference(db, pack, day)
    if closing_ticket < ref:
        raise LotteryStateError(
            f"Count {closing_ticket} is below the previous count ({ref}) — "
            "ticket numbers only move forward.",
        )
    tickets_per_pack = int(pack.game.tickets_per_pack or 0)
    if tickets_per_pack and closing_ticket > tickets_per_pack:
        raise LotteryStateError(
            f"Count {closing_ticket} is past the end of the pack "
            f"({tickets_per_pack} tickets).",
        )
    nxt = (
        db.query(LotteryDayCount)
        .filter(
            LotteryDayCount.pack_id == pack.id,
            LotteryDayCount.report_date > day,
        )
        .order_by(LotteryDayCount.report_date.asc())
        .first()
    )
    if nxt is not None and closing_ticket > int(nxt.closing_ticket):
        raise LotteryStateError(
            f"Count {closing_ticket} exceeds the later count already "
            f"recorded on {nxt.report_date.isoformat()} ({nxt.closing_ticket}).",
        )

    row = (
        db.query(LotteryDayCount)
        .filter_by(store_id=store_id, report_date=day, pack_id=pack.id)
        .first()
    )
    if row is None:
        row = LotteryDayCount(
            store_id=store_id, report_date=day, pack_id=pack.id,
            closing_ticket=int(closing_ticket), created_by=created_by,
        )
        db.add(row)
    else:
        row.closing_ticket = int(closing_ticket)
        row.created_by = created_by
    db.flush()
    return row


@dataclass
class PackDaySummary:
    pack: LotteryPack
    counted: bool
    closing_ticket: int | None
    sold: int
    value_cents: int


@dataclass
class DaySummary:
    rows: list[PackDaySummary]
    total_sold: int
    total_value_cents: int
    uncounted_active_packs: int


def day_summary(db: Session, store_id: int, day: date) -> DaySummary:
    """Per-pack sold counts + dollar value for one day, across every
    pack that was active that day OR has a count recorded for it.
    Packs missing a count surface with ``counted=False`` so the UI
    can nag — an uncounted active pack is the #1 shrinkage blind
    spot in a c-store."""
    counts = {
        c.pack_id: c
        for c in db.query(LotteryDayCount)
        .filter_by(store_id=store_id, report_date=day)
        .all()
    }
    active = (
        db.query(LotteryPack)
        .filter_by(store_id=store_id, status="active")
        .all()
    )
    pack_ids = {p.id for p in active} | set(counts.keys())
    packs = (
        db.query(LotteryPack)
        .filter(LotteryPack.id.in_(pack_ids))
        .all()
        if pack_ids else []
    )

    rows: list[PackDaySummary] = []
    total_sold = 0
    total_value = 0
    uncounted = 0
    for pack in sorted(packs, key=lambda p: (p.bin_number or "", p.id)):
        count = counts.get(pack.id)
        if count is None:
            uncounted += 1
            rows.append(PackDaySummary(
                pack=pack, counted=False, closing_ticket=None,
                sold=0, value_cents=0,
            ))
            continue
        ref = previous_reference(db, pack, day)
        sold = max(0, int(count.closing_ticket) - ref)
        value = sold * int(pack.game.ticket_price_cents or 0)
        total_sold += sold
        total_value += value
        rows.append(PackDaySummary(
            pack=pack, counted=True,
            closing_ticket=int(count.closing_ticket),
            sold=sold, value_cents=value,
        ))
    return DaySummary(
        rows=rows, total_sold=total_sold,
        total_value_cents=total_value,
        uncounted_active_packs=uncounted,
    )


__all__ = [
    "DaySummary", "LotteryError", "LotteryNotFoundError",
    "LotteryStateError", "PackDaySummary", "PACK_STATUSES",
    "activate_pack", "create_game", "day_summary", "list_games",
    "list_packs", "previous_reference", "receive_pack",
    "record_day_count", "return_pack", "settle_pack", "update_game",
]
