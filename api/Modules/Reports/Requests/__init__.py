"""Reports module — Pydantic request/response schemas.

Schemas are split by report family so each file stays focused:

  sales.py       — Sales-by-X, By-destination-country, Top-recipients.
                   Same row shape (label + count + sums + avg) so they
                   share base classes.
  customers.py   — Top customers / Top senders. Adds a phone field.
  employees.py   — Sales-by-employee and Cashier-productivity. Adds
                   identity fields (username for users, is_active for
                   roster employees).

Cross-cutting types (period filter, totals, common row base) live in
`common.py` and get imported by the family-specific files.
"""
from .common import AggregatedTotals, AggregatedRowBase
from .sales import (
    CompanyRow,
    ServiceTypeRow,
    CountryRow,
    RecipientRow,
    SalesByCompanyResponse,
    SalesByServiceResponse,
    ByDestinationCountryResponse,
    TopRecipientsResponse,
)
from .customers import CustomerRow, TopCustomersResponse
from .employees import (
    EmployeeRow,
    CashierRow,
    SalesByEmployeeResponse,
    CashierProductivityResponse,
)

__all__ = [
    "AggregatedTotals",
    "AggregatedRowBase",
    "CompanyRow",
    "ServiceTypeRow",
    "CountryRow",
    "RecipientRow",
    "CustomerRow",
    "EmployeeRow",
    "CashierRow",
    "SalesByCompanyResponse",
    "SalesByServiceResponse",
    "ByDestinationCountryResponse",
    "TopRecipientsResponse",
    "TopCustomersResponse",
    "SalesByEmployeeResponse",
    "CashierProductivityResponse",
]
