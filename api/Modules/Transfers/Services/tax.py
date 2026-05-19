"""Transfer tax + service-type predicates.

Single source of truth for the federal-tax math + service-type
classification that gates it. Both `new_transfer` and
`edit_transfer` call into the same helpers so the rule can't drift
between create and update.

Rules (per CLAUDE.md invariant #9):
  - `Transfer.federal_tax` is the percentage the IRS collects on
    money sent abroad — separate from `Transfer.fee` (which is
    store revenue).
  - Tax applies only to `service_type="Money Transfer"`. Bill
    Payment / Top Up / Recharge are exempt — no ACH withdrawal
    crosses a border for those.
  - Tax also skips when the recipient country is domestic (US),
    even for Money Transfer.
  - Rate is `Store.federal_tax_rate` (defaults to 0.01 = 1%).

Pure functions — no DB, no Stripe, no side-effects.
"""
from typing import Any


# All recognized service types. The transfer form's dropdown
# options must match this tuple exactly.
SERVICE_TYPES: tuple[str, ...] = (
    "Money Transfer", "Bill Payment", "Top Up", "Recharge",
)

# Service types that don't carry the federal-tax remittance.
# Money Transfer is the only taxable kind; everything else
# is exempt.
TAX_EXEMPT_SERVICES: frozenset[str] = frozenset(SERVICE_TYPES) - {
    "Money Transfer",
}

# Recipient countries that don't carry the federal-tax
# remittance. Domestic transfers (within the US) skip the tax
# entirely — it's the IRS levy on money sent abroad.
DOMESTIC_COUNTRIES: frozenset[str] = frozenset({"United States"})

# Countries shown in the recipient-country dropdown on the
# transfer form. Single source so server validation, template,
# and tests agree. 'United States' is included so admins can
# log a domestic transfer; 'Other' is the catch-all.
TRANSFER_COUNTRIES: tuple[str, ...] = (
    "United States", "Mexico", "Guatemala", "El Salvador", "Honduras",
    "Dominican Republic", "Colombia", "Ecuador", "Peru", "Other",
)


def normalize_service_type(raw: str | None) -> str:
    """Coerce the form input to a known service type.

    Anything we don't recognize falls back to "Money Transfer"
    (the historical default), so a bad client value can't
    quietly disable tax.
    """
    val = (raw or "").strip()
    return val if val in SERVICE_TYPES else "Money Transfer"


def federal_tax_for(
    send_amount: float | None,
    service_type: str,
    store: Any,
    country: str | None = None,
) -> float:
    """Compute the federal tax on a transfer.

    Returns 0.0 in three cases:
      - service_type isn't `Money Transfer`
      - recipient country is in `DOMESTIC_COUNTRIES`
      - store has no `federal_tax_rate` set (defensive)

    Otherwise returns `send_amount * rate` rounded to cents.
    """
    if service_type in TAX_EXEMPT_SERVICES:
        return 0.0
    if country and country.strip() in DOMESTIC_COUNTRIES:
        return 0.0
    rate = (store.federal_tax_rate if store else None) or 0
    return round((send_amount or 0) * rate, 2)
