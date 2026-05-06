"""Reports module — Repositories layer.

Each module here owns a slice of query intent. Functions accept an
explicit SQLAlchemy `Session` so the same code paths work from:

  - **Flask routes** (legacy app.py), which pass `db.session`.
  - **FastAPI routes** (new), which inject a per-request session via
    `Depends(get_db)`.

That's the contract for the strangler-fig phase. Once Flask is gone,
we can revisit and fold in dependency-injected repository classes if
the function-style starts to feel limiting.

Layer rules from the ADR:
    Repository → Model        ✓
    Repository → DB session   ✓
    Repository → Service      ✗
    Repository → Controller   ✗
    Repository → Provider     ✗

Adding a new query: drop a function in the right file, write a unit
test alongside (`tests/Modules/Reports/Repositories/test_<file>.py`),
expose it through `__all__` here.
"""
from .transfers import (
    aggregate,
    period_filters,
)

__all__ = [
    "aggregate",
    "period_filters",
]
