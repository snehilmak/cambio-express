"""Canonical UTC timestamp for the application.

Every runtime call site that needs "now in UTC" should use
``utc_now()`` instead of ``datetime.utcnow()``.

``datetime.utcnow()`` is deprecated in Python 3.12 (PEP 615) because
it returns a *naive* datetime that callers silently compare against
timezone-aware values — a class of bug that's hard to catch in
review.  This helper centralizes the call so a future migration to
``datetime.now(timezone.utc)`` (timezone-aware) only touches one
line.

For now we still return a **naive** datetime because the ORM column
defaults (``Column(DateTime, default=datetime.utcnow)``) and every
stored value in the DB are naive UTC.  Mixing aware + naive in
comparisons would raise ``TypeError`` at runtime.  When the DB layer
is ready for aware timestamps, flip the implementation here.
"""
from datetime import datetime


def utc_now() -> datetime:
    """Return the current UTC time as a naive datetime."""
    return datetime.utcnow()
