"""Reports module — Repositories layer.

Each module here owns a slice of query intent. Functions take an
explicit SQLAlchemy ``Session`` (injected via ``Depends(get_db)``
in the FastAPI controllers).

Layer rules from the ADR:
    Repository → Model        ✓
    Repository → DB session   ✓
    Repository → Service      ✗
    Repository → Controller   ✗
    Repository → Provider     ✗

Adding a new query: drop a function in the right file, write a
unit test alongside (``tests/Modules/Reports/Repositories/test_<file>.py``),
expose it through ``__all__`` here.
"""
from .transfers import (
    aggregate,
    period_filters,
)

__all__ = [
    "aggregate",
    "period_filters",
]
