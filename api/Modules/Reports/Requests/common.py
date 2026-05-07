"""Cross-cutting Pydantic types for the Reports module.

`AggregatedRowBase` and `AggregatedTotals` mirror the dict shape the
repository returns from `aggregate()`. Family-specific schemas
(`sales.py`, `customers.py`, `employees.py`) inherit from
`AggregatedRowBase` and add their identity field(s).

We keep the field names matching the legacy dict keys (`count`,
`sent`, `fees`, `tax`, `avg`) so the templates that consume them
in `report_*.html` don't have to change during the migration.
"""
from pydantic import BaseModel, ConfigDict, Field


class AggregatedRowBase(BaseModel):
    """Numeric envelope for any grouped report row.

    Subclasses add their identity field — `company`, `service_type`,
    `customer`, etc.
    """

    count: int = Field(..., description="Transfers in this group.")
    sent: float = Field(..., description="Sum of send_amount in USD.")
    fees: float = Field(..., description="Sum of fee in USD.")
    tax: float = Field(..., description="Sum of federal_tax in USD.")
    avg: float = Field(..., description="sent / count, or 0 if count == 0.")

    model_config = ConfigDict(extra="forbid")


class AggregatedTotals(BaseModel):
    """Sums across every row, returned alongside the rows."""

    count: int
    sent: float
    fees: float
    tax: float

    model_config = ConfigDict(extra="forbid")
