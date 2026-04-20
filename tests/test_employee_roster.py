"""Tests for the store-employee roster + Transfer audit log.

Covers:
- Admin can add, rename, deactivate, and reactivate names on the roster.
- The "Processed by" dropdown on the transfer form is required and only
  shows active employees.
- Transfer creation records a TransferAudit entry with action="created" and
  the snapshot `employee_name` captured at save time.
- Transfer edits record an audit entry with a human-readable summary and
  preserve `employee_name` even after the roster row is deactivated.
"""
import pytest
from datetime import date
from app import app as flask_app, db


def _today_iso():
    return date.today().isoformat()


def _base_transfer_form(**overrides):
    """Minimal POST body for /transfers/new. Override any field by keyword."""
    body = {
        "send_date":     _today_iso(),
        "company":       "Intermex",
        "sender_name":   "Jane Doe",
        "send_amount":   "100.00",
        "fee":           "5.00",
        "federal_tax":   "1.00",
        "commission":    "0.00",
        "recipient_name":"Juan Perez",
        "country":       "Mexico",
        "recipient_phone":"",
        "sender_phone":  "5551234567",
        "sender_phone_country": "+1",
        "sender_address":"",
        "sender_dob":    "",
        "confirm_number":"INTX-001",
        "status":        "Sent",
        "status_notes":  "",
        "batch_id":      "",
        "internal_notes":"",
    }
    body.update(overrides)
    return body


def _add_roster_row(name, store_id, active=True):
    from app import StoreEmployee
    with flask_app.app_context():
        e = StoreEmployee(store_id=store_id, name=name, is_active=active)
        db.session.add(e)
        db.session.commit()
        return e.id


def _store_id():
    from app import Store
    with flask_app.app_context():
        s = Store.query.filter_by(slug="test-store").first()
        return s.id


# ── Roster CRUD ─────────────────────────────────────────────────

def test_admin_can_add_a_roster_name(logged_in_client):
    resp = logged_in_client.post("/admin/settings/roster/add",
                                 data={"name": "Maria Gonzalez"},
                                 follow_redirects=False)
    assert resp.status_code == 302
    from app import StoreEmployee
    with flask_app.app_context():
        e = StoreEmployee.query.filter_by(name="Maria Gonzalez").first()
        assert e is not None
        assert e.is_active is True


def test_duplicate_add_reactivates_instead_of_duplicating(logged_in_client):
    sid = _store_id()
    eid = _add_roster_row("Alex", sid, active=False)
    # Case-insensitive match — "ALEX" should reactivate the existing row.
    resp = logged_in_client.post("/admin/settings/roster/add",
                                 data={"name": "ALEX"},
                                 follow_redirects=False)
    assert resp.status_code == 302
    from app import StoreEmployee
    with flask_app.app_context():
        rows = StoreEmployee.query.filter(
            db.func.lower(StoreEmployee.name) == "alex"
        ).all()
        assert len(rows) == 1
        assert rows[0].id == eid
        assert rows[0].is_active is True


def test_admin_can_deactivate_and_reactivate(logged_in_client):
    sid = _store_id()
    eid = _add_roster_row("Sam", sid)
    logged_in_client.post(f"/admin/settings/roster/{eid}/toggle")
    from app import StoreEmployee
    with flask_app.app_context():
        assert db.session.get(StoreEmployee, eid).is_active is False
    logged_in_client.post(f"/admin/settings/roster/{eid}/toggle")
    with flask_app.app_context():
        assert db.session.get(StoreEmployee, eid).is_active is True


def test_admin_can_rename_without_losing_id(logged_in_client):
    sid = _store_id()
    eid = _add_roster_row("Original Name", sid)
    logged_in_client.post(f"/admin/settings/roster/{eid}/rename",
                          data={"name": "New Name"})
    from app import StoreEmployee
    with flask_app.app_context():
        e = db.session.get(StoreEmployee, eid)
        assert e.name == "New Name"


# ── Transfer form dropdown + required validation ────────────────

def test_transfer_form_shows_roster_dropdown(logged_in_client):
    sid = _store_id()
    _add_roster_row("Maria", sid)
    _add_roster_row("Bob", sid, active=False)  # inactive — must be hidden
    resp = logged_in_client.get("/transfers/new")
    assert resp.status_code == 200
    assert b"Processed by" in resp.data
    assert b"Maria" in resp.data
    # Inactive employee shouldn't be in the new-transfer dropdown.
    assert b"Bob" not in resp.data


def test_new_transfer_requires_employee_pick(logged_in_client):
    sid = _store_id()
    _add_roster_row("Maria", sid)
    resp = logged_in_client.post("/transfers/new",
                                  data=_base_transfer_form(),
                                  follow_redirects=False)
    # No employee_id → redirect back to form with an error flash.
    assert resp.status_code == 302
    assert "/transfers/new" in resp.headers["Location"]
    from app import Transfer
    with flask_app.app_context():
        assert Transfer.query.count() == 0


