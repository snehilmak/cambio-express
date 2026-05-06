"""SQLAlchemy models the Reports module reads from.

During the strangler-fig migration we **re-export** the existing
legacy models from `app.py` rather than redefining them here. This
keeps a single source of truth for the schema while the rest of the
Reports module migrates to the new layered shape.

When the Transfers module migrates (PR-3 in the per-module sequence
from ADR §4 — i.e., the third module after Reports + Customers),
the `Transfer` model will move to `api/Modules/Transfers/Models/`
and this file will switch its import accordingly. Same eventual
fate for `Store`, `User`, `DailyReport`, etc.

Don't add new model definitions here — only re-exports. New tables
that the Reports module owns (if any are ever needed) get their own
file alongside this `__init__.py`.
"""
from app import (  # noqa: WPS433 — intentional legacy hop, see migration ADR
    Transfer,
    Store,
    User,
    DailyReport,
    StoreEmployee,
    Customer,
    ACHBatch,
    BankTransaction,
    ReturnCheck,
)
from app import _OWNER_TRANSFER_EXCLUDED

__all__ = [
    "Transfer",
    "Store",
    "User",
    "DailyReport",
    "StoreEmployee",
    "Customer",
    "ACHBatch",
    "BankTransaction",
    "ReturnCheck",
    "_OWNER_TRANSFER_EXCLUDED",
]
