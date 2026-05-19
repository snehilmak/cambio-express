"""Transfer audit-log helpers.

Per CLAUDE.md the `TransferAudit` table is the per-row history
of every change to a `Transfer`. Three small helpers own the
contract:

  - `TRANSFER_AUDIT_FIELDS` — the field → label list that
    determines which Transfer columns get audited and how they're
    rendered in the diff summary. Adding a new column to the
    audit means appending a tuple here.
  - `transfer_snapshot(t)` — capture the audited subset of a
    Transfer row as a dict.
  - `summarize_changes(before, after, max_fields=4)` — format a
    before/after diff into the human-readable summary string
    stored on `TransferAudit.summary`.
  - `record_audit(db, transfer, user, action, employee_id,
    employee_name, summary)` — append a TransferAudit row.
    Caller commits.

Pure-ish: only `record_audit` touches the DB, and even it just
adds the row (the surrounding transaction commits in the route).
"""
from sqlalchemy.orm import Session
from typing import Any


# Audited column → human-readable label. Order is the order
# fields appear in summary strings. Adding a new field is one
# line here + one matching cell in the audit-log template.
TRANSFER_AUDIT_FIELDS: list[tuple[str, str]] = [
    ("send_date",       "Send date"),
    ("company",         "Company"),
    ("service_type",    "Service"),
    ("sender_name",     "Sender"),
    ("send_amount",     "Amount"),
    ("fee",             "Fee"),
    ("federal_tax",     "Tax"),
    ("commission",      "Commission"),
    ("recipient_name",  "Recipient"),
    ("country",         "Country"),
    ("recipient_phone", "Recipient phone"),
    ("sender_phone",    "Sender phone"),
    ("sender_address",  "Sender address"),
    ("confirm_number",  "Confirm #"),
    ("status",          "Status"),
    ("status_notes",    "Status notes"),
    ("batch_id",        "Batch"),
    ("internal_notes",  "Notes"),
    ("employee_name",   "Processed by"),
]


def transfer_snapshot(transfer: Any) -> dict[str, Any]:
    """Capture the audited subset of `transfer` as a dict.

    The shape matches `TRANSFER_AUDIT_FIELDS` so a `summarize_
    changes` call against two snapshots produces a useful diff
    string regardless of which non-audited fields changed.
    """
    return {
        field: getattr(transfer, field, None)
        for field, _ in TRANSFER_AUDIT_FIELDS
    }


def summarize_changes(
    before: dict[str, Any], after: dict[str, Any], max_fields: int = 4,
) -> str:
    """Format a before/after diff into the audit-log summary.

    Walks `TRANSFER_AUDIT_FIELDS` in order, includes only fields
    that actually changed, renders empty / None values as the
    em-dash sentinel (—), and caps the output at `max_fields`
    entries with a "+N more field(s)" overflow note.

    Returns the joined "Field: old → new; …" string.
    """
    parts: list[str] = []
    for field, label in TRANSFER_AUDIT_FIELDS:
        old, new = before.get(field), after.get(field)
        if (old or None) == (new or None):
            continue
        old_s = "—" if old in (None, "") else str(old)
        new_s = "—" if new in (None, "") else str(new)
        parts.append(f"{label}: {old_s} → {new_s}")
    if len(parts) > max_fields:
        overflow = len(parts) - max_fields
        parts = parts[:max_fields] + [
            f"+{overflow} more field{'s' if overflow != 1 else ''}"
        ]
    return "; ".join(parts)


def record_audit(
    db: Session,
    transfer: Any,
    user: Any,
    action: str,
    employee_id: int | None,
    employee_name: str,
    summary: str,
) -> None:
    """Append a `TransferAudit` row capturing the action.

    `user` is the User row that performed the change; `employee_
    id` and `employee_name` snapshot the cashier picked in the
    "Processed by" field (so the audit history survives even if
    the StoreEmployee row is later deleted).

    No commit — caller wraps the audit row in the same
    transaction as the underlying transfer mutation.
    """
    from api.Modules.Audit.Models import TransferAudit
    db.add(TransferAudit(
        store_id=transfer.store_id,
        transfer_id=transfer.id,
        user_id=user.id if user else None,
        employee_id=employee_id,
        employee_name=employee_name,
        action=action,
        summary=summary,
    ))
