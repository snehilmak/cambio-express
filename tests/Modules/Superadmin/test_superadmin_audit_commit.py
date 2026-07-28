"""Regression tests for the superadmin audit-commit ordering bug
(HANDOFF §3 / "PR D").

Every superadmin mutation MUST leave a `SuperadminAuditLog` row behind
(CLAUDE.md invariant #7). The bug these tests lock down: a batch of
routes called `db.commit()` *before* adding the audit row — or added
it with no commit at all — so `get_db()`'s `finally: db.close()`
rolled the audit entry back. The mutation landed; the audit trail
silently didn't.

Each test performs the mutation over HTTP (so the real `get_db()`
request lifecycle runs, including the close-on-teardown that exposed
the bug) and asserts the matching audit row is durably persisted in a
*fresh* session afterward.

The fix routes every mutation through `_audit_and_commit(...)` so the
audit row and the state change commit together. If any route regresses
to the commit-then-audit form, the corresponding test here goes red.
"""
from datetime import datetime, timedelta

import pytest

from tests._app import db, db_session
from tests.conftest import login_superadmin


@pytest.fixture
def sa_token(client):
    return login_superadmin(client)


@pytest.fixture
def sa_headers(sa_token):
    return {"Authorization": f"Bearer {sa_token}"}


def _seed_user(store_id, *, role="admin", email="", with_2fa=False):
    """Insert a non-superadmin User in `store_id` and return its id.

    Opens its own committed transaction so the row is visible to the
    request under test (which runs in a separate session)."""
    from api.Modules.Tenancy.Models import User
    stamp = datetime.utcnow().timestamp()
    with db_session():
        u = User(
            username=f"audit-target-{store_id}-{stamp}@test.com",
            role=role,
            full_name="Audit Target",
            email=email,
            store_id=store_id,
        )
        u.set_password("targetpass123!")
        if with_2fa:
            u.totp_secret = "JBSWY3DPEHPK3PXP"
            u.totp_enrolled_at = datetime.utcnow()
        db.session.add(u)
        db.session.commit()
        return u.id


def _audit_rows(action, target_id=None):
    """Return persisted SuperadminAuditLog rows for `action` (optionally
    filtered by target_id), read in a fresh session."""
    from api.Modules.Audit.Models import SuperadminAuditLog
    with db_session():
        q = (
            db.session.query(SuperadminAuditLog)
              .filter(SuperadminAuditLog.action == action)
        )
        if target_id is not None:
            q = q.filter(SuperadminAuditLog.target_id == str(target_id))
        return q.all()


# ── User-management routes ─────────────────────────────────


class TestUserMutationsAudit:
    def test_change_user_role_persists_audit(self, client, sa_headers, test_store_id):
        uid = _seed_user(test_store_id, role="employee")
        resp = client.post(
            f"/api/v2/superadmin/users/{uid}/change-role",
            headers=sa_headers, json={"role": "admin"},
        )
        assert resp.status_code == 200
        rows = _audit_rows("change_user_role", uid)
        assert len(rows) == 1

    def test_toggle_user_active_persists_audit(self, client, sa_headers, test_store_id):
        uid = _seed_user(test_store_id)
        resp = client.post(
            f"/api/v2/superadmin/users/{uid}/toggle-active",
            headers=sa_headers,
        )
        assert resp.status_code == 200
        # Seeded user starts active → this disables it.
        rows = _audit_rows("disable_user", uid)
        assert len(rows) == 1

    def test_reset_2fa_persists_audit(self, client, sa_headers, test_store_id):
        uid = _seed_user(test_store_id, with_2fa=True)
        resp = client.post(
            f"/api/v2/superadmin/users/{uid}/reset-2fa",
            headers=sa_headers,
        )
        assert resp.status_code == 200
        rows = _audit_rows("reset_2fa", uid)
        assert len(rows) == 1

    def test_force_password_reset_persists_audit(self, client, sa_headers, test_store_id):
        uid = _seed_user(test_store_id)
        resp = client.post(
            f"/api/v2/superadmin/users/{uid}/force-password-reset",
            headers=sa_headers,
        )
        assert resp.status_code == 200
        rows = _audit_rows("force_password_reset", uid)
        assert len(rows) == 1

    def test_revoke_sessions_persists_audit(self, client, sa_headers, test_store_id):
        uid = _seed_user(test_store_id)
        resp = client.post(
            f"/api/v2/superadmin/users/{uid}/revoke-sessions",
            headers=sa_headers,
        )
        assert resp.status_code == 200
        rows = _audit_rows("revoke_user_sessions", uid)
        assert len(rows) == 1

    def test_impersonate_persists_audit(self, client, sa_headers, test_store_id):
        uid = _seed_user(test_store_id)
        resp = client.post(
            f"/api/v2/superadmin/impersonate/{uid}",
            headers=sa_headers,
        )
        assert resp.status_code == 200
        rows = _audit_rows("impersonate_user", uid)
        assert len(rows) == 1