# ── Audit log on create ─────────────────────────────────────────

def test_new_transfer_records_created_audit(logged_in_client):
    sid = _store_id()
    eid = _add_roster_row("Maria", sid)
    resp = logged_in_client.post("/transfers/new",
                                  data=_base_transfer_form(employee_id=str(eid)),
                                  follow_redirects=False)
    assert resp.status_code == 302
    from app import Transfer, TransferAudit
    with flask_app.app_context():
        t = Transfer.query.first()
        assert t is not None
        assert t.employee_id == eid
        assert t.employee_name == "Maria"  # snapshot captured
        events = TransferAudit.query.filter_by(transfer_id=t.id).all()
        assert len(events) == 1
        assert events[0].action == "created"
        assert events[0].employee_name == "Maria"


# ── Audit log on edit + status change classification ────────────

def test_edit_transfer_records_audit_with_diff_summary(logged_in_client):
    sid = _store_id()
    eid_maria = _add_roster_row("Maria", sid)
    eid_bob = _add_roster_row("Bob", sid)
    # First, create the transfer via POST so creator audit exists.
    logged_in_client.post("/transfers/new",
                          data=_base_transfer_form(employee_id=str(eid_maria)))
    from app import Transfer, TransferAudit
    with flask_app.app_context():
        tid = Transfer.query.first().id

    # Now edit — Bob changes the fee and status. Should log an "updated" entry.
    edit_body = _base_transfer_form(
        employee_id=str(eid_bob), fee="7.50", status="Canceled",
    )
    logged_in_client.post(f"/transfers/{tid}/edit", data=edit_body)
    with flask_app.app_context():
        events = TransferAudit.query.filter_by(transfer_id=tid)\
            .order_by(TransferAudit.created_at.asc()).all()
        assert len(events) == 2
        edit = events[1]
        assert edit.action == "updated"
        assert edit.employee_name == "Bob"
        assert "Status" in edit.summary
        assert "Fee" in edit.summary
        # Snapshot: transfer now shows Bob as processor.
        assert db.session.get(Transfer, tid).employee_name == "Bob"


def test_status_only_edit_marks_audit_as_status_changed(logged_in_client):
    sid = _store_id()
    eid = _add_roster_row("Maria", sid)
    logged_in_client.post("/transfers/new",
                          data=_base_transfer_form(employee_id=str(eid)))
    from app import Transfer, TransferAudit
    with flask_app.app_context():
        tid = Transfer.query.first().id
    edit_body = _base_transfer_form(employee_id=str(eid), status="Canceled")
    logged_in_client.post(f"/transfers/{tid}/edit", data=edit_body)
    with flask_app.app_context():
        latest = TransferAudit.query.filter_by(transfer_id=tid)\
            .order_by(TransferAudit.created_at.desc()).first()
        assert latest.action == "status_changed"


# ── Employee_name survives roster deactivation ──────────────────

def test_deactivating_employee_preserves_historical_attribution(logged_in_client):
    sid = _store_id()
    eid = _add_roster_row("Maria", sid)
    logged_in_client.post("/transfers/new",
                          data=_base_transfer_form(employee_id=str(eid)))
    from app import Transfer, StoreEmployee
    with flask_app.app_context():
        t = Transfer.query.first()
        tid = t.id
        assert t.employee_name == "Maria"
    # Admin deactivates Maria.
    logged_in_client.post(f"/admin/settings/roster/{eid}/toggle")
    with flask_app.app_context():
        assert db.session.get(StoreEmployee, eid).is_active is False
        # Historical transfer still shows Maria by name.
        assert db.session.get(Transfer, tid).employee_name == "Maria"


def test_edit_page_shows_inactive_employee_as_preselected_option(logged_in_client):
    sid = _store_id()
    eid = _add_roster_row("Maria", sid)
    logged_in_client.post("/transfers/new",
                          data=_base_transfer_form(employee_id=str(eid)))
    from app import Transfer
    with flask_app.app_context():
        tid = Transfer.query.first().id
    # Deactivate Maria — she should still appear in the edit dropdown so
    # the attribution doesn't silently blank when the page renders.
    logged_in_client.post(f"/admin/settings/roster/{eid}/toggle")
    resp = logged_in_client.get(f"/transfers/{tid}/edit")
    assert resp.status_code == 200
    assert b"Maria" in resp.data


# ── Activity section on edit page ──────────────────────────────

def test_edit_page_renders_audit_activity_section(logged_in_client):
    sid = _store_id()
    eid = _add_roster_row("Maria", sid)
    logged_in_client.post("/transfers/new",
                          data=_base_transfer_form(employee_id=str(eid)))
    from app import Transfer
    with flask_app.app_context():
        tid = Transfer.query.first().id
    resp = logged_in_client.get(f"/transfers/{tid}/edit")
    assert resp.status_code == 200
    assert b"Activity" in resp.data
    assert b"Created" in resp.data
