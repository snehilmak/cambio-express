"""HTTP integration tests for `GET /api/v2/auth/activity`.

The activity feed returns every OperatorAuditLog + TransferAudit
row authored by the current user across every store they've
touched. Available to every authed role.
"""
from datetime import datetime

from tests._app import db, db_session
from tests.conftest import login_admin


def _seed_op_log(*, user_id: int, store_id: int,
                 action: str = "delete", target_type: str = "transfer",
                 summary: str = "", created_at: datetime | None = None):
    from api.Modules.Audit.Models import OperatorAuditLog
    row = OperatorAuditLog(
        store_id=store_id, user_id=user_id,
        action=action, target_type=target_type, target_id="1",
        target_label="Test target", summary=summary,
        user_name="Test User", user_role="admin",
        created_at=created_at or datetime.utcnow(),
    )
    db.session.add(row); db.session.commit()
    return row.id


def _seed_tx_audit(*, user_id: int, store_id: int,
                   transfer_id: int = 1, action: str = "created",
                   summary: str = "$100 to Maria",
                   created_at: datetime | None = None):
    from api.Modules.Audit.Models import TransferAudit
    row = TransferAudit(
        store_id=store_id, transfer_id=transfer_id, user_id=user_id,
        action=action, summary=summary,
        created_at=created_at or datetime.utcnow(),
    )
    db.session.add(row); db.session.commit()
    return row.id


# ── Auth gating ─────────────────────────────────────────────


def test_activity_requires_jwt(client):
    resp = client.get("/api/v2/auth/activity")
    assert resp.status_code == 401


# ── Happy path ──────────────────────────────────────────────


def test_activity_returns_my_rows(client, test_store_id, test_admin_id):
    """A row authored by the current user appears in the feed."""
    with db_session():
        _seed_op_log(
            user_id=test_admin_id, store_id=test_store_id,
            action="lock", target_type="daily_report",
            summary="Locked 2026-05-10",
        )
        _seed_tx_audit(
            user_id=test_admin_id, store_id=test_store_id,
            transfer_id=42, summary="$200 to Juan",
        )
    token = login_admin(client, test_store_id)
    resp = client.get(
        "/api/v2/auth/activity",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 2
    actions = {r["action"] for r in body["rows"]}
    assert actions == {"lock", "created"}


def test_activity_excludes_other_users_rows(
    client, test_store_id, test_admin_id,
):
    """A row authored by a DIFFERENT user must not appear in the
    current user's feed even though it's on the same store."""
    with db_session():
        from api.Modules.Auth.Models import User
        other = User(
            store_id=test_store_id, username="other@test.com",
            full_name="Other Admin", role="admin",
        )
        other.set_password("testpass123!")
        db.session.add(other); db.session.commit()
        other_id = other.id
        _seed_op_log(
            user_id=other_id, store_id=test_store_id,
            action="lock", target_type="daily_report",
            summary="Other user's action",
        )
    token = login_admin(client, test_store_id)
    body = client.get(
        "/api/v2/auth/activity",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["total"] == 0


def test_activity_attaches_store_name(client, test_store_id, test_admin_id):
    """Each row carries the human-readable store_name so multi-store
    users can disambiguate."""
    with db_session():
        _seed_op_log(
            user_id=test_admin_id, store_id=test_store_id,
            action="update", target_type="batch", summary="",
        )
    token = login_admin(client, test_store_id)
    rows = client.get(
        "/api/v2/auth/activity",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()["rows"]
    assert len(rows) == 1
    assert rows[0]["store_name"] == "Test Store"
    assert rows[0]["store_id"] == test_store_id


# ── Filters ─────────────────────────────────────────────────


def test_activity_target_filter(client, test_store_id, test_admin_id):
    with db_session():
        _seed_op_log(
            user_id=test_admin_id, store_id=test_store_id,
            action="lock", target_type="daily_report",
        )
        _seed_op_log(
            user_id=test_admin_id, store_id=test_store_id,
            action="create", target_type="batch",
        )
    token = login_admin(client, test_store_id)
    rows = client.get(
        "/api/v2/auth/activity?target=batch",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()["rows"]
    assert len(rows) == 1
    assert rows[0]["target_type"] == "batch"


def test_activity_target_filter_for_transfer_includes_tx_audit(
    client, test_store_id, test_admin_id,
):
    """When the operator picks target=transfer the TransferAudit
    feed must be included (it's the transfer-only audit table)."""
    with db_session():
        _seed_op_log(
            user_id=test_admin_id, store_id=test_store_id,
            action="lock", target_type="daily_report",
        )
        _seed_tx_audit(
            user_id=test_admin_id, store_id=test_store_id,
            transfer_id=7, summary="$50",
        )
    token = login_admin(client, test_store_id)
    rows = client.get(
        "/api/v2/auth/activity?target=transfer",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()["rows"]
    sources = {r["source"] for r in rows}
    assert "transfer" in sources


def test_activity_target_filter_for_nonref_suppresses_tx_audit(
    client, test_store_id, test_admin_id,
):
    """target=batch (a non-transfer target) suppresses TransferAudit
    rows even when the user has them."""
    with db_session():
        _seed_op_log(
            user_id=test_admin_id, store_id=test_store_id,
            action="create", target_type="batch",
        )
        _seed_tx_audit(
            user_id=test_admin_id, store_id=test_store_id,
            transfer_id=7, summary="$50",
        )
    token = login_admin(client, test_store_id)
    rows = client.get(
        "/api/v2/auth/activity?target=batch",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()["rows"]
    assert all(r["source"] != "transfer" for r in rows)


def test_activity_action_filter(client, test_store_id, test_admin_id):
    with db_session():
        _seed_op_log(
            user_id=test_admin_id, store_id=test_store_id, action="lock",
        )
        _seed_op_log(
            user_id=test_admin_id, store_id=test_store_id, action="unlock",
        )
    token = login_admin(client, test_store_id)
    rows = client.get(
        "/api/v2/auth/activity?action=lock",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()["rows"]
    assert len(rows) == 1
    assert rows[0]["action"] == "lock"


# ── Ordering + pagination ───────────────────────────────────


def test_activity_ordered_newest_first(
    client, test_store_id, test_admin_id,
):
    from datetime import timedelta
    old = datetime.utcnow() - timedelta(days=5)
    new = datetime.utcnow()
    with db_session():
        _seed_op_log(
            user_id=test_admin_id, store_id=test_store_id,
            action="old", created_at=old,
        )
        _seed_op_log(
            user_id=test_admin_id, store_id=test_store_id,
            action="new", created_at=new,
        )
    token = login_admin(client, test_store_id)
    rows = client.get(
        "/api/v2/auth/activity",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()["rows"]
    assert rows[0]["action"] == "new"
    assert rows[-1]["action"] == "old"


def test_activity_pagination_caps_per_page_at_50(
    client, test_store_id, test_admin_id,
):
    """Per-page is fixed at 50; a user with 60 rows gets 50 on
    page=1 and the remaining 10 on page=2."""
    with db_session():
        for i in range(60):
            _seed_op_log(
                user_id=test_admin_id, store_id=test_store_id,
                action=f"a{i}",
            )
    token = login_admin(client, test_store_id)
    p1 = client.get(
        "/api/v2/auth/activity?page=1",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    p2 = client.get(
        "/api/v2/auth/activity?page=2",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert p1["per_page"] == 50
    assert len(p1["rows"]) == 50
    assert len(p2["rows"]) == 10
    assert p1["total"] == 60
    assert p1["total_pages"] == 2
