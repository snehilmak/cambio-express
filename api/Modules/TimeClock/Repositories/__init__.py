"""TimeClock — Repositories.

Pure query functions for time-clock endpoints. No permission
checks, no audit, no commits.
"""
from api.Modules.TimeClock.Repositories.employees import (
    get_employee_name_map,
    list_active_employees,
)
from api.Modules.TimeClock.Repositories.history import (
    list_entry_history,
)

__all__ = [
    "get_employee_name_map",
    "list_active_employees",
    "list_entry_history",
]
