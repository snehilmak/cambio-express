"""Tests for the auto-computed Federal Tax feature.

Rules enforced:
1. New Store rows default to 1% (0.01).
2. Creating a transfer server-side computes federal_tax = send_amount × rate,
   ignoring any value the client submits.
3. Editing a transfer recomputes federal_tax from the edited Send Amount.
4. The admin can update the rate via Settings → Store and the new rate
   applies to future transfers.
5. The transfer form renders the Federal Tax input as readonly.
"""
from datetime import date
from app import app as flask_app, db


def _today_iso():
    return date.today().isoformat()


def _seed_roster_row(store_id, name="Maria"):
    from app import StoreEmployee
    with flask_app.app_context():
        e = StoreEmployee(store_id=store_id, name=name, is_active=True)
        db.session.add(e)
        db.session.commit()
        return e.id


def _store_id():
    from app import Store
    with flask_app.app_context():
        return Store.query.filter_by(slug="test-store").first().id


def _transfer_form_body(employee_id, **overrides):
    body = {
        "send_date":      _today_iso(),
        "company":        "Intermex",
        "sender_name":    "Jane Doe",
        "send_amount":    "500.00",
        "fee":            "5.00",
        # Intentionally pass a bogus federal_tax — the server must ignore it.
        "federal_tax":    "9999.00",
        "commission":     "0.00",
        "recipient_name": "Juan Perez",
        "country":        "Mexico",
        "recipient_phone":"",
        "sender_phone":   "5551234567",
        "sender_phone_country": "+1",
        "sender_address": "",
        "sender_dob":     "",
        "confirm_number": "INTX-001",
        "status":         "Sent",
        "status_notes":   "",
        "batch_id":       "",
        "internal_notes": "",
        "employee_id":    str(employee_id),
    }
    body.update(overrides)
    return body


# ── Store default rate ──────────────────────────────────────────

def test_new_store_defaults_to_one_percent():
    from app import Store
    with flask_app.app_context():
        s = Store.query.filter_by(slug="test-store").first()
        # 0.01 = 1%. Anything else means the column default changed
        # unexpectedly or the seed is overriding.
        assert abs(s.federal_tax_rate - 0.01) < 1e-9


# ── Server-side compute ignores client submission ───────────────

def test_new_transfer_computes_tax_server_side_ignoring_form(logged_in_client):
    sid = _store_id()
    eid = _seed_roster_row(sid)
    logged_in_client.post("/transfers/new",
                           data=_transfer_form_body(eid,
                                send_amount="500.00",
                                federal_tax="9999.00"))
    from app import Transfer
    with flask_app.app_context():
        t = Transfer.query.first()
        assert t is not None
        # 500 × 0.01 = 5.00. Not 9999 (client value), not 0.
        assert abs(t.federal_tax - 5.00) < 0.01


def test_new_transfer_handles_blank_client_tax(logged_in_client):
    sid = _store_id()
    eid = _seed_roster_row(sid)
    logged_in_client.post("/transfers/new",
                           data=_transfer_form_body(eid,
                                send_amount="250.00",
                                federal_tax=""))
    from app import Transfer
    with flask_app.app_context():
        t = Transfer.query.first()
        assert abs(t.federal_tax - 2.50) < 0.01


# ── Edit path also recomputes ──────────────────────────────────

def test_edit_transfer_recomputes_tax_from_new_amount(logged_in_client):
    sid = _store_id()
    eid = _seed_roster_row(sid)
    logged_in_client.post("/transfers/new",
                           data=_transfer_form_body(eid, send_amount="500.00"))
    from app import Transfer
    with flask_app.app_context():
        tid = Transfer.query.first().id
    # Bump the amount to $800 — tax should follow to $8.00.
    logged_in_client.post(f"/transfers/{tid}/edit",
                          data=_transfer_form_body(eid,
                                send_amount="800.00",
                                federal_tax="0"))
    with flask_app.app_context():
        t = db.session.get(Transfer, tid)
        assert abs(t.send_amount - 800.00) < 0.01
        assert abs(t.federal_tax - 8.00) < 0.01


# ── Admin can configure a different rate per store ──────────────

def test_admin_can_change_federal_tax_rate(logged_in_client):
    # Submit the Store Info form with a custom rate of 2.5%.
    resp = logged_in_client.post("/admin/settings",
                                  data={
                                      "_tab": "store",
                                      "store_name": "Test Store",
                                      "email": "admin@test.com",
                                      "phone": "",
                                      "federal_tax_rate": "2.5",
                                  },
                                  follow_redirects=False)
    assert resp.status_code == 302
    from app import Store
    with flask_app.app_context():
        s = Store.query.filter_by(slug="test-store").first()
        assert abs(s.federal_tax_rate - 0.025) < 1e-9


def test_custom_rate_applies_to_new_transfers(logged_in_client):
    sid = _store_id()
    eid = _seed_roster_row(sid)
    # Admin sets 2%.
    logged_in_client.post("/admin/settings", data={
        "_tab": "store",
        "store_name": "Test Store",
        "email": "admin@test.com",
        "phone": "",
        "federal_tax_rate": "2",
    })
    logged_in_client.post("/transfers/new",
                           data=_transfer_form_body(eid, send_amount="500.00"))
    from app import Transfer
    with flask_app.app_context():
        t = Transfer.query.first()
        # 500 × 0.02 = 10.00.
        assert abs(t.federal_tax - 10.00) < 0.01


def test_rejects_rate_outside_0_100(logged_in_client):
    resp = logged_in_client.post("/admin/settings", data={
        "_tab": "store",
        "store_name": "Test Store",
        "email": "admin@test.com",
        "phone": "",
        "federal_tax_rate": "150",
    })
    # On validation error the form re-renders (200), not a redirect.
    assert resp.status_code == 200
    assert b"Enter a percent between 0 and 100" in resp.data


# ── UI: tax field is read-only on the transfer form ─────────────

def test_transfer_form_tax_field_is_readonly(logged_in_client):
    sid = _store_id()
    _seed_roster_row(sid)
    resp = logged_in_client.get("/transfers/new")
    assert resp.status_code == 200
    # The Federal Tax input has `readonly`. Match on the field name to be
    # specific.
    html = resp.data.decode("utf-8", errors="ignore")
    # Find the federal_tax input line and confirm `readonly` is there.
    start = html.find('name="federal_tax"')
    assert start != -1
    # Look within the surrounding ~200 chars for the attribute.
    assert "readonly" in html[max(0, start - 200):start + 200]
