"""Bank-transaction sync orchestrator.

Pulls transactions from every enabled Stripe Financial Connections
account on a store, upserts them into our cache, applies the rule
chain, and runs the historical backfill + legacy-slug migration.

Public entry points:

  - `sync_bank_transactions(db, store, since=None, until=None)`
    The full sync flow. Returns `(new_rows, total_seen, last_error)`.
    `new_rows` counts inserted rows, `total_seen` counts every row
    we touched, `last_error` is "" unless one or more accounts
    errored.

  - `upsert_bank_transaction(db, store_id, account_row, api_obj)`
    Idempotent persist of one Stripe FC Transaction. Returns
    `(row, inserted)`.

  - `backfill_uncategorized_rows(db, store_id)` — DB-side rule
    application against historical rows that fall outside
    Stripe's 7-day retroactive window.

  - `migrate_generic_bank_charge_per_account(db, store_id)`
    One-shot migration of legacy `bank_charge` rows into
    `bank_charge_<last4>`. Idempotent; once every store has been
    migrated this is a permanent no-op.

The Service uses `logging.getLogger(__name__)` instead of
`app.logger`. Caller commits — `sync_bank_transactions` commits
internally between sub-passes (per-row → backfill → migrate)
so a partial-sync crash leaves the DB in a consistent state.
"""
import logging
from datetime import datetime, timedelta

import stripe
from sqlalchemy import or_
from sqlalchemy.orm import Session

from api.Modules.BankSync.Services.applier import (
    apply_rules_to_uncategorized_row,
)
from api.Modules.BankSync.Services.builtin_rules import (
    BUILTIN_BANK_RULES,
)
from api.Modules.Billing.Services.config import stripe_is_configured
from api.Core.Clock import utc_now


logger = logging.getLogger(__name__)


# How far back to scan on a fresh sync when no `since` is provided.
# Yesterday + today only by default — minimal cost, still catches
# same-day deposits not yet entered into the daily book.
INITIAL_SYNC_DAYS_BACK = 1


def upsert_bank_transaction(
    db: Session, store_id: int, account_row, api_obj,
) -> tuple:
    """Persist (or refresh) a Stripe FC Transaction into our cache.

    Idempotent on `stripe_transaction_id`. Returns
    `(row, inserted)` where `inserted` is True iff this call
    created the row.
    """
    from api.Modules.BankSync.Models import BankTransaction

    txn_id = (
        api_obj.get("id") if isinstance(api_obj, dict)
        else api_obj.id
    )
    existing = (
        db.query(BankTransaction)
          .filter_by(stripe_transaction_id=txn_id)
          .first()
    )
    row = existing or BankTransaction(
        store_id=store_id,
        stripe_bank_account_id=account_row.id,
        stripe_transaction_id=txn_id,
        amount_cents=0,
    )
    amt = (
        api_obj.get("amount") if isinstance(api_obj, dict)
        else getattr(api_obj, "amount", 0)
    )
    cur = (
        api_obj.get("currency") if isinstance(api_obj, dict)
        else getattr(api_obj, "currency", "usd")
    )
    desc = (
        api_obj.get("description") if isinstance(api_obj, dict)
        else getattr(api_obj, "description", "")
    )
    status = (
        api_obj.get("status") if isinstance(api_obj, dict)
        else getattr(api_obj, "status", "posted")
    )
    transacted_at = (
        api_obj.get("transacted_at") if isinstance(api_obj, dict)
        else getattr(api_obj, "transacted_at", None)
    )
    try:
        row.amount_cents = int(amt or 0)
    except (TypeError, ValueError):
        row.amount_cents = 0
    row.currency = (cur or "usd").lower()
    row.description = (desc or "")[:500]
    row.status = status or "posted"
    if transacted_at:
        try:
            row.posted_at = datetime.utcfromtimestamp(
                int(transacted_at),
            )
        except (TypeError, ValueError):
            pass
    if existing is None:
        db.add(row)
    db.flush()
    return row, (existing is None)


def migrate_generic_bank_charge_per_account(
    db: Session, store_id: int,
) -> int:
    """Retag rows previously bulked into `bank_charge` by older
    account-agnostic built-ins (BELOW AVG BAL FEE, CHECK DEPOSIT
    FEE, MSB MONTHLY FEE, MONTHLY SERVICE FEE) into
    `bank_charge_<last4>` based on the account each charge hit.
    Returns the count migrated. Caller commits.

    Only retags when the description matches a current built-in
    substring — that confirms the row was auto-tagged, not a
    deliberate operator override that happened to use the
    generic slug.

    Idempotent: rows already on a per-account slug are left
    alone. Once every store has been migrated, this is a
    permanent no-op.
    """
    from api.Modules.BankSync.Models import BankTransaction, StripeBankAccount

    accounts = {
        a.id: a for a in
        db.query(StripeBankAccount).filter_by(store_id=store_id).all()
    }
    rows = (
        db.query(BankTransaction)
          .filter(
              BankTransaction.store_id == store_id,
              BankTransaction.category_slug == "bank_charge",
          )
          .all()
    )
    builtin_subs = {sub for sub, _, _ in BUILTIN_BANK_RULES}
    migrated = 0
    for row in rows:
        acct = accounts.get(row.stripe_bank_account_id)
        if not acct or not acct.last4:
            continue
        stripped = acct.last4.lstrip("0") or acct.last4
        desc = (row.description or "").upper()
        if not any(sub in desc for sub in builtin_subs):
            # Description doesn't match any current built-in —
            # treat the existing `bank_charge` tag as an operator
            # override and leave it alone.
            continue
        row.category_slug = f"bank_charge_{stripped}"
        migrated += 1
    return migrated


