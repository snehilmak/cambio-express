"""Bank-account helpers.

`StripeBankAccount` rows hold one Stripe Financial Connections
account each. The /bank/transactions UI lists them in the account
picker; the BankTransaction.list endpoint joins on them.
"""
from typing import Iterable

from sqlalchemy.orm import Session

from api.Modules.BankSync.Models import StripeBankAccount


def list_accounts(
    db: Session, store_ids: Iterable[int],
) -> list[StripeBankAccount]:
    """All connected bank accounts for the given stores, ordered by
    account display name (StripeBankAccount.account_nickname or the
    institution-supplied name). Falls back to id when both are empty
    so output is deterministic in tests."""
    rows = (
        db.query(StripeBankAccount)
          .filter(StripeBankAccount.store_id.in_(store_ids))
          .all()
    )
    rows.sort(key=lambda a: (
        (a.nickname or a.display_name or a.institution_name or "").lower(),
        a.id,
    ))
    return rows
