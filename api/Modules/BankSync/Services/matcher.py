"""BankRule matching engine.

Two pure-ish helpers that own the "does this rule fire on this
transaction?" decision:

  - `rule_matches(rule, txn)` — pure function over field
    comparisons. No DB. Works against transient (un-persisted)
    rule rows because SQLAlchemy column defaults only fire on
    insert: `rule.enabled` is None on a freshly-constructed
    rule, treated as True so the operator can preview a match
    before saving.

  - `find_matching_rule(db, store_id, txn)` — first enabled rule
    (lowest priority first) that matches `txn`. None when nothing
    applies.

Match conditions on `BankRule`:
  - description: regex (case-insensitive) / contains / starts_with
    / equals (lowercase comparisons for the non-regex variants).
    Invalid regex → no-match (avoid blowing up the sync).
  - sign filter: credit (amount > 0) / debit (amount <= 0).
  - amount range: min/max as absolute cents.
  - account filter: optional `stripe_bank_account_id` pin.

Conditions left unset are treated as "any" — the rule still
fires on a transaction that doesn't pin them.
"""
import re
from typing import Any

from sqlalchemy.orm import Session


def rule_matches(rule: Any, txn: Any) -> bool:
    """Pure predicate: does `rule` fire on `txn`?

    Disabled rules (`rule.enabled is False`) never match.
    `enabled is None` on a transient row counts as True so
    operators can preview matches before saving.
    """
    if rule.enabled is False:
        return False

    # Description match.
    if rule.desc_match_type and rule.desc_match_value:
        desc = (txn.description or "")
        val = rule.desc_match_value
        mt = rule.desc_match_type
        if mt == "regex":
            try:
                if not re.search(val, desc, re.IGNORECASE):
                    return False
            except re.error:
                # Bad regex — refuse to match rather than crash
                # the sync.
                return False
        else:
            d = desc.lower()
            v = val.lower()
            if mt == "contains" and v not in d:
                return False
            if mt == "starts_with" and not d.startswith(v):
                return False
            if mt == "equals" and d != v:
                return False

    # Sign filter — debit at or below zero, credit above.
    if rule.sign_filter == "credit" and (txn.amount_cents or 0) < 0:
        return False
    if rule.sign_filter == "debit" and (txn.amount_cents or 0) >= 0:
        return False

    # Amount range — both bounds use absolute cents so a -210 cent
    # debit checks against |amount|=210.
    abs_cents = abs(txn.amount_cents or 0)
    if (
        rule.amount_min_cents is not None
        and abs_cents < rule.amount_min_cents
    ):
        return False
    if (
        rule.amount_max_cents is not None
        and abs_cents > rule.amount_max_cents
    ):
        return False

    # Account filter — pin the rule to one connected account.
    if (
        rule.account_filter_id
        and rule.account_filter_id != txn.stripe_bank_account_id
    ):
        return False

    return True


def find_matching_rule(db: Session, store_id: int, txn: Any) -> Any:
    """First enabled rule (lowest priority first) that matches
    `txn` for the given store. None when no rule applies.

    Tie-break on `id` so the order is deterministic when two
    rules share a priority.
    """
    from api.Modules.BankSync.Models import BankRule
    rules = (
        db.query(BankRule)
          .filter_by(store_id=store_id, enabled=True)
          .order_by(BankRule.priority.asc(), BankRule.id.asc())
          .all()
    )
    for rule in rules:
        if rule_matches(rule, txn):
            return rule
    return None
