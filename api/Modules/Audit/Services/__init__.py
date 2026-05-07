"""Audit — Services. Append-only record_* helpers."""
from api.Modules.Audit.Services.recorder import (
    record_operator_action,
    record_superadmin_action,
)

__all__ = [
    "record_operator_action",
    "record_superadmin_action",
]
