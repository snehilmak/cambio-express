"""Schemas for employee-driven reports.

Two flavors with different group keys (per the migration ADR — they
answer different questions):

  Sales by Employee     — group by Transfer.created_by (login user
                          who SAVED the row).
  Cashier Productivity  — group by Transfer.employee_id (StoreEmployee
                          on duty who PROCESSED the customer).

Both resolve their FKs to display names; the Cashier flavor adds
`is_active` so deactivated roster rows can be tagged.
"""
from pydantic import BaseModel, ConfigDict

from .common import AggregatedRowBase, AggregatedTotals


class EmployeeRow(AggregatedRowBase):
    employee: str          # full_name or username, or "(unattributed)"
    username: str = ""


class CashierRow(AggregatedRowBase):
    cashier: str           # roster name, or "Cashier #ID", or "(unattributed)"
    is_active: bool = False


class SalesByEmployeeResponse(BaseModel):
    rows: list[EmployeeRow]
    totals: AggregatedTotals
    model_config = ConfigDict(extra="forbid")


class CashierProductivityResponse(BaseModel):
    rows: list[CashierRow]
    totals: AggregatedTotals
    model_config = ConfigDict(extra="forbid")
