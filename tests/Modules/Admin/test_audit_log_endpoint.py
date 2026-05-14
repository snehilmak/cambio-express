"""HTTP integration tests for the admin audit-log endpoint.

Powers /app/admin/audit-log. Mirrors the legacy Jinja
/admin/audit-log Flask route's filter + pagination contract:
target / action / user query params, page is 1-based, per_page
is 50.
"""
from datetime import datetime, timedelta
from tests._app import db, db_session


def _login(client_, store_id):
    resp = client_.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


def _seed_op_row(store_id, *, action="lock", target_type="daily_report",
                 user_id=None, ts=None):
    """Insert an OperatorAuditLog row directly."""
    from api.Modules.Audit.Models import OperatorAuditLog
    from tests._app import db
    row = OperatorAuditLog(
        store_id=store_id, action=action,
        target_type=target_type, target_id="1",
        target_label="Test target", user_id=user_id,
        user_name="Tester", user_role="admin",
        summary="seeded by tests",
        created_at=ts or datetime.utcnow(),
    )
    db.session.add(row); db.session.commit()
    return row.id


def _seed_tx_row(store_id, *, action="create", user_id=None,
                 transfer_id=1, ts=None):
    """Insert a TransferAudit row directly."""
    from api.Modules.Audit.Models import TransferAudit
    from tests._app import db
    row = TransferAudit(
        store_id=store_id, transfer_id=transfer_id,
        action=action, user_id=user_id,
        employee_name="Test Cashier",
        summary="Created transfer #1",
        created_at=ts or datetime.utcnow(),
    )
    db.session.add(row); db.session.commit()
    return row.id


# ── auth gating ─────────────────────────────────────────────


def test_audit_log_requires_jwt(client):
    resp = client.get("/api/v2/admin/audit-log")
    assert resp.status_code == 401


def test_audit_log_rejects_superadmin(client):
    """Superadmin JWT carries no store scope — the feed needs a
    store_id, so it 403s."""
    from tests.conftest import login_superadmin
    token = login_superadmin(client)
    resp = client.get(
        "/api/v2/admin/audit-log",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── empty + happy paths ─────────────────────────────────────


def test_audit_log_empty_store_returns_zero_rows(
    client, test_store_id,
):
    """A brand-new store with no audit history returns an empty
    feed and total=0 — but still a valid envelope with the
    user-roster dropdown populated."""
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/admin/audit-log",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["rows"] == []
    assert body["total"] == 0
    assert body["page"] == 1
    assert body["per_page"] == 50
    assert body["total_pages"] == 1
    # The seeded admin@test.com user should be in the dropdown.
    assert any(
        u["label"] in {"admin@test.com", "Test Admin"}
        or u["role"] == "admin"
        for u in body["store_users"]
    )


def test_audit_log_merges_op_and_tx_feeds(
    client, test_store_id,
):
    with db_session():
        _seed_op_row(test_store_id, action="lock")
        _seed_tx_row(test_store_id, action="create")
    token = _login(client, test_store_id)
    body = client.get(
        "/api/v2/admin/audit-log",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["total"] == 2
    sources = {r["source"] for r in body["rows"]}
    assert sources == {"operator", "transfer"}


def test_audit_log_orders_newest_first(
    client, test_store_id,
):
    base = datetime.utcnow()
    with db_session():
        _seed_op_row(test_store_id, action="lock", ts=base - timedelta(days=2))
        _seed_op_row(test_store_id, action="unlock", ts=base)
    token = _login(client, test_store_id)
    body = client.get(
        "/api/v2/admin/audit-log",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["rows"][0]["action"] == "unlock"
    assert body["rows"][1]["action"] == "lock"


# ── filters ─────────────────────────────────────────────────


def test_audit_log_target_filter_drops_non_matching(
    client, test_store_id,
):
    """`?target=batch` should drop daily_report rows AND suppress
    the entire transfer feed (TransferAudit is transfer-only)."""
    with db_session():
        _seed_op_row(test_store_id, target_type="daily_report")
        _seed_op_row(test_store_id, target_type="batch")
        _seed_tx_row(test_store_id)
    token = _login(client, test_store_id)
    body = client.get(
        "/api/v2/admin/audit-log?target=batch",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["total"] == 1
    assert body["rows"][0]["target_type"] == "batch"


def test_audit_log_target_transfer_keeps_transfer_feed(
    client, test_store_id,
):
    """`?target=transfer` keeps only transfer-flavored rows
    (TransferAudit + OperatorAuditLog with target_type=transfer)."""
    with db_session():
        _seed_op_row(test_store_id, target_type="batch")
        _seed_op_row(test_store_id, target_type="transfer")
        _seed_tx_row(test_store_id)
    token = _login(client, test_store_id)
    body = client.get(
        "/api/v2/admin/audit-log?target=transfer",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["total"] == 2  # one OperatorAuditLog + one TransferAudit


def test_audit_log_action_filter(client, test_store_id):
    with db_session():
        _seed_op_row(test_store_id, action="lock")
        _seed_op_row(test_store_id, action="unlock")
    token = _login(client, test_store_id)
    body = client.get(
        "/api/v2/admin/audit-log?action=lock",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["total"] == 1
    assert body["rows"][0]["action"] == "lock"


def test_audit_log_user_filter(client, test_store_id):
    """A `?user=` value targets a specific User.id."""
    from api.Modules.Tenancy.Models import User
    from tests._app import db
    with db_session():
        u = User(
            store_id=test_store_id, username="extra@test.com",
            full_name="Extra User", role="admin",
        )
        u.set_password("p")
        db.session.add(u); db.session.commit()
        uid = u.id
        _seed_op_row(test_store_id, user_id=uid)
        _seed_op_row(test_store_id, user_id=None)
    token = _login(client, test_store_id)
    body = client.get(
        f"/api/v2/admin/audit-log?user={uid}",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["total"] == 1


def test_audit_log_garbage_user_filter_silently_ignored(
    client, test_store_id,
):
    """A non-numeric user filter is treated as no filter — matches
    legacy behavior (don't 422 on operator typos)."""
    with db_session():
        _seed_op_row(test_store_id)
    token = _login(client, test_store_id)
    body = client.get(
        "/api/v2/admin/audit-log?user=not-a-number",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["total"] == 1


# ── pagination ──────────────────────────────────────────────


def test_audit_log_paginates_at_50_per_page(
    client, test_store_id,
):
    with db_session():
        # 51 rows: 50 fit on page 1, 1 spills to page 2.
        for i in range(51):
            _seed_op_row(
                test_store_id, action="lock",
                ts=datetime.utcnow() - timedelta(seconds=i),
            )
    token = _login(client, test_store_id)
    p1 = client.get(
        "/api/v2/admin/audit-log?page=1",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    p2 = client.get(
        "/api/v2/admin/audit-log?page=2",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert p1["total"] == 51
    assert len(p1["rows"]) == 50
    assert p1["total_pages"] == 2
    assert len(p2["rows"]) == 1


# ── Flask redirect ──────────────────────────────────────────


def test_legacy_admin_audit_log_redirects_to_app(
    logged_in_client,
):
    resp = logged_in_client.get(
        "/admin/audit-log", follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["Location"].startswith("/app/admin/audit-log")


def test_legacy_admin_audit_log_preserves_query_string(
    logged_in_client,
):
    resp = logged_in_client.get(
        "/admin/audit-log?action=lock&page=2", follow_redirects=False,
    )
    assert resp.status_code == 301
    location = resp.headers["Location"]
    assert "action=lock" in location
    assert "page=2" in location
