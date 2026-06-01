"""Audit-log SQL helpers for time-clock entry history.

The "who edited this punch" feed is built from OperatorAuditLog
rows tagged with target_type='time_clock_entry'.
"""
from sqlalchemy.orm import Session

from api.Modules.Audit.Models import OperatorAuditLog


def list_entry_history(
    db: Session, store_id: int, entry_id: int,
) -> list[OperatorAuditLog]:
    """All audit rows for one time-clock entry, newest first."""
    return (
        db.query(OperatorAuditLog)
          .filter(
              OperatorAuditLog.store_id == store_id,
              OperatorAuditLog.target_type == "time_clock_entry",
              OperatorAuditLog.target_id == str(entry_id),
          )
          .order_by(OperatorAuditLog.id.desc())
          .all()
    )
