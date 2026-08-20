"""The tickets-only "support" platform role.

Covers the four pillars of the role:

  1. **Creation** — POST /superadmin/platform-users mints a
     store-less support login. Superadmin only, audited,
     globally-unique username.
  2. **Login** — password only (no TOTP hop) and a HARD 7-day
     refresh-chain lifetime (vs 14 days for everyone else).
  3. **Scope** — full access to the Support module (tickets, staff
     replies, superadmin audit sink), 403 everywhere else on the
     platform surface.
  4. **Claiming** — claim/release marks who's working a ticket so
     the rest of the team sees it; support can't take over another
     person's claim, superadmin can.
"""
import pytest

from tests._app import db, db_session
from tests.conftest import login_admin, login_superadmin


SUPPORT_PASSWORD = "supportpass123!"


@pytest.fixture
def sa_headers(client):
    return {"Authorization": f"Bearer {login_superadmin(client)}"}


@pytest.fixture
def admin_headers(client):
    with db_session():
        from api.Modules.Tenancy.Models import Store
        store_id = db.session.query(Store).first().id
    return {"Authorization": f"Bearer {login_admin(client, store_id)}"}


def _create_support_user(client, sa_headers, username="support-ana"):
    resp = client.post(
        "/api/v2/superadmin/platform-users", headers=sa_headers,
        json={
            "username": username,
            "full_name": "Ana Support",
            "email": f"{username}@example.com",
            "password": SUPPORT_PASSWORD,
        },
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.json()["user"]


def _login_support(client, username="support-ana"):
    resp = client.post(
        "/api/v2/auth/login",
        json={
            "username": username, "password": SUPPORT_PASSWORD,
            "store_id": None,
        },
    )
    assert resp.status_code == 200, resp.get_json()
    body = resp.json()
    # Password-only: no TOTP hop for the support role.
    assert not body.get("requires_totp")
    assert body["role"] == "support"
    return body


def _make_ticket(client, headers, subject="Support-role test"):
    resp = client.post("/api/v2/tickets", headers=headers, json={
        "category": "question", "subject": subject, "body": "Help please.",
    })
    assert resp.status_code == 201
    return resp.json()["ticket"]["id"]


class TestCreation:
    def test_superadmin_creates_support_login(self, client, sa_headers):
        user = _create_support_user(client, sa_headers)
        assert user["role"] == "support"
        with db_session():
            from api.Modules.Audit.Models import SuperadminAuditLog
            from api.Modules.Tenancy.Models import User
            row = db.session.get(User, user["id"])
            assert row.store_id is None
            assert row.role == "support"
            audit = (
                db.session.query(SuperadminAuditLog)
                .filter_by(
                    action="create_platform_user",
                    target_id=str(user["id"]),
                )
                .first()
            )
            assert audit is not None

    def test_store_admin_cannot_create(self, client, admin_headers):
        resp = client.post(
            "/api/v2/superadmin/platform-users", headers=admin_headers,
            json={"username": "sneaky", "password": SUPPORT_PASSWORD},
        )
        assert resp.status_code == 403

    def test_username_collision_rejected(self, client, sa_headers):
        _create_support_user(client, sa_headers, username="support-dup")
        resp = client.post(
            "/api/v2/superadmin/platform-users", headers=sa_headers,
            json={"username": "support-dup", "password": SUPPORT_PASSWORD},
        )
        assert resp.status_code == 409

    def test_collision_with_store_username_rejected(
        self, client, sa_headers, admin_headers,
    ):
        """Cross-store login is first-match-by-username, so a support
        login shadowing a store user's name must be refused."""
        with db_session():
            from api.Modules.Tenancy.Models import User
            existing = db.session.query(User).filter(
                User.store_id.isnot(None),
            ).first().username
        resp = client.post(
            "/api/v2/superadmin/platform-users", headers=sa_headers,
            json={"username": existing, "password": SUPPORT_PASSWORD},
        )
        assert resp.status_code == 409


class TestLoginAndExpiry:
    def test_password_only_login(self, client, sa_headers):
        _create_support_user(client, sa_headers)
        body = _login_support(client)
        assert "platform.support" in (body.get("permissions") or [])

    def test_refresh_chain_is_seven_days(self, client, sa_headers):
        """The support refresh row expires 7 days after login — and
        reuse() never extends it, so that IS the absolute window."""
        from datetime import timedelta
        user = _create_support_user(client, sa_headers, "support-ttl")
        _login_support(client, "support-ttl")
        with db_session():
            from api.Modules.Auth.Models import RefreshToken
            row = (
                db.session.query(RefreshToken)
                .filter_by(user_id=user["id"])
                .order_by(RefreshToken.id.desc())
                .first()
            )
            assert row is not None
            lifetime = row.expires_at - row.created_at
            assert lifetime == timedelta(days=7)

    def test_admin_refresh_chain_stays_fourteen_days(
        self, client, admin_headers,
    ):
        from datetime import timedelta
        with db_session():
            from api.Modules.Auth.Models import RefreshToken
            row = (
                db.session.query(RefreshToken)
                .order_by(RefreshToken.id.desc())
                .first()
            )
            assert row is not None
            assert row.expires_at - row.created_at == timedelta(days=14)


class TestScope:
    @pytest.fixture
    def support_headers(self, client, sa_headers):
        _create_support_user(client, sa_headers, "support-scope")
        body = _login_support(client, "support-scope")
        return {"Authorization": f"Bearer {body['access_token']}"}

    def test_support_sees_all_tickets(
        self, client, admin_headers, support_headers,
    ):
        tid = _make_ticket(client, admin_headers)
        resp = client.get("/api/v2/tickets/all", headers=support_headers)
        assert resp.status_code == 200
        assert any(t["id"] == tid for t in resp.json()["tickets"])
        # The bare /tickets list delegates to /all for platform staff.
        resp = client.get("/api/v2/tickets", headers=support_headers)
        assert resp.status_code == 200

    def test_support_reply_is_staff_and_audited(
        self, client, admin_headers, support_headers,
    ):
        tid = _make_ticket(client, admin_headers)
        resp = client.post(
            f"/api/v2/tickets/{tid}/messages", headers=support_headers,
            json={"body": "Support here, looking into it."},
        )
        assert resp.status_code == 201
        thread = client.get(
            f"/api/v2/tickets/{tid}/messages", headers=admin_headers,
        ).json()
        assert thread["messages"][-1]["author_kind"] == "staff"
        detail = client.get(
            f"/api/v2/tickets/{tid}", headers=admin_headers,
        ).json()["ticket"]
        assert detail["admin_reply"] == "Support here, looking into it."
        with db_session():
            from api.Modules.Audit.Models import SuperadminAuditLog
            row = (
                db.session.query(SuperadminAuditLog)
                .filter_by(
                    action="reply_support_ticket", target_id=str(tid),
                )
                .first()
            )
            assert row is not None

    def test_support_can_update_status(
        self, client, admin_headers, support_headers,
    ):
        tid = _make_ticket(client, admin_headers)
        resp = client.put(
            f"/api/v2/tickets/{tid}", headers=support_headers,
            json={"status": "in_progress"},
        )
        assert resp.status_code == 200
        assert resp.json()["ticket"]["status"] == "in_progress"

    def test_support_blocked_from_superadmin_surface(
        self, client, support_headers,
    ):
        for path in (
            "/api/v2/superadmin/stores",
            "/api/v2/superadmin/users",
            "/api/v2/superadmin/audit-log",
        ):
            assert client.get(
                path, headers=support_headers,
            ).status_code == 403, path
        resp = client.post(
            "/api/v2/superadmin/platform-users", headers=support_headers,
            json={"username": "support-two", "password": SUPPORT_PASSWORD},
        )
        assert resp.status_code == 403

    def test_support_cannot_create_tickets(self, client, support_headers):
        """No store scope → no ticket creation (support answers
        tickets, it doesn't file them)."""
        resp = client.post(
            "/api/v2/tickets", headers=support_headers,
            json={
                "category": "question", "subject": "x", "body": "y",
            },
        )
        assert resp.status_code in (400, 403)


class TestClaiming:
    @pytest.fixture
    def support_headers(self, client, sa_headers):
        _create_support_user(client, sa_headers, "support-claim")
        body = _login_support(client, "support-claim")
        return {"Authorization": f"Bearer {body['access_token']}"}

    @pytest.fixture
    def support2_headers(self, client, sa_headers):
        _create_support_user(client, sa_headers, "support-claim2")
        body = _login_support(client, "support-claim2")
        return {"Authorization": f"Bearer {body['access_token']}"}

    def test_claim_marks_owner_and_audits(
        self, client, admin_headers, support_headers,
    ):
        tid = _make_ticket(client, admin_headers)
        resp = client.post(
            f"/api/v2/tickets/{tid}/claim", headers=support_headers,
        )
        assert resp.status_code == 200
        t = resp.json()["ticket"]
        assert t["assigned_to_name"] == "Ana Support"
        assert t["assigned_to_user_id"] is not None
        with db_session():
            from api.Modules.Audit.Models import SuperadminAuditLog
            row = (
                db.session.query(SuperadminAuditLog)
                .filter_by(
                    action="claim_support_ticket", target_id=str(tid),
                )
                .first()
            )
            assert row is not None

    def test_support_cannot_steal_claim(
        self, client, admin_headers, support_headers, support2_headers,
    ):
        tid = _make_ticket(client, admin_headers)
        client.post(f"/api/v2/tickets/{tid}/claim", headers=support_headers)
        resp = client.post(
            f"/api/v2/tickets/{tid}/claim", headers=support2_headers,
        )
        assert resp.status_code == 409

    def test_superadmin_can_reassign(
        self, client, admin_headers, support_headers, sa_headers,
    ):
        tid = _make_ticket(client, admin_headers)
        client.post(f"/api/v2/tickets/{tid}/claim", headers=support_headers)
        resp = client.post(f"/api/v2/tickets/{tid}/claim", headers=sa_headers)
        assert resp.status_code == 200

    def test_release_own_claim(self, client, admin_headers, support_headers):
        tid = _make_ticket(client, admin_headers)
        client.post(f"/api/v2/tickets/{tid}/claim", headers=support_headers)
        resp = client.post(
            f"/api/v2/tickets/{tid}/release", headers=support_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["ticket"]["assigned_to_user_id"] is None

    def test_release_unclaimed_is_409(
        self, client, admin_headers, support_headers,
    ):
        tid = _make_ticket(client, admin_headers)
        resp = client.post(
            f"/api/v2/tickets/{tid}/release", headers=support_headers,
        )
        assert resp.status_code == 409

    def test_store_admin_cannot_claim(self, client, admin_headers):
        tid = _make_ticket(client, admin_headers)
        resp = client.post(
            f"/api/v2/tickets/{tid}/claim", headers=admin_headers,
        )
        assert resp.status_code == 403


class TestNotificationRecipients:
    def test_support_joins_platform_recipients(self, client, sa_headers):
        _create_support_user(client, sa_headers, "support-notify")
        with db_session():
            from api.Modules.Notifications.Services.ticket_updates import (
                platform_recipients,
            )
            names = {
                u.username for u in platform_recipients(db.session)
            }
            assert "support-notify" in names
