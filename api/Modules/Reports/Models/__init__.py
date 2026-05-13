"""SQLAlchemy models the Reports module reads from.

The Reports module doesn't own any tables of its own — it
aggregates rows from every other domain. We re-export the
relevant classes here so existing
``from api.Modules.Reports.Models import Transfer`` call sites in
Reports/Services keep working. The canonical definitions live in
their owning domain's ``Models`` package.

Don't add new model definitions here — only re-exports.
"""
from api.Modules.Batches.Models import ACHBatch
from api.Modules.BankSync.Models import BankTransaction
from api.Modules.Customers.Models import Customer
from api.Modules.DailyBook.Models import DailyReport
from api.Modules.ReturnChecks.Models import ReturnCheck
from api.Modules.Tenancy.Models import Store, StoreEmployee, User
from api.Modules.Transfers.Models import Transfer

# Reports-internal constant; lives in app.py until the helpers
# migration pulls it into a Reports Service module.
from app import _OWNER_TRANSFER_EXCLUDED  # noqa: E402

__all__ = [
    "ACHBatch",
    "BankTransaction",
    "Customer",
    "DailyReport",
    "ReturnCheck",
    "Store",
    "StoreEmployee",
    "Transfer",
    "User",
    "_OWNER_TRANSFER_EXCLUDED",
]
