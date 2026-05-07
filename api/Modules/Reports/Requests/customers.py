"""Schemas for customer-driven reports (Top Customers / Top Senders).

Distinct from Top Recipients (which lives in `sales.py`) because
customers come from the `Customer` table — we resolve the FK to
get the display name + phone — whereas recipients are just
free-form strings on the Transfer row.
"""
from pydantic import BaseModel, ConfigDict

from .common import AggregatedRowBase, AggregatedTotals


class CustomerRow(AggregatedRowBase):
    customer: str  # Resolved name, or "(walk-in)", or "Customer #ID"
    phone: str = ""


class TopCustomersResponse(BaseModel):
    rows: list[CustomerRow]
    totals: AggregatedTotals
    model_config = ConfigDict(extra="forbid")