def backfill_uncategorized_rows(db: Session, store_id: int) -> int:
    """Run the rule chain against every uncategorised
    `BankTransaction` in the store, regardless of age. Returns
    the count newly tagged. Caller commits.

    This is what makes "I added a new built-in rule, my old
    Nizari transactions just got tagged on the next sync" work —
    without it, historical rows would stay uncategorised forever
    because Stripe won't re-yield them through `Transaction.list`.
    """
    from api.Modules.BankSync.Models import BankTransaction, StripeBankAccount

    rows = (
        db.query(BankTransaction)
          .filter(
              BankTransaction.store_id == store_id,
              or_(
                  BankTransaction.category_slug.is_(None),
                  BankTransaction.category_slug == "",
              ),
          )
          .all()
    )
    if not rows:
        return 0
    accounts = {
        a.id: a for a in
        db.query(StripeBankAccount).filter_by(store_id=store_id).all()
    }
    tagged = 0
    for row in rows:
        acct = accounts.get(row.stripe_bank_account_id)
        if apply_rules_to_uncategorized_row(
            db, row, acct, allow_auto_post=False,
        ):
            tagged += 1
    return tagged


def sync_bank_transactions(
    db: Session, store, since: datetime | None = None,
    until: datetime | None = None,
) -> tuple[int, int, str]:
    """Pull transactions from every enabled FC account on `store`.

    `since` / `until` are datetimes mapped to Stripe's
    `transacted_at[gte]` / `transacted_at[lte]` filters. When
    `since` is None, we use a rolling 7-day lookback (Stripe FC
    surfaces transactions retroactively — a transaction posted
    on May 1 may not appear in Stripe's feed until May 3 — so
    filtering strictly by `max(posted_at)` would skip late-arriving
    rows).

    Returns `(new_rows, total_seen, last_error)`:
      - `new_rows`: count of rows inserted (vs updated)
      - `total_seen`: count of every row touched
      - `last_error`: empty unless one or more accounts errored
    """
    from api.Modules.BankSync.Models import StripeBankAccount

    if not stripe_is_configured():
        return 0, 0, "Stripe is not configured."
    new_rows = 0
    total = 0
    last_error = ""
    now = utc_now()
    fallback_since = datetime.combine(
        (now - timedelta(days=INITIAL_SYNC_DAYS_BACK)).date(),
        datetime.min.time(),
    )
    accounts = (
        db.query(StripeBankAccount)
          .filter_by(store_id=store.id, enabled=True)
          .all()
    )
    for acct in accounts:
        try:
            # Idempotent self-heal: ensure this account is
            # subscribed to the transactions feature. Accounts
            # connected before the subscribe step was added won't
            # have any transactions otherwise. Stripe accepts the
            # call on already-subscribed accounts without error.
            try:
                stripe.financial_connections.Account.subscribe(
                    acct.stripe_account_id, features=["transactions"],
                )
            except stripe.error.StripeError as e:
                logger.warning(
                    "FC transactions subscribe (sync) failed for %s: %s",
                    acct.stripe_account_id, e,
                )
            # Trigger an explicit refresh so Stripe pulls fresh
            # data from the bank before we list. The refresh is
            # async — this call may return stale data, but the
            # NEXT manual sync will see whatever the bank has now.
            try:
                stripe.financial_connections.Account.refresh_account(
                    acct.stripe_account_id, features=["transactions"],
                )
            except stripe.error.StripeError as e:
                logger.warning(
                    "FC transactions refresh (sync) failed for %s: %s",
                    acct.stripe_account_id, e,
                )

            # Resolve the lower bound. Caller-provided `since` for
            # initial connect; otherwise rolling 7-day lookback.
            if since is not None:
                lo = since
            else:
                lo = max(
                    utc_now() - timedelta(days=7),
                    fallback_since,
                )
            params = {
                "account": acct.stripe_account_id,
                "limit": 100,
                "transacted_at": {"gte": int(lo.timestamp())},
            }
            if until is not None:
                params["transacted_at"]["lte"] = int(until.timestamp())
            for txn in stripe.financial_connections.Transaction.list(
                **params,
            ).auto_paging_iter():
                row, inserted = upsert_bank_transaction(
                    db, store.id, acct, txn,
                )
                if inserted:
                    new_rows += 1
                # Apply rules whenever the row is uncategorised —
                # both fresh inserts AND backfill of older rows
                # that landed before a matching rule existed.
                # auto_post is suppressed during backfill so we
                # don't surprise-post into an already-reconciled
                # daily book.
                apply_rules_to_uncategorized_row(
                    db, row, acct, allow_auto_post=inserted,
                )
                total += 1
        except stripe.error.StripeError as e:
            msg = e.user_message or str(e)
            last_error = (
                f"{acct.display_name or acct.stripe_account_id}: {msg}"
            )
            logger.warning(
                "FC txn sync failed for %s: %s",
                acct.stripe_account_id, e,
            )
        except Exception as e:
            last_error = (
                f"{acct.display_name or acct.stripe_account_id}: "
                f"{type(e).__name__}: {e}"
            )
            logger.exception(
                "FC txn sync crashed for %s",
                acct.stripe_account_id,
            )
    if total:
        db.commit()
    # DB-side backfill: catch historical uncategorised rows that
    # fall OUTSIDE Stripe's 7-day API window — those never came
    # through the loop above. Pure DB, no API call, same rule
    # chain.
    backfilled = backfill_uncategorized_rows(db, store.id)
    if backfilled:
        db.commit()
    # One-shot legacy migration: rows tagged generically as
    # `bank_charge` get split into bank_charge_<last4>. Idempotent;
    # no-op once all legacy rows have been migrated.
    migrated = migrate_generic_bank_charge_per_account(db, store.id)
    if migrated:
        db.commit()
    return new_rows, total, last_error
