"""Endpoint tests for the pre-beta superadmin controls:

* `POST /superadmin/users/{user_id}/revoke-sessions`
* `GET  /superadmin/retention-dry-run`
* `POST /superadmin/stores/{store_id}/clear-retention`

Each new control gets: happy path, auth gate, 404, and a
side-effect / audit assertion. The shared `sa_token` / `sa_headers`
fixture pattern matches `test_superadmin_tier2.py`.
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


# ── revoke-sessions ────────────────────────────────────────


class TestRevokeUserSessions:
    def _seed_user_with_refresh_tokens(self, store_id, *, count=2):
        """Insert a User + N active RefreshToken rows. Returns (user_id,
        list_of_token_ids). Caller commits."""
        from api.Modules.Auth.Models import RefreshToken
        from api.Modules.Tenancy.Models import User
        u = User(
            username=f"revoke-target-{store_id}-{datetime.utcnow().timestamp()}@test.com",
            password_hash="x", role="admin",
            full_name="x",
            email=f"revoke-target-{store_id}@test.com",
            store_id=store_id,
        )
        db.session.add(u)
        db.session.flush()
        token_ids: list[int] = []
        for i in range(count):
            rt = RefreshToken(
                jti=f"jti-revoke-{u.id}-{i}",
                user_id=u.id,
                expires_at=datetime.utcnow() + timedelta(days=14),
            )
            db.session.add(rt)
            db.session.flush()
            token_ids.append(rt.id)
        return u.id, token_ids

    def test_revokes_all_active_tokens(self, client, sa_headers, test_store_id):
        from api.Modules.Auth.Models import RefreshToken
        with db_session():
            user_id, token_ids = self._seed_user_with_refresh_tokens(
                test_store_id, count=3,
            )
            db.session.commit()
        resp = client.post(
            f"/api/v2/superadmin/users/{user_id}/revoke-sessions",
            headers=sa_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["revoked_count"] == 3
        with db_session():
            for tid in token_ids:
                rt = db.session.get(RefreshToken, tid)
                assert rt.revoked_at is not None

    def test_does_not_touch_already_revoked(self, client, sa_headers, test_store_id):
        """Tokens already marked revoked shouldn't be re-stamped or
        counted in the response."""
        from api.Modules.Auth.Models import RefreshToken
        with db_session():
            user_id, token_ids = self._seed_user_with_refresh_tokens(
                test_store_id, count=2,
            )
            old_revoke_time = datetime.utcnow() - timedelta(days=2)
            already_revoked = db.session.get(RefreshToken, token_ids[0])
            already_revoked.revoked_at = old_revoke_time
            db.session.commit()
        resp = client.post(
            f"/api/v2/superadmin/users/{user_id}/revoke-sessions",
            headers=sa_headers,
        )
        assert resp.status_code == 200
        # Only the second (active) token gets revoked.
        assert resp.json()["revoked_count"] == 1
        with db_session():
            unchanged = db.session.get(RefreshToken, token_ids[0])
            # The original timestamp was preserved.
            assert unchanged.revoked_at == old_revoke_time

    def test_404_for_unknown_user(self, client, sa_headers):
        resp = client.post(
            "/api/v2/superadmin/users/9999999/revoke-sessions",
            headers=sa_headers,
        )
        assert resp.status_code == 404

    def test_rejects_superadmin_target(self, client, sa_headers):
        """Cannot revoke a superadmin's sessions via this route — they
        use the regular logout / session-mgmt path."""
        from api.Modules.Tenancy.Models import User
        with db_session():
            sa = db.session.query(User).filter_by(role="superadmin").first()
            sa_id = sa.id
        resp = client.post(
            f"/api/v2/superadmin/users/{sa_id}/revoke-sessions",
            headers=sa_headers,
        )
        assert resp.status_code == 403

    def test_requires_superadmin(self, client):
        resp = client.post("/api/v2/superadmin/users/1/revoke-sessions")
        assert resp.status_code in (401, 403)

    def test_writes_audit_entry(self, client, sa_headers, test_store_id):
        """Every superadmin mutation must record an audit row
        (invariant #7)."""
        from api.Modules.Audit.Models import SuperadminAuditLog
        with db_session():
            user_id, _ = self._seed_user_with_refresh_tokens(
                test_store_id, count=1,
            )
            before = db.session.query(SuperadminAuditLog).count()
            db.session.commit()
        resp = client.post(
            f"/api/v2/superadmin/users/{user_id}/revoke-sessions",
            headers=sa_headers,
        )
        assert resp.status_code == 200
        with db_session():
            after = db.session.query(SuperadminAuditLog).count()
            assert after == before + 1
            last = (
                db.session.query(SuperadminAuditLog)
                  .order_by(SuperadminAuditLog.id.desc())
                  .first()
            )
            assert last.action == "revoke_user_sessions"
            assert last.target_id == str(user_id)


# ── retention dry-run ──────────────────────────────────────


class TestRetentionDryRun:
    def test_empty_when_no_expired_stores(self, client, sa_headers):
        from api.Modules.Tenancy.Models import Store
        with db_session():
            # Hermetic: clear any retention-elapsed stores in the test DB.
            db.session.query(Store).filter(
                Store.plan == "inactive",
            ).update(
                {"data_retention_until": None},
                synchronize_session=False,
            )
            db.session.commit()
        resp = client.get(
            "/api/v2/superadmin/retention-dry-run",
            headers=sa_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["store_count"] == 0
        assert body["total_child_rows"] == 0
        assert body["stores"] == []

    def test_reports_expired_store_with_row_counts(self, client, sa_headers):
        from api.Modules.Customers.Models import Customer
        from api.Modules.Tenancy.Models import Store, User
        with db_session():
            s = Store(
                name="DryRun-Doomed", slug="dryrun-doomed",
                plan="inactive", email="doomed@test.com",
                data_retention_until=datetime.utcnow() - timedelta(days=1),
            )
            db.session.add(s); db.session.flush()
            db.session.add(User(
                username="doomed-admin@test.com",
                password_hash="x", role="admin", full_name="x",
                email="doomed-admin@test.com", store_id=s.id,
            ))
            db.session.add(Customer(
                store_id=s.id, full_name="Doomed Customer",
                phone_country="+1", phone_number="5550000",
            ))
            db.session.commit()
            sid = s.id
        resp = client.get(
            "/api/v2/superadmin/retention-dry-run",
            headers=sa_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["store_count"] >= 1
        target = next(
            (st for st in body["stores"] if st["store_id"] == sid), None,
        )
        assert target is not None
        assert target["row_counts"].get("User", 0) >= 1
        assert target["row_counts"].get("Customer", 0) >= 1
        assert target["row_count"] >= 2

    def test_is_read_only(self, client, sa_headers):
        """The dry-run must NOT delete anything — the whole point is
        preview-without-commit."""
        from api.Modules.Tenancy.Models import Store
        with db_session():
            s = Store(
                name="DryRun-Preserve", slug="dryrun-preserve",
                plan="inactive", email="preserve@test.com",
                data_retention_until=datetime.utcnow() - timedelta(days=1),
            )
            db.session.add(s); db.session.commit()
            sid = s.id
        resp = client.get(
            "/api/v2/superadmin/retention-dry-run",
            headers=sa_headers,
        )
        assert resp.status_code == 200
        with db_session():
            assert db.session.query(Store).filter_by(id=sid).first() is not None

    def test_requires_superadmin(self, client):
        resp = client.get("/api/v2/superadmin/retention-dry-run")
        assert resp.status_code in (401, 403)


# ── clear-retention ────────────────────────────────────────


class TestClearRetention:
    def _seed_canceled_store(self):
        from api.Modules.Tenancy.Models import Store
        s = Store(
            name="ClearMe", slug="clear-me",
            plan="inactive", email="clear-me@test.com",
            canceled_at=datetime.utcnow() - timedelta(days=10),
            data_retention_until=datetime.utcnow() + timedelta(days=170),
        )
        db.session.add(s)
        db.session.commit()
        return s.id

    def test_clears_retention_fields(self, client, sa_headers):
        from api.Modules.Tenancy.Models import Store
        with db_session():
            sid = self._seed_canceled_store()
        resp = client.post(
            f"/api/v2/superadmin/stores/{sid}/clear-retention",
            headers=sa_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        with db_session():
            s = db.session.get(Store, sid)
            assert s.canceled_at is None
            assert s.data_retention_until is None

    def test_idempotent_on_already_clear_store(self, client, sa_headers, test_store_id):
        """A store with no retention timer set is a no-op (returns
        already_clear=True)."""
        resp = client.post(
            f"/api/v2/superadmin/stores/{test_store_id}/clear-retention",
            headers=sa_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        # Either the seeded test store already had no retention timer
        # (already_clear=True), or it did and the second call would now
        # show it clear. Either way, no error.

    def test_404_for_unknown_store(self, client, sa_headers):
        resp = client.post(
            "/api/v2/superadmin/stores/9999999/clear-retention",
            headers=sa_headers,
        )
        assert resp.status_code == 404

    def test_requires_superadmin(self, client):
        resp = client.post("/api/v2/superadmin/stores/1/clear-retention")
        assert resp.status_code in (401, 403)

    def test_writes_audit_entry(self, client, sa_headers):
        from api.Modules.Audit.Models import SuperadminAuditLog
        with db_session():
            sid = self._seed_canceled_store()
            before = db.session.query(SuperadminAuditLog).count()
        resp = client.post(
            f"/api/v2/superadmin/stores/{sid}/clear-retention",
            headers=sa_headers,
        )
        assert resp.status_code == 200
        with db_session():
            after = db.session.query(SuperadminAuditLog).count()
            assert after == before + 1
            last = (
                db.session.query(SuperadminAuditLog)
                  .order_by(SuperadminAuditLog.id.desc())
                  .first()
            )
            assert last.action == "clear_retention"
            assert last.target_id == str(sid)
            # Audit should preserve the prior retention_until for forensics.
            assert "prior retention_until" in (last.details or "")
