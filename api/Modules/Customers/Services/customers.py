"""Customer service layer — upsert and autocomplete search.

Two behaviors composed over the SQL helpers in
``Repositories/customers.py``:

  - ``upsert`` — create-or-update used by the transfer form's
    sender block + the dedicated /upsert endpoint.
  - ``search`` — autocomplete for the sender autocomplete.

Both are scoped to the OWNER UMBRELLA — sibling stores under the
same Owner share customers; unrelated stores are isolated. The
Repository's ``sibling_store_ids`` is the single chokepoint that
controls that scope.
"""
from datetime import datetime
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from api.Modules.Customers.Models import Customer
from api.Modules.Customers.Repositories import (
    find_by_id_in_stores,
    find_by_phone_in_stores,
    recent_customers,
    search_by_substring,
    sibling_store_ids,
)


# Threshold tuned in the original Flask implementation: catches
# "Gonzales/Gonzalez" and other common spelling drift, but rejects
# unrelated names. Don't change without re-evaluating against real
# customer-directory data.
_FUZZY_MATCH_RATIO_THRESHOLD = 0.72

# Min characters before we run the fuzzy-suggestion pass. SequenceMatcher
# on short queries returns too many false positives.
_FUZZY_MIN_QUERY_LEN = 4

# Cap the suggestion list so the picker doesn't drown the cashier.
_FUZZY_MAX_SUGGESTIONS = 3

# Precomputing fuzzy candidates from the most-recent N customers keeps
# SequenceMatcher off the full directory on every keystroke. ~0.5ms
# at 200 names — well under the autocomplete debounce window.
_FUZZY_CANDIDATE_POOL = 200

# When matches already filled this many slots, skip the fuzzy pass
# entirely — the cashier has plenty to pick from already.
_FUZZY_SKIP_IF_MATCHES_GE = 5


def upsert(
    db: Session, store_id: int, full_name: str,
    phone_country: str, phone_number: str,
    *, address: str = "", dob=None, customer_id: int | None = None,
) -> Customer:
    """Return the Customer row for this sender, creating / updating as needed.

    Lookup priority (matches `app.py::find_or_upsert_customer`):
      1. explicit `customer_id` — accepted only if the target lives
         in the owner umbrella;
      2. `(phone_country, phone_number)` across the umbrella — repeat
         senders get one row per person per owner, not per store;
      3. otherwise create a new row pinned to `store_id`.

    Last write wins on every non-empty field — newest values overwrite,
    so the customer record always tracks the latest info anywhere in
    the owner's portfolio.
    """
    siblings = sibling_store_ids(db, store_id)

    cust: Customer | None = None
    if customer_id:
        cust = find_by_id_in_stores(db, customer_id, siblings)
    if cust is None and phone_number:
        cust = find_by_phone_in_stores(
            db, siblings, phone_country, phone_number,
        )
    if cust is None:
        cust = Customer(
            store_id=store_id, full_name=full_name or "",
            phone_country=(phone_country or "+1"),
            phone_number=phone_number or "",
        )
        db.add(cust)
    if full_name:     cust.full_name     = full_name
    if address:       cust.address       = address
    if dob:           cust.dob           = dob
    if phone_country: cust.phone_country = phone_country
    if phone_number:  cust.phone_number  = phone_number
    cust.updated_at = datetime.utcnow()
    db.flush()
    return cust


def search(
    db: Session, store_id: int, q: str,
) -> tuple[list[Customer], list[Customer]]:
    """Autocomplete search across the owner umbrella.

    Returns `(matches, suggestions)` — exact substring matches on
    `full_name` or `phone_number` first, then fuzzy near-misses
    (different list so the UI can label "Did you mean…?"). Empty
    queries and queries shorter than 2 chars return `([], [])`.

    The fuzzy pass only fires when:
      * query is at least 4 characters (shorter queries produce too
        many false positives in SequenceMatcher);
      * the exact-match list has fewer than 5 rows (otherwise the
        cashier already has plenty to pick from).
    """
    q_text = q.strip()
    if len(q_text) < 2:
        return [], []

    siblings = sibling_store_ids(db, store_id)

    matches = search_by_substring(db, siblings, q_text, limit=10)
    matched_ids = {c.id for c in matches}

    suggestions: list[Customer] = []
    if (
        len(q_text) >= _FUZZY_MIN_QUERY_LEN
        and len(matches) < _FUZZY_SKIP_IF_MATCHES_GE
    ):
        candidates = recent_customers(
            db, siblings, limit=_FUZZY_CANDIDATE_POOL,
        )
        q_lower = q_text.lower()
        scored: list[tuple[float, Customer]] = []
        for c in candidates:
            if c.id in matched_ids:
                continue
            name = (c.full_name or "").lower()
            if not name:
                continue
            ratio = SequenceMatcher(None, q_lower, name).ratio()
            if ratio >= _FUZZY_MATCH_RATIO_THRESHOLD:
                scored.append((ratio, c))
        scored.sort(key=lambda t: t[0], reverse=True)
        suggestions = [c for _, c in scored[:_FUZZY_MAX_SUGGESTIONS]]

    return matches, suggestions
