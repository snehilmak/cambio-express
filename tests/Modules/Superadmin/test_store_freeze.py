"""Endpoint tests for superadmin store freeze / unfreeze (PR C).

  * `POST /superadmin/stores/{id}/freeze`
  * `POST /superadmin/stores/{id}/unfreeze`

Covers happy path, state persistence, the audit row (invariant #7),
404, the auth gate, and the frozen flag surfacing in the store drill.
"""
import pytest

from tests._app import db, db_session
from tests.conftest import login_superadmin


@pytest.fixture
def sa_headers(client):
    return {"Authorization": f"Bearer {login_superadmin(client)}"}


def _store(store_id):
    from api.Modules.Tenancy.Models import Store
    with db_session():
        return db.session.get(Store, store_id)


def _audit_rows(action, target_id):
    from api.Modules.Audit.Models import SuperadminAuditLog
    with db_session():
        return (
            db.session.query(SuperadminAuditLog)
              .filter(SuperadminAuditLog.action == action)
              .filter(SuperadminAuditLog.target_id == str(target_id))
              .all()
        )


class TestFreeze:
    def test_freeze_sets_state_and_persists(self, client, sa_headers, test_store_id):
        resp = client.post(
            f"/api/v2/superadmin/stores/{test_store_id}/freeze",
            headers=sa_headers, json={"reason": "chargeback dispute"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True and body["frozen"] is True
        assert body["frozen_at"] != ""
        assert body["frozen_reason"] == "chargeback dispute"
        # Persisted on the row.
        assert _store(test_store_id).frozen_at is not None

    def test_freeze_writes_audit(self, client, sa_headers, test_store_id):
        resp = client.post(
            f"/api/v2/superadmin/stores/{test_store_id}/freeze",
            headers=sa_headers, json={"reason": "abuse"},
        )
        assert resp.status_code == 200
        assert len(_audit_rows("freeze_store", test_store_id)) == 1

    def test_freeze_404_for_missing_store(self, client, sa_headers):
        resp = client.post(
            "/api/v2/superadmin/stores/999999/freeze",
            headers=sa_headers, json={"reason": ""},
        )
        assert resp.status_code == 404

    def test_freeze_requires_superadmin(self, client, test_store_id):
        resp = client.post(
            f"/api/v2/superadmin/stores/{test_store_id}/freeze",
            json={"reason": ""},
        )
        assert resp.status_code in (401, 403)

    def test_frozen_flag_in_drill(self, client, sa_headers, test_store_id):
        client.post(
            f"/api/v2/superadmin/stores/{test_store_id}/freeze",
            headers=sa_headers, json={"reason": "hold"},
        )
        resp = client.get(
            f"/api/v2/superadmin/stores/{test_store_id}/drill",
            headers=sa_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["store"]["frozen"] is True


class TestUnfreeze:
    def test_unfreeze_clears_state_and_audits(self, client, sa_headers, test_store_id):
        client.post(
            f"/api/v2/superadmin/stores/{test_store_id}/freeze",
            headers=sa_headers, json={"reason": "temp"},
        )
        resp = client.post(
            f"/api/v2/superadmin/stores/{test_store_id}/unfreeze",
            headers=sa_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True and body["frozen"] is False
        assert _store(test_store_id).frozen_at is None
        assert len(_audit_rows("unfreeze_store", test_store_id)) == 1

    def test_unfreeze_404_for_missing_store(self, client, sa_headers):
        resp = client.post(
            "/api/v2/superadmin/stores/999999/unfreeze",
            headers=sa_headers,
        )
        assert resp.status_code == 404
