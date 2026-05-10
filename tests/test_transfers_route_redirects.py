"""Redirect-contract tests for the legacy `/transfers` Flask URLs.

The list view, create form, edit form, and hard-delete handler all
moved to React (`/app/transfers[/...]`) backed by `/api/v2/transfers`.
Behaviours the legacy test suite pinned (sort + filter + pagination,
federal-tax recompute, employee-roster validation, customer upsert,
TransferAudit history, OperatorAuditLog on delete, cross-store 404)
are exercised against the JSON endpoints in
`tests/Modules/Transfers/test_transfers_controllers.py` +
`tests/Modules/Transfers/test_get_by_id_endpoint.py`.

These tests guard:
  - Each legacy URL returns a 301 to the right `/app/*` target.
  - Auth gate (login_required + admin_required) runs *before* the
    redirect, so anonymous + non-admin requests still bounce to
    login (NOT to the SPA).
  - Query strings on the list view are preserved — minus the legacy
    `?partial=1` AJAX-only marker.
  - The new DELETE /api/v2/transfers/<id> endpoint covers the hard-
    delete contract that the legacy /transfers/<tid>/delete used to
    own (admin-role gate, cross-store 404, OperatorAuditLog row).
"""
from datetime import date

from app import app as flask_app, db


def _admin_jwt(client, store_id):
    resp = client.post(
        "/api/v2/auth/login",
        json={"username": "admin@test.com",
              "password": "testpass123!",
              "store_id": store_id},
    )
    return resp.get_json()["access_token"]


# ── Auth gate (runs BEFORE the 301) ─────────────────────────


