"""Reports module — Services layer.

A service is a function that:
  1. Takes a SQLAlchemy `Session` (so it works in both Flask and
     FastAPI request paths during the strangler-fig migration).
  2. Calls one or more Repository functions.
  3. Applies business logic (renaming dict keys for the template,
     resolving FK lookups via a separate query, sorting, limit).
  4. Returns `(rows, totals)` — same shape as the legacy data fns
     in `app.py` for drop-in compatibility.

Layer rules from the ADR:
    Service → Repository    ✓
    Service → Provider      ✓ (none yet — Reports is read-only)
    Service → Service       ✓ (sparingly)
    Service → Controller    ✗
    Service → DB session    via Repository, never raw

The legacy `_sales_by_company_data` etc. in `app.py` are now
2-line shims that delegate to the corresponding service. Single
source of truth for the business logic; both Flask templates and
the new FastAPI controllers (PR 4) hit the same code.
"""
from .customers import top_customers
from .date_helpers import day_end, day_start
from .employees import cashier_productivity, sales_by_employee
from .sales import (
    by_destination_country,
    sales_by_company,
    sales_by_service,
    top_recipients,
)

__all__ = [
    "by_destination_country",
    "cashier_productivity",
    "day_end",
    "day_start",
    "sales_by_company",
    "sales_by_employee",
    "sales_by_service",
    "top_customers",
    "top_recipients",
]
