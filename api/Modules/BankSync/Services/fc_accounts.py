"""Stripe Financial Connections account cache.

Two helpers that own the `StripeBankAccount` row lifecycle:

  - `upsert_fc_account(db, store_id, api_obj)`
    Idempotently persist a Stripe FC `Account` payload into our
    cache. Handles both dict-shaped responses (raw API JSON) and
    object-shaped responses (SDK objects). Captures balance
    metadata when present.

  - `refresh_bank_balances(db, store)`
    Pull fresh balances for every enabled account on the store
    via `Account.refresh_account(features=["balance"])` followed
    by `Account.retrieve`. Returns
    `(updated_count, error_message_or_empty)` so the caller can
    surface the error in a flash.

The Service uses `logging.getLogger(__name__)` instead of
`app.logger` so it's callable from any context.
"""
import logging
from datetime import datetime

import stripe
from sqlalchemy.orm import Session

from api.Modules.Billing.Services.config import stripe_is_configured


logger = logging.getLogger(__name__)


def _read(api_obj, key: str, default=None):
    """Read a field off an SDK object OR a dict response.

    Stripe SDKs sometimes return raw dicts (when caller used
    `.list(...)` for example) and sometimes return objects.
    Normalize the access here.
    """
    if isinstance(api_obj, dict):
        return api_obj.get(key, default)
    return getattr(api_obj, key, default)


def upsert_fc_account(db: Session, store_id: int, api_obj):
    """Persist (or refresh) a Stripe FC `Account` into our cache.

    Idempotent on `stripe_account_id`. Returns the row.

    Field-merge contract: every cached field uses the new API
    value when present, otherwise falls back to the prior cached
    value. Net effect: if Stripe drops a field on a subsequent
    fetch (rare, usually permission-related), we keep what we
    last knew rather than blanking the row.

    Balance fields are extracted out of the `balance` sub-object
    when present:
      - `current` is a `{"usd": <cents>}` dict; we pick the
        currency matching the account's, falling back to the
        first value.
      - `as_of` is a unix timestamp.
    """
    from api.Modules.BankSync.Models import StripeBankAccount

    acct_id = _read(api_obj, "id")
    existing = (
        db.query(StripeBankAccount)
          .filter_by(stripe_account_id=acct_id)
          .first()
    )
    row = existing or StripeBankAccount(
        store_id=store_id, stripe_account_id=acct_id,
    )
    institution = _read(api_obj, "institution_name", "")
    display     = _read(api_obj, "display_name", "")
    last4       = _read(api_obj, "last4", "")
    category    = _read(api_obj, "category", "")
    subcategory = _read(api_obj, "subcategory", "")

    row.institution_name = institution or row.institution_name or ""
    row.display_name     = display or row.display_name or ""
    row.last4            = last4 or row.last4 or ""
    row.category         = category or row.category or ""
    row.subcategory      = subcategory or row.subcategory or ""

    # Balance payload lives inside the "balance" sub-object;
    # may be missing if the "balances" permission wasn't granted,
    # or null if Stripe's async balance fetch hasn't completed
    # yet (common right after connect when prefetch wasn't
    # requested).
    bal = _read(api_obj, "balance")
    if bal:
        current = _read(bal, "current")
        as_of = _read(bal, "as_of")
        # Stripe returns balances as a dict {"usd": <cents>};
        # pick whatever matches the account currency, falling
        # back to the first value. Guard against
        # missing/empty `current`.
        cents = 0
        if isinstance(current, dict) and current:
            cents = (
                current.get(row.currency or "usd")
                or next(iter(current.values()), 0)
            )
        elif current is not None:
            cents = current
        try:
            row.last_balance_cents = int(cents or 0)
        except (TypeError, ValueError):
            row.last_balance_cents = 0
        if as_of:
            try:
                row.last_balance_as_of = datetime.utcfromtimestamp(
                    int(as_of),
                )
            except (TypeError, ValueError):
                pass

    row.enabled = True
    row.disconnected_at = None
    if existing is None:
        db.add(row)
    db.flush()
    return row


def refresh_bank_balances(db: Session, store) -> tuple[int, str]:
    """Pull fresh balances for every enabled account on `store`.

    Stripe requires the `balances` feature to be refreshed
    explicitly when the cached value is stale; we call
    `Account.refresh_account(features=["balance"])` and then
    `retrieve` to capture the new snapshot.

    Returns `(updated_count, error_message_or_empty)`. The
    caller can surface `error_message` in a flash so the operator
    sees *why* a refresh failed without grepping the server log.
    """
    from api.Modules.BankSync.Models import StripeBankAccount

    if not stripe_is_configured():
        return 0, "Stripe is not configured."
    updated = 0
    last_error = ""
    accounts = (
        db.query(StripeBankAccount)
          .filter_by(store_id=store.id, enabled=True)
          .all()
    )
    for acct in accounts:
        try:
            # SDK note: the operation is `refresh_account` (not
            # `refresh`). `refresh` is the inherited APIResource
            # instance method that only re-fetches local state;
            # calling it with kwargs raises "got an unexpected
            # keyword argument 'features'".
            stripe.financial_connections.Account.refresh_account(
                acct.stripe_account_id, features=["balance"],
            )
            api_obj = stripe.financial_connections.Account.retrieve(
                acct.stripe_account_id,
            )
            upsert_fc_account(db, store.id, api_obj)
            updated += 1
        except stripe.error.StripeError as e:
            msg = e.user_message or str(e)
            last_error = (
                f"{acct.display_name or acct.stripe_account_id}: {msg}"
            )
            logger.warning(
                "FC refresh failed for %s: %s",
                acct.stripe_account_id, e,
            )
        except Exception as e:
            # Anything not a StripeError — usually a response-shape
            # mismatch in upsert_fc_account or a network blip.
            # Logged with full traceback so the cause is visible.
            last_error = (
                f"{acct.display_name or acct.stripe_account_id}: "
                f"{type(e).__name__}: {e}"
            )
            logger.exception(
                "FC refresh crashed for %s",
                acct.stripe_account_id,
            )
    if updated:
        db.commit()
    return updated, last_error
