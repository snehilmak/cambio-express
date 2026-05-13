"""Bank-rule audit-log report aggregator.

Groups `BankTransaction` rows that were auto-categorised by an
operator-defined `BankRule` (matched_rule_id IS NOT NULL) in
the period, counting per-rule firings + total absolute amount.

Manual operator overrides (matched_rule_id IS NULL even if
categorised) and platform-built-in rule matches (also no
matched_rule_id) are NOT counted — this is specifically for
auditing operator-managed rules.

Pure DB read — no commits, no side-effects.
"""
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session


def bank_rule_audit(
    db: Session,
    store_ids: list[int],
    d_from: date,
    d_to: date,
) -> tuple[list[dict], dict]:
    """Aggregate BankTransaction rows by `matched_rule_id`.

    Returns `(rows, totals)`:
      - rows: per-rule dicts with `rule_id`, `label`, `target`
        (operator-friendly category), `match` (description
        condition summary), `count`, `amount`. Rules deleted
        since the matches were created render as
        `"Rule #<id> (deleted)"`. Sorted by count desc.
      - totals: `count`, `amount`, `rules` (distinct rule count).
    """
    from api.Modules.BankSync.Models import BankRule, BankTransaction
    from api.Modules.BankSync.Services import bank_category_label
    from api.Modules.Reports.Services.date_helpers import (
        day_end, day_start,
    )

    month_start = day_start(d_from)
    month_end   = day_end(d_to)
    rows_q = (
        db.query(
            BankTransaction.matched_rule_id,
            func.count(BankTransaction.id),
            func.coalesce(func.sum(BankTransaction.amount_cents), 0),
        )
        .filter(
            BankTransaction.store_id.in_(store_ids),
            BankTransaction.matched_rule_id.isnot(None),
            BankTransaction.posted_at >= month_start,
            BankTransaction.posted_at <= month_end,
        )
        .group_by(BankTransaction.matched_rule_id)
        .all()
    )
    rule_ids = [rid for rid, *_ in rows_q]
    rules = (
        {
            r.id: r
            for r in db.query(BankRule).filter(BankRule.id.in_(rule_ids)).all()
        }
        if rule_ids else {}
    )

    rows: list[dict] = []
    for rid, count, cents in rows_q:
        rule = rules.get(rid)
        if rule is None:
            label  = f"Rule #{rid} (deleted)"
            target = ""
            match  = ""
        else:
            label  = f"Rule #{rule.id}"
            target = bank_category_label(rule.target_kind or "")
            match  = (
                f'{rule.desc_match_type or "any"}: '
                f'"{rule.desc_match_value or ""}"'
            ).strip(": ")
        rows.append({
            "rule_id": rid,
            "label":   label,
            "target":  target,
            "match":   match,
            "count":   int(count or 0),
            "amount":  abs(float(cents or 0)) / 100.0,
        })
    rows.sort(key=lambda r: r["count"], reverse=True)

    totals = {
        "count":  sum(r["count"]  for r in rows),
        "amount": sum(r["amount"] for r in rows),
        "rules":  len(rows),
    }
    return rows, totals
