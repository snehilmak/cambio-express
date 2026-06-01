"""Superadmin audit-log SQL helpers.

The superadmin action history is read-only (writes happen via
``record_superadmin_action`` in the recorder Service). These
helpers build the filtered + paginated Query the activity page
needs.
"""
from sqlalchemy.orm import Query, Session

from api.Modules.Audit.Models import SuperadminAuditLog


def superadmin_audit_query(
    db: Session, *, action: str = "",
) -> "Query[SuperadminAuditLog]":
    """Base Query for the superadmin activity feed. Optional
    case-insensitive ``action`` substring filter. Returns the
    Query — caller paginates via ``api.Core.Pagination.paginate``."""
    q = db.query(SuperadminAuditLog)
    if action:
        q = q.filter(SuperadminAuditLog.action.ilike(f"%{action}%"))
    return q.order_by(SuperadminAuditLog.created_at.desc())
