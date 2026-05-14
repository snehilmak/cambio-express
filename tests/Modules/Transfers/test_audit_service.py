"""Unit tests for Transfers.Services.audit (PR 77)."""
from datetime import date
from unittest.mock import MagicMock


def _stub_transfer(*, store_id=1, transfer_id=42, send_amount=100.0,
                    fee=2.0, federal_tax=1.0, status="Sent",
                    company="Intermex"):
    t = MagicMock()
    t.id = transfer_id
    t.store_id = store_id
    t.send_date = date(2026, 5, 1)
    t.company = company
    t.service_type = "Money Transfer"
    t.sender_name = "Alice"
    t.send_amount = send_amount
    t.fee = fee
    t.federal_tax = federal_tax
    t.commission = 0.0
    t.recipient_name = "Bob"
    t.country = "Mexico"
    t.recipient_phone = "+52 555 1234"
    t.sender_phone = "+1 555 9999"
    t.sender_address = "123 Main"
    t.confirm_number = ""
    t.status = status
    t.status_notes = ""
    t.batch_id = None
    t.internal_notes = ""
    t.employee_name = "Cashier"
    return t


# ── transfer_snapshot ─────────────────────────────────────


def test_snapshot_captures_audited_fields_only():
    """Every key in the snapshot dict must be from
    TRANSFER_AUDIT_FIELDS — no extra Transfer columns leak in."""
    from api.Modules.Transfers.Services import (
        TRANSFER_AUDIT_FIELDS, transfer_snapshot,
    )
    t = _stub_transfer()
    snap = transfer_snapshot(t)
    expected_keys = {field for field, _ in TRANSFER_AUDIT_FIELDS}
    assert set(snap.keys()) == expected_keys


def test_snapshot_reads_attribute_values():
    from api.Modules.Transfers.Services import transfer_snapshot
    t = _stub_transfer(send_amount=250.0, status="Pending")
    snap = transfer_snapshot(t)
    assert snap["send_amount"] == 250.0
    assert snap["status"] == "Pending"
    assert snap["sender_name"] == "Alice"


def test_snapshot_handles_missing_attributes_with_none():
    """Defensive: a transient row missing some columns reads as
    None rather than AttributeError."""
    from api.Modules.Transfers.Services import transfer_snapshot
    t = MagicMock(spec=[])  # no attributes at all
    snap = transfer_snapshot(t)
    assert all(v is None for v in snap.values())


# ── summarize_changes ─────────────────────────────────────


def test_summarize_no_changes_returns_empty_string():
    from api.Modules.Transfers.Services import (
        summarize_transfer_changes, transfer_snapshot,
    )
    t = _stub_transfer()
    snap = transfer_snapshot(t)
    assert summarize_transfer_changes(snap, snap) == ""


def test_summarize_one_change():
    from api.Modules.Transfers.Services import summarize_transfer_changes
    before = {"sender_name": "Alice", "send_amount": 100.0}
    after  = {"sender_name": "Bob",   "send_amount": 100.0}
    result = summarize_transfer_changes(before, after)
    assert result == "Sender: Alice → Bob"


def test_summarize_multiple_changes_joined():
    from api.Modules.Transfers.Services import summarize_transfer_changes
    before = {
        "sender_name": "Alice",
        "send_amount": 100.0,
        "status": "Pending",
    }
    after = {
        "sender_name": "Bob",
        "send_amount": 200.0,
        "status": "Pending",
    }
    result = summarize_transfer_changes(before, after)
    # Two changes, joined with "; ".
    assert "Sender: Alice → Bob" in result
    assert "Amount: 100.0 → 200.0" in result
    assert result.count(";") == 1


def test_summarize_uses_em_dash_for_empty_values():
    """Empty / None values render as em-dash so the diff is
    readable for newly-set or cleared fields."""
    from api.Modules.Transfers.Services import summarize_transfer_changes
    before = {"recipient_phone": ""}
    after  = {"recipient_phone": "+52 555 1234"}
    result = summarize_transfer_changes(before, after)
    assert "Recipient phone: — → +52 555 1234" == result


def test_summarize_treats_empty_and_none_as_equal():
    """`None` vs `""` shouldn't show as a change — both render
    as em-dash, so the operator hasn't actually changed
    anything."""
    from api.Modules.Transfers.Services import summarize_transfer_changes
    before = {"internal_notes": None}
    after  = {"internal_notes": ""}
    assert summarize_transfer_changes(before, after) == ""


def test_summarize_caps_at_max_fields_with_overflow_note():
    """When more than `max_fields` fields changed, only the
    first N show + a "+X more fields" overflow note."""
    from api.Modules.Transfers.Services import summarize_transfer_changes
    before = {
        "sender_name": "A", "send_amount": 1, "fee": 1,
        "commission": 1, "recipient_name": "X",
        "country": "Mexico",
    }
    after = {
        "sender_name": "B", "send_amount": 2, "fee": 2,
        "commission": 2, "recipient_name": "Y",
        "country": "Guatemala",
    }
    # 6 changes; cap at 4 → 4 + "+2 more fields".
    result = summarize_transfer_changes(before, after, max_fields=4)
    # Exactly 4 commas/semicolons in the prefix + the overflow
    parts = result.split("; ")
    assert len(parts) == 5  # 4 changes + 1 overflow
    assert parts[-1] == "+2 more fields"