# ── Store-action routes ────────────────────────────────────


class TestStoreMutationsAudit:
    def test_extend_trial_persists_audit(self, client, sa_headers, test_store_id):
        resp = client.post(
            f"/api/v2/superadmin/stores/{test_store_id}/extend-trial",
            headers=sa_headers, json={"days": 7},
        )
        assert resp.status_code == 200
        rows = _audit_rows("extend_trial", test_store_id)
        assert len(rows) == 1

    def test_toggle_store_active_persists_audit(self, client, sa_headers, test_store_id):
        resp = client.post(
            f"/api/v2/superadmin/stores/{test_store_id}/toggle-active",
            headers=sa_headers,
        )
        assert resp.status_code == 200
        # Seeded store starts active → this disables it.
        rows = _audit_rows("disable_store", test_store_id)
        assert len(rows) == 1

    def test_bulk_action_persists_audit(self, client, sa_headers, test_store_id):
        resp = client.post(
            "/api/v2/superadmin/bulk-action",
            headers=sa_headers,
            json={"store_ids": [test_store_id], "action": "extend_trial", "days": 5},
        )
        assert resp.status_code == 200
        rows = _audit_rows("bulk_extend_trial", test_store_id)
        assert len(rows) == 1

    def test_email_store_persists_audit(self, client, sa_headers, test_store_id):
        # email_store needs at least one admin with an email address,
        # else it 422s before the audit. Seed one.
        _seed_user(test_store_id, role="admin", email="reachable@test.com")
        resp = client.post(
            f"/api/v2/superadmin/stores/{test_store_id}/email",
            headers=sa_headers,
            json={"subject": "Heads up", "message": "Test message body."},
        )
        assert resp.status_code == 200
        rows = _audit_rows("email_store", test_store_id)
        assert len(rows) == 1


# ── Platform-wide routes ───────────────────────────────────


class TestPlatformMutationsAudit:
    def test_set_maintenance_persists_audit(self, client, sa_headers):
        # `set_setting` commits the settings internally; the audit row
        # is added afterward, so it needs its own commit — the exact
        # shape of the bug for this route.
        resp = client.post(
            "/api/v2/superadmin/maintenance",
            headers=sa_headers,
            json={"enabled": True, "message": "Back at 9pm CT"},
        )
        assert resp.status_code == 200
        rows = _audit_rows("maintenance_mode_toggle", "platform")
        assert len(rows) == 1

    def test_update_permissions_persists_audit(self, client, sa_headers):
        # Fetch the live matrix, flip one admin action, and PUT it back
        # so `affected_roles` is non-empty (the session-revocation +
        # audit both have to commit in one transaction).
        got = client.get("/api/v2/superadmin/permissions", headers=sa_headers)
        assert got.status_code == 200
        matrix = got.json()["matrix"]
        admin = matrix["admin"]
        resource = next(iter(admin))
        action = next(iter(admin[resource]))
        admin[resource][action] = not admin[resource][action]
        resp = client.put(
            "/api/v2/superadmin/permissions",
            headers=sa_headers, json={"matrix": {"admin": admin}},
        )
        assert resp.status_code == 200
        rows = _audit_rows("update_permissions", "role_permission")
        assert len(rows) >= 1
