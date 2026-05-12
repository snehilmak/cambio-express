"""Audit-log recorders for superadmin + operator actions.

Two append-only sinks:

  - `SuperadminAuditLog`: platform-wide actions taken by the
    superadmin (extending a trial, comping a plan, flipping a
    feature flag). Read by the superadmin → Activity tab.
  - `OperatorAuditLog`: per-store actions taken by the store's
    own admins/employees on objects that don't have a dedicated
    audit table (daily reports, ACH batches, transfer deletes).
    Read by the admin → Audit log page.

The Services take *explicit* identity kwargs (admin_id, admin_name,
user_role, store_id, ...) instead of reaching into Flask's session.
That keeps them callable from any context — Flask routes, FastAPI
controllers, CLI commands, tests — without spinning up an app
context just to record one row.

Per CLAUDE.md invariant #7: every superadmin mutation MUST call
record_audit. Don't add a superadmin route that mutates state
without a matching record_superadmin_action call.

No commit. The caller wraps the audit row in the same transaction
as the mutation that triggered it, so the audit entry rolls back
if the mutation fails.
"""
from sqlalchemy.orm import Session

from api.Modules.Audit.Models import (
    OperatorAuditLog,
    SuperadminAuditLog,
)


# Schema-imposed limits the recorders enforce so callers can
# pass arbitrary user-supplied strings without truncation
# surprises later.
_SUPERADMIN_TARGET_TYPE_MAX = 30
_SUPERADMIN_TARGET_ID_MAX = 60
_SUPERADMIN_DETAILS_MAX = 2000

_OPERATOR_TARGET_TYPE_MAX = 30
_OPERATOR_TARGET_ID_MAX = 60
_OPERATOR_TARGET_LABEL_MAX = 160
_OPERATOR_ACTION_MAX = 30
_OPERATOR_USER_NAME_MAX = 120
_OPERATOR_USER_ROLE_MAX = 20
_OPERATOR_SUMMARY_MAX = 2000


def record_superadmin_action(
    db: Session,
    *,
    admin_id: int | None,
    admin_name: str,
    action: str,
    target_type: str = "",
    target_id: str = "",
    details: str = "",
) -> SuperadminAuditLog:
    """Append a row to the superadmin audit log.

    `admin_name` is a snapshot — the User row may later be deleted
    and we still want the audit entry to identify who did the
    action. Caller fishes admin_id + admin_name out of session +
    the User row before calling.

    Returns the unsaved row (added to the session, not flushed) so
    a caller that needs the id can call db.flush() itself.
    """
    row = SuperadminAuditLog(
        admin_id=admin_id,
        admin_name=str(admin_name or "")[:_OPERATOR_USER_NAME_MAX],
        action=action,
        target_type=str(target_type)[:_SUPERADMIN_TARGET_TYPE_MAX],
        target_id=str(target_id)[:_SUPERADMIN_TARGET_ID_MAX],
        details=str(details)[:_SUPERADMIN_DETAILS_MAX],
    )
    db.add(row)
    return row


def record_operator_action(
    db: Session,
    *,
    store_id: int,
    user_id: int | None,
    user_name: str,
    user_role: str,
    target_type: str,
    target_id: str = "",
    target_label: str = "",
    action: str,
    summary: str = "",
) -> OperatorAuditLog:
    """Append a row to the per-store operator audit log.

    Captures user identity + role at write time so the audit row
    stays useful even after the User row is later deleted.

    Target types (canonical list — add new ones here when wiring
    a new mutation surface):
        'transfer'        (delete-only — TransferAudit covers
                           create/edit on the per-row table)
        'daily_report'    (lock / unlock / line-item writes via
                           api/Modules/DailyBook)
        'batch'           (create / update / delete via
                           api/Modules/Batches)
        'return_check'    (create / update / delete / mark_loss /
                           mark_fraud / reopen / payment /
                           delete_payment via
                           blueprints/bookkeeping_mutations.py)
        'roster_member'   (create / reactivate / deactivate /
                           rename via
                           blueprints/admin_settings_mutations.py)
        'user'            (reset_password — admin-side employee
                           password reset)
        'owner_link'      (connect — admin redeems an owner code)

    Actions:
        'create', 'update', 'delete', 'lock', 'unlock',
        'reactivate', 'deactivate', 'rename', 'mark_loss',
        'mark_fraud', 'reopen', 'payment', 'delete_payment',
        'reset_password', 'connect'.

    Returns the unsaved row (added to the session, not flushed).
    """
    row = OperatorAuditLog(
        store_id=store_id,
        user_id=user_id,
        user_name=str(user_name or "")[:_OPERATOR_USER_NAME_MAX],
        user_role=str(user_role or "")[:_OPERATOR_USER_ROLE_MAX],
        target_type=str(target_type)[:_OPERATOR_TARGET_TYPE_MAX],
        target_id=str(target_id)[:_OPERATOR_TARGET_ID_MAX],
        target_label=str(target_label)[:_OPERATOR_TARGET_LABEL_MAX],
        action=str(action)[:_OPERATOR_ACTION_MAX],
        summary=str(summary)[:_OPERATOR_SUMMARY_MAX],
    )
    db.add(row)
    return row