def test_summarize_overflow_singular_when_one_extra():
    from api.Modules.Transfers.Services import summarize_transfer_changes
    before = {
        "sender_name": "A", "send_amount": 1, "fee": 1,
        "commission": 1, "recipient_name": "X",
    }
    after = {
        "sender_name": "B", "send_amount": 2, "fee": 2,
        "commission": 2, "recipient_name": "Y",
    }
    # 5 changes, max_fields=4 → "+1 more field" (singular)
    result = summarize_transfer_changes(before, after, max_fields=4)
    parts = result.split("; ")
    assert parts[-1] == "+1 more field"


def test_summarize_walks_in_registry_order():
    """The diff order matches TRANSFER_AUDIT_FIELDS, not
    insertion order in the dict."""
    from api.Modules.Transfers.Services import summarize_transfer_changes
    # Status is later than sender_name in the registry
    before = {"status": "Pending", "sender_name": "Alice"}
    after  = {"status": "Sent",    "sender_name": "Bob"}
    result = summarize_transfer_changes(before, after)
    parts = result.split("; ")
    # sender_name (index 3 in registry) comes before status (14)
    assert parts[0].startswith("Sender:")
    assert parts[1].startswith("Status:")


# ── record_audit ──────────────────────────────────────────


def test_record_audit_adds_row_with_expected_fields():
    """The audit row carries store_id + transfer_id + user_id +
    employee snapshot + action + summary."""
    from api.Modules.Audit.Models import TransferAudit
    from app import app as flask_app, db
    from api.Modules.Transfers.Services import record_transfer_audit
    with flask_app.app_context():
        TransferAudit.query.delete()
        db.session.commit()
        # Stub transfer + user.
        t = MagicMock()
        t.store_id = 5
        t.id = 99
        u = MagicMock()
        u.id = 7
        record_transfer_audit(
            db.session, t, u, action="edit",
            employee_id=42, employee_name="Cashier Bob",
            summary="Sender: Alice → Bob",
        )
        db.session.flush()
        rows = TransferAudit.query.all()
        assert len(rows) == 1
        row = rows[0]
        assert row.store_id == 5
        assert row.transfer_id == 99
        assert row.user_id == 7
        assert row.employee_id == 42
        assert row.employee_name == "Cashier Bob"
        assert row.action == "edit"
        assert row.summary == "Sender: Alice → Bob"


def test_record_audit_handles_none_user():
    """System / cron-triggered audits may have no user — user_id
    falls through as None."""
    from api.Modules.Audit.Models import TransferAudit
    from app import app as flask_app, db
    from api.Modules.Transfers.Services import record_transfer_audit
    with flask_app.app_context():
        TransferAudit.query.delete()
        db.session.commit()
        t = MagicMock()
        t.store_id = 1; t.id = 2
        record_transfer_audit(
            db.session, t, user=None, action="auto_close",
            employee_id=None, employee_name="",
            summary="status: Pending → Closed",
        )
        db.session.flush()
        row = TransferAudit.query.first()
        assert row.user_id is None
        assert row.action == "auto_close"


def test_record_audit_does_not_commit():
    """Caller commits — record_audit just adds the row."""
    from api.Modules.Audit.Models import TransferAudit
    from app import app as flask_app, db
    from api.Modules.Transfers.Services import record_transfer_audit
    with flask_app.app_context():
        TransferAudit.query.delete()
        db.session.commit()
        t = MagicMock()
        t.store_id = 1; t.id = 2
        u = MagicMock(); u.id = 1
        # Patch commit to detect calls.
        orig_commit = db.session.commit
        commit_calls = [0]
        db.session.commit = lambda: commit_calls.__setitem__(
            0, commit_calls[0] + 1,
        )
        try:
            record_transfer_audit(
                db.session, t, u, "x", None, "", "",
            )
            assert commit_calls[0] == 0
        finally:
            db.session.commit = orig_commit
            db.session.rollback()


# ── constants ─────────────────────────────────────────────


def test_audit_fields_includes_core_columns():
    """Every Transfer column the operator can edit should be
    audited — accidentally dropping one means changes silently
    disappear from history."""
    from api.Modules.Transfers.Services import TRANSFER_AUDIT_FIELDS
    field_names = [field for field, _ in TRANSFER_AUDIT_FIELDS]
    # Spot-check a few stable columns.
    expected = {
        "send_date", "send_amount", "fee", "federal_tax",
        "sender_name", "recipient_name", "country",
        "status", "employee_name",
    }
    assert expected.issubset(set(field_names))


# ── legacy Flask wrappers ─────────────────────────────────