def test_transfers_requires_login(client):
    resp = client.get("/transfers", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_transfers_no_store_bounces_to_dashboard(client):
    """The legacy guard ("Select a store first" → /dashboard)
    survives — without a store_id session claim the SPA's
    /api/v2/transfers would 403 anyway, so /dashboard is the
    cleaner fallback."""
    from app import User
    with flask_app.app_context():
        owner = User(username="owner_for_xfers@test.com",
                     full_name="Owner", role="owner", store_id=None)
        owner.set_password("p")
        db.session.add(owner); db.session.commit()
        oid = owner.id
    with client.session_transaction() as sess:
        sess["user_id"] = oid
        sess["role"] = "owner"
        sess["store_id"] = None
    resp = client.get("/transfers", follow_redirects=False)
    # Owner without a store → /dashboard.
    assert resp.status_code == 302
    loc = resp.headers["Location"]
    assert "/dashboard" in loc or "/login" in loc


# ── 301 contract: list ──────────────────────────────────────


def test_transfers_list_redirects_to_spa(logged_in_client):
    resp = logged_in_client.get("/transfers", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/transfers"


def test_transfers_list_preserves_filter_and_sort_query_string(logged_in_client):
    resp = logged_in_client.get(
        "/transfers?company=Intermex&status=Sent&sort=amount&dir=desc",
        follow_redirects=False,
    )
    assert resp.status_code == 301
    loc = resp.headers["Location"]
    assert loc.startswith("/app/transfers")
    assert "company=Intermex" in loc
    assert "status=Sent" in loc
    assert "sort=amount" in loc
    assert "dir=desc" in loc


def test_transfers_list_strips_partial_marker(logged_in_client):
    """The legacy `?partial=1` flag was an AJAX-only contract for
    the deleted Jinja live-search; the SPA never sends it. Strip
    it on the redirect target so a stale browser cache isn't
    forwarded a no-op param."""
    resp = logged_in_client.get(
        "/transfers?partial=1&q=foo", follow_redirects=False,
    )
    assert resp.status_code == 301
    loc = resp.headers["Location"]
    assert "partial=1" not in loc
    assert "q=foo" in loc


# ── 301 contract: create ────────────────────────────────────


def test_new_transfer_get_redirects_to_spa(logged_in_client):
    resp = logged_in_client.get("/transfers/new", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/transfers/new"


def test_new_transfer_post_redirects_to_spa(logged_in_client):
    """Legacy form POSTs also 301. The SPA POSTs to /api/v2/transfers
    directly — the legacy form path is dead. Any in-flight Jinja
    submission lands the user on the SPA create page."""
    resp = logged_in_client.post(
        "/transfers/new",
        data={"sender_name": "X", "send_date": date.today().isoformat()},
        follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/transfers/new"


# ── 301 contract: edit ──────────────────────────────────────


def test_edit_transfer_get_redirects_to_spa(logged_in_client):
    resp = logged_in_client.get(
        "/transfers/42/edit", follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/transfers/42/edit"


def test_edit_transfer_post_redirects_to_spa(logged_in_client):
    resp = logged_in_client.post(
        "/transfers/42/edit", data={"send_amount": "100"},
        follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/transfers/42/edit"


# ── 301 contract: delete + API equivalent ───────────────────


def test_delete_transfer_post_redirects_to_list(logged_in_client):
    """The legacy /transfers/<tid>/delete POST 301s to /app/transfers.
    The actual hard-delete moved to DELETE /api/v2/transfers/<id> —
    see the API-side test below + tests/test_operator_audit.py for
    the audit-log row contract."""
    resp = logged_in_client.post(
        "/transfers/42/delete", follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/transfers"


def test_api_delete_transfer_round_trip(client, test_store_id):
    """DELETE /api/v2/transfers/<id> is the new hard-delete path.
    Admin role + store scope required, cross-store ID returns 404,
    successful delete returns 204 + appends an OperatorAuditLog row."""
    from app import Transfer, OperatorAuditLog, db
    with flask_app.app_context():
        t = Transfer(
            store_id=test_store_id, send_date=date.today(),
            sender_name="API Delete Test",
            recipient_name="Recipient",
            country="MX", confirm_number="DEL-API", company="Intermex",
            send_amount=500.0, fee=5.0, federal_tax=0.0, status="Sent",
        )
        db.session.add(t); db.session.commit()
        tid = t.id
    token = _admin_jwt(client, test_store_id)
    resp = client.delete(
        f"/api/v2/transfers/{tid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204
    with flask_app.app_context():
        # Row gone, audit row written.
        assert Transfer.query.get(tid) is None
        rows = OperatorAuditLog.query.filter_by(
            store_id=test_store_id,
            target_type="transfer", action="delete",
        ).all()
        assert len(rows) == 1
        assert "API Delete Test" in rows[0].target_label
        assert "DEL-API" in rows[0].summary


def test_api_delete_transfer_cross_store_404(client, test_store_id):
    """A different store's transfer ID returns 404 — opaque tenancy."""
    from app import Store, Transfer, db
    with flask_app.app_context():
        other = Store(name="Other XF", slug="other-xf", plan="basic")
        db.session.add(other); db.session.commit()
        other_id = other.id
        t = Transfer(
            store_id=other_id, send_date=date.today(),
            sender_name="OtherStore", recipient_name="X",
            country="MX", confirm_number="OTH", company="Intermex",
            send_amount=100.0, fee=1.0, federal_tax=0.0, status="Sent",
        )
        db.session.add(t); db.session.commit()
        other_tid = t.id
    token = _admin_jwt(client, test_store_id)
    resp = client.delete(
        f"/api/v2/transfers/{other_tid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_api_delete_transfer_employee_blocked(client, test_store_id):
    """Employees can't hard-delete (admin role required). The
    legacy form route was gated by @admin_required; the API path
    uses the same role check."""
    from tests.conftest import make_employee_client
    from app import User, Transfer, db
    with flask_app.app_context():
        t = Transfer(
            store_id=test_store_id, send_date=date.today(),
            sender_name="EmpBlock", recipient_name="X",
            country="MX", confirm_number="E1", company="Intermex",
            send_amount=50.0, fee=1.0, federal_tax=0.0, status="Sent",
        )
        db.session.add(t); db.session.commit()
        tid = t.id
    emp = make_employee_client(test_store_id)
    with emp.session_transaction() as sess:
        emp_uid = sess["user_id"]
    with flask_app.app_context():
        emp_username = User.query.filter_by(id=emp_uid).one().username
    login = client.post(
        "/api/v2/auth/login",
        json={"username": emp_username, "password": "x",
              "store_id": test_store_id},
    )
    emp_token = login.get_json()["access_token"]
    resp = client.delete(
        f"/api/v2/transfers/{tid}",
        headers={"Authorization": f"Bearer {emp_token}"},
    )
    assert resp.status_code == 403
    # Row still there.
    with flask_app.app_context():
        assert Transfer.query.get(tid) is not None
