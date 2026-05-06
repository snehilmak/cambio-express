"""BankRule SQL helpers.

Operator-managed auto-categorization rules. Listed in priority order
(low priority number = matches first) — the legacy rule engine in
app.py walks them in that order and stops at the first match.
"""
from typing import Iterable

from sqlalchemy.orm import Session

from api.Modules.BankSync.Models import BankRule, StripeBankAccount


def list_rules(
    db: Session, store_ids: Iterable[int], *, enabled_only: bool = False,
) -> list[BankRule]:
    """Rules for the given stores, ordered by priority asc, then by
    id asc as tie-break (oldest rule wins when priorities collide,
    matching the legacy `/bank/rules` page render order). Pass
    `enabled_only=True` to skip disabled rules — needed by the auto-
    apply path during sync."""
    q = db.query(BankRule).filter(BankRule.store_id.in_(store_ids))
    if enabled_only:
        q = q.filter(BankRule.enabled.is_(True))
    return q.order_by(BankRule.priority.asc(), BankRule.id.asc()).all()


def get_rule_by_id(
    db: Session, rule_id: int, store_id: int,
) -> BankRule | None:
    """Scoped get-by-id. Returns `None` for cross-tenant lookups so
    callers translate to 404."""
    return (
        db.query(BankRule)
          .filter(BankRule.id == rule_id, BankRule.store_id == store_id)
          .first()
    )


def find_account_in_store(
    db: Session, account_id: int, store_id: int,
) -> StripeBankAccount | None:
    """Verify a `StripeBankAccount` belongs to a given store.
    Used by the rule editor's `account_filter_id` validation —
    cross-store account refs are rejected before the rule lands."""
    return (
        db.query(StripeBankAccount)
          .filter(
              StripeBankAccount.id == account_id,
              StripeBankAccount.store_id == store_id,
          )
          .first()
    )
