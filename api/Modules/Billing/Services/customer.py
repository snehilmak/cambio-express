"""Stripe billing-customer lifecycle.

`ensure_stripe_customer(db, store)` returns a Stripe customer ID
for a store, minting one on first use and self-healing when the
cached ID points at a customer in a different Stripe mode (e.g.
after a test→live migration).

Stripe FC requires an `account_holder={"type":"customer", ...}`
on every Financial Connections session — so even trial / inactive
stores that haven't paid yet need a customer record to link a
bank account. The "no charge until subscribe" model still uses a
customer object for FC linking and balance-credit retention.

Commits the session itself when minting a new customer — the FC
connect flow needs the new ID to persist immediately so the
subsequent FC.Session.create has it.
"""
import logging

import stripe
from sqlalchemy.orm import Session

from api.Modules.Billing.Models import Store


logger = logging.getLogger(__name__)


def ensure_stripe_customer(db: Session, store: Store) -> str:
    """Return a Stripe customer id for `store`, creating one if needed.

    Lookup priority:
      1. cached `store.stripe_customer_id` — if `Customer.retrieve`
         succeeds we trust it and return.
      2. on `"No such customer"` / `"resource_missing"` we clear
         the cache and mint fresh — that's the test→live
         self-heal.
      3. on any other Stripe error during retrieve, propagate so
         the caller (typically the FC connect endpoint) can
         surface a real failure.
      4. on mint, persist the new customer ID via `db.commit()`
         and return.

    Customer retrieves are not metered, so the verify-then-use
    cost is effectively zero per connect attempt.
    """
    if store.stripe_customer_id:
        try:
            stripe.Customer.retrieve(store.stripe_customer_id)
            return store.stripe_customer_id
        except stripe.error.InvalidRequestError as e:
            msg = str(e)
            if "No such customer" in msg or "resource_missing" in msg:
                logger.warning(
                    "Stripe customer %s not found in current mode "
                    "for store %s; minting fresh.",
                    store.stripe_customer_id, store.id,
                )
                store.stripe_customer_id = ""
            else:
                raise

    try:
        cust = stripe.Customer.create(
            email=(store.email or None),
            name=store.name,
            metadata={"store_id": str(store.id)},
        )
    except stripe.error.StripeError as e:
        logger.error(
            "Stripe customer create failed for store %s: %s",
            store.id, e,
        )
        raise

    store.stripe_customer_id = cust.id
    db.commit()
    return cust.id
