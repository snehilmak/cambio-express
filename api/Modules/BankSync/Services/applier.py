"""Bank-rule application orchestrator.

Runs the full rule chain (operator `BankRule` → platform-managed
built-in) against an uncategorised bank transaction and tags it.

Sits one layer above the matcher + categorize Services:

  matcher.find_matching_rule    → operator BankRule lookup
  builtin_rules.match_builtin_  → platform built-in lookup
  categorize.categorize_        → write the slug + maybe post
                                   a DailyLineItem

`apply_rules_to_uncategorized_row` is idempotent — rows that
already have a `category_slug` are left untouched so operator
overrides survive a re-sync.

`allow_auto_post` controls whether a matched operator rule with
`auto_post=True` also creates a `DailyLineItem`:
  - `True`  for freshly-inserted rows (operator's expressed
            intent on new data).
  - `False` when backfilling historical rows (the daily book
            may already be reconciled — let the operator post
            manually).

Built-in rules NEVER post to the daily book regardless — the
`post_to_daily=False` is hard-coded for them per CLAUDE.md.

Caller commits.
"""
from typing import Any

from sqlalchemy.orm import Session

from api.Modules.BankSync.Services.builtin_rules import (
    match_builtin_bank_rule,
)
from api.Modules.BankSync.Services.categorize import (
    categorize_transaction,
)
from api.Modules.BankSync.Services.categories import (
    is_daily_book_kind,
)
from api.Modules.BankSync.Services.matcher import find_matching_rule


def apply_rules_to_uncategorized_row(
    db: Session, row: Any, account: Any, *, allow_auto_post: bool,
) -> bool:
    """Apply the rule chain to `row`. Returns True iff the row
    was tagged.

    Order matters:
      1. Operator BankRule chain (lowest priority first). If a
         rule matches, tag the row + maybe post a DailyLineItem
         when `auto_post AND allow_auto_post`.
      2. Built-in (platform-managed) rule chain. If a built-in
         matches, tag the row WITHOUT posting to the daily book.
      3. Otherwise leave the row uncategorised.
    """
    if row.category_slug:
        return False

    rule = find_matching_rule(db, row.store_id, row)
    if rule is not None:
        categorize_transaction(
            db, row, rule.target_kind,
            rule=rule,
            post_to_daily=(rule.auto_post and allow_auto_post),
            is_daily_book_kind=is_daily_book_kind,
        )
        return True

    builtin = match_builtin_bank_rule(row, account)
    if builtin:
        categorize_transaction(
            db, row, builtin,
            rule=None,
            post_to_daily=False,
            is_daily_book_kind=is_daily_book_kind,
        )
        return True

    return False
