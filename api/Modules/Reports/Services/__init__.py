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
from .ach_volume import ach_volume
from .bank_charges import bank_charges_by_account
from .bank_rule_audit import bank_rule_audit
from .bank_txn_breakdown import bank_txn_breakdown
from .customer_segments import new_vs_returning
from .customers import top_customers
from .daily_aggregates import check_deposits, daily_drops
from .date_helpers import day_end, day_start
from .employee_activity import employee_activity
from .employees import cashier_productivity, sales_by_employee
from .fees_vs_tax import fees_vs_tax
from .high_value_transfers import high_value_transfers
from .period_comparison import (
    PL_EXPENSE_LINES,
    PL_INCOME_LINES,
    period_comparison,
)
from .period_pl import period_pl
from .returned_checks import returned_check_status
from .sales import (
    by_destination_country,
    sales_by_company,
    sales_by_service,
    top_recipients,
)

__all__ = [
    "PL_EXPENSE_LINES",
    "PL_INCOME_LINES",
    "ach_volume",
    "bank_charges_by_account",
    "bank_rule_audit",
    "bank_txn_breakdown",
    "by_destination_country",
    "cashier_productivity",
    "check_deposits",
    "daily_drops",
    "day_end",
    "day_start",
    "employee_activity",
    "fees_vs_tax",
    "high_value_transfers",
    "new_vs_returning",
    "period_comparison",
    "period_pl",
    "returned_check_status",
    "sales_by_company",
    "sales_by_employee",
    "sales_by_service",
    "top_customers",
    "top_recipients",
]
