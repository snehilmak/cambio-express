"""Exact money conversion — the ONLY place dollars ↔ cents math lives.

The schema is migrating from Float dollars to BigInteger cents
(P0-3, HANDOFF.md §2) so money math is exact. The conversion rules:

* ``to_cents``  — dollars (float / str / Decimal / int) → integer
  cents, rounding HALF-UP at the cent like a cash register does
  ("2.675" → 268, never bankers-rounded to 267). Goes through
  ``Decimal(str(x))`` so float artifacts (2.675 stored as
  2.67499999…) still round the way the operator wrote them.
* ``to_dollars`` — integer cents → float dollars for the API
  boundary. Exact for any realistic amount (2^53 cents ≈ $90
  trillion), so the JSON contract keeps speaking dollars while
  the database and all derived math stay integral.

Model pattern (see BankSync for the original): store
``<name>_cents = Column(BigInteger)`` and expose a ``<name>``
property whose getter returns dollars and whose setter accepts
dollars — Python readers/writers and ORM kwargs keep working in
dollars, while SQL expressions are forced onto the ``_cents``
column explicitly (a missed call site fails loudly instead of
being silently off by 100×).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_CENT = Decimal("0.01")


def to_cents(dollars: object) -> int:
    """Dollars → integer cents, HALF-UP at the cent. None/'' → 0."""
    if dollars is None or dollars == "":
        return 0
    try:
        quantized = Decimal(str(dollars)).quantize(_CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError(f"not a money amount: {dollars!r}") from exc
    return int(quantized * 100)


def to_dollars(cents: int | None) -> float:
    """Integer cents → float dollars for the API boundary."""
    return (cents or 0) / 100.0
