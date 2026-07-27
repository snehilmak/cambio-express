"""Superadmin-issued Stripe account credits.

A superadmin can hand a store a goodwill / make-good credit from the
control panel — e.g. to compensate for downtime, a billing dispute,
or a promised discount that never made it onto an invoice. The credit
lands on the store's Stripe customer balance and is automatically
applied to the store's next invoice by Stripe.

Mechanically this is the same Stripe primitive the referral path uses
(`stripe.Customer.create_balance_transaction` with a NEGATIVE amount —
negative = credit the customer, positive = debit). The difference in
intent:

  - The referral path (``referrals.apply_pending_referral_credits``)
    is fire-and-forget inside a webhook: it swallows Stripe errors and
    still writes its lockout row so a retry can't double-credit.
  - This path is an interactive superadmin action. The operator needs
    to KNOW whether the credit actually posted, so failures surface as
    exceptions the Controller maps to HTTP status codes — nothing is
    silently swallowed.

Per CLAUDE.md invariant #9 this touches only the Stripe customer
balance; it never writes a Transfer / DailyBook / Monthly row, so
none of the money-math invariants are in play. The audit entry
(invariant #7) is the Controller's responsibility.
"""
import stripe
from sqlalchemy.orm import Session

from api.Modules.Billing.Models import Store
from api.Modules.Billing.Services.checkout import StripeServiceError
from api.Modules.Billing.Services.config import require_stripe_configured
from api.Modules.Billing.Services.portal import NoBillingCustomerError


# Guardrails on a single superadmin-issued credit. These are
# intentionally conservative — a goodwill credit is a manual, one-off
# action, not a bulk operation. A fat-fingered extra zero on a $50
# credit shouldn't be able to zero out a store's next several
# invoices, so we cap a single credit at $5,000. Raise this only with
# a deliberate reason.
MIN_CREDIT_CENTS = 1
MAX_CREDIT_CENTS = 500_000  # $5,000


class InvalidCreditAmountError(Exception):
    """The requested credit amount is outside the allowed range
    (``MIN_CREDIT_CENTS``..``MAX_CREDIT_CENTS``). Surfaced as a 422 so
    the SPA can render an inline field error."""


def issue_store_credit(
    db: Session,
    store: Store,
    amount_cents: int,
    *,
    reason: str = "",
    superadmin_username: str = "",
) -> str:
    """Post a goodwill credit to `store`'s Stripe customer balance and
    return the balance-transaction id.

    ``amount_cents`` is the POSITIVE size of the credit in cents; we
    negate it for Stripe (negative balance transaction = credit).

    Raises:
        InvalidCreditAmountError — amount outside the guardrail range.
        StripeNotConfiguredError — ``stripe.api_key`` is empty (operator
            hasn't set STRIPE_SECRET_KEY). Distinct from the generic
            StripeServiceError so the Controller can surface a clear
            "Stripe isn't configured" message.
        NoBillingCustomerError — store has no ``stripe_customer_id``;
            there's no Stripe customer to credit. The operator has to
            get the store onto a plan (which mints the customer) first.
        StripeServiceError — the Stripe SDK raised (the underlying
            exception is on ``__cause__`` for logging).

    The caller owns the transaction and the audit entry: this Service
    makes the Stripe call and returns the txn id, but does NOT commit
    or record audit — keeping the Stripe side-effect and the DB audit
    row atomic from the Controller's point of view.
    """
    if amount_cents < MIN_CREDIT_CENTS or amount_cents > MAX_CREDIT_CENTS:
        raise InvalidCreditAmountError(
            f"Credit must be between {MIN_CREDIT_CENTS} and "
            f"{MAX_CREDIT_CENTS} cents (got {amount_cents}).",
        )

    require_stripe_configured()
    if not store or not getattr(store, "stripe_customer_id", None):
        raise NoBillingCustomerError(
            "Store has no Stripe billing customer.",
        )

    # Stripe caps the description at 350 chars; keep it well under and
    # tag the actor + store so the credit is traceable from the Stripe
    # dashboard without cross-referencing our audit log.
    description = "Account credit from DineroBook"
    if reason.strip():
        description = f"{description}: {reason.strip()[:200]}"
    metadata = {
        "kind": "superadmin_credit",
        "store_id": str(getattr(store, "id", "") or ""),
    }
    if superadmin_username:
        metadata["issued_by"] = superadmin_username[:100]

    try:
        txn = stripe.Customer.create_balance_transaction(
            str(store.stripe_customer_id),
            amount=-abs(int(amount_cents)),
            currency="usd",
            description=description,
            metadata=metadata,
        )
    except stripe.error.StripeError as e:  # type: ignore[attr-defined]
        raise StripeServiceError("Stripe account credit failed") from e
    return str(getattr(txn, "id", "") or "")
