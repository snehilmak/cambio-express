"""Regression guard for CLAUDE.md invariant #7 — every mutating
TV-display endpoint records an `OperatorAuditLog` row.

All TV-display write routes are gated by `_require_tv_store`
(store-scoped admin/employee JWT), so each mutation is a store
operator action and lands in the per-store operator log. These
tests fire if a future refactor drops any of the six audit
emissions off the controllers.
"""
from tests._app import db, db_session


def _login_admin(client, store_id):
    resp = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


def _enable_tv_addon(store_id):
    from api.Modules.Tenancy.Models import Store
    with db_session():
        s = db.session.get(Store, store_id)
        s.plan = "basic"
        s.addons = "tv_display"
        db.session.commit()


def _latest_audit(store_id, action: str):
    from api.Modules.Audit.Models import OperatorAuditLog
    return (
        db.session.query(OperatorAuditLog)
          .filter_by(store_id=store_id, action=action)
          .order_by(OperatorAuditLog.id.desc())
          .first()
    )


def _count_audit(store_id, action: str) -> int:
    from api.Modules.Audit.Models import OperatorAuditLog
    return (
        db.session.query(OperatorAuditLog)
          .filter_by(store_id=store_id, action=action)
          .count()
    )


# ── POST /settings ──────────────────────────────────────────


def test_settings_emits_audit_row(client, test_store_id):
    _enable_tv_addon(test_store_id)
    token = _login_admin(client, test_store_id)
    resp = client.post(
        "/api/v2/tv-display/settings",
        json={"title": "Rates", "subtitle": "",
              "orientation": "portrait", "theme": "dark"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204, resp.get_data(as_text=True)
    row = _latest_audit(test_store_id, "update_tv_settings")
    assert row is not None
    assert row.target_type == "tv_display"
    assert "theme=dark" in (row.summary or "")


# ── POST /regenerate-token ──────────────────────────────────


def test_regenerate_token_emits_audit_row(client, test_store_id):
    _enable_tv_addon(test_store_id)
    token = _login_admin(client, test_store_id)
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post(
        "/api/v2/tv-display/regenerate-token", json={}, headers=headers,
    )
    assert resp.status_code == 200
    new_token = resp.get_json()["public_token"]
    row = _latest_audit(test_store_id, "regenerate_tv_token")
    assert row is not None
    # Security: the rotated token value must never land in the log.
    assert new_token not in (row.summary or "")
    assert "rotated" in (row.summary or "")


# ── POST /claim + /pairings/{id}/revoke ─────────────────────


def _pair_a_device(client, test_store_id):
    init = client.post("/api/tv-pair/init", json={"device_label": "Counter"})
    code = init.get_json()["code"]
    token = _login_admin(client, test_store_id)
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post(
        "/api/v2/tv-display/claim", json={"code": code}, headers=headers,
    )
    assert resp.status_code == 204, resp.get_data(as_text=True)
    return headers


def test_claim_emits_audit_row(client, test_store_id):
    _enable_tv_addon(test_store_id)
    _pair_a_device(client, test_store_id)
    row = _latest_audit(test_store_id, "claim_tv_pairing")
    assert row is not None
    assert row.target_type == "tv_pairing"


def test_revoke_pairing_emits_audit_row_once(client, test_store_id):
    """Revoke emits `revoke_tv_pairing` on the state transition; a
    second (no-op) revoke of the same pairing adds no row."""
    from api.Modules.TVDisplay.Models import TVPairing
    _enable_tv_addon(test_store_id)
    headers = _pair_a_device(client, test_store_id)
    with db_session():
        pairing_id = (
            db.session.query(TVPairing)
              .order_by(TVPairing.id.desc())
              .first().id
        )
    resp = client.post(
        f"/api/v2/tv-display/pairings/{pairing_id}/revoke", headers=headers,
    )
    assert resp.status_code == 204
    assert _count_audit(test_store_id, "revoke_tv_pairing") == 1
    # Re-revoke is a no-op — no second audit row.
    resp2 = client.post(
        f"/api/v2/tv-display/pairings/{pairing_id}/revoke", headers=headers,
    )
    assert resp2.status_code == 204
    assert _count_audit(test_store_id, "revoke_tv_pairing") == 1


# ── POST + DELETE /countries ────────────────────────────────


def test_country_create_and_delete_emit_audit_rows(client, test_store_id):
    _enable_tv_addon(test_store_id)
    token = _login_admin(client, test_store_id)
    headers = {"Authorization": f"Bearer {token}"}
    create = client.post(
        "/api/v2/tv-display/countries",
        json={"country_name": "Mexico", "country_code": "MX",
              "mt_companies": "Maxi"},
        headers=headers,
    )
    assert create.status_code == 201, create.get_data(as_text=True)
    country_id = create.get_json()["id"]
    crow = _latest_audit(test_store_id, "create_tv_country")
    assert crow is not None
    assert crow.target_id == str(country_id)

    resp = client.delete(
        f"/api/v2/tv-display/countries/{country_id}", headers=headers,
    )
    assert resp.status_code == 204
    drow = _latest_audit(test_store_id, "delete_tv_country")
    assert drow is not None
    assert drow.target_id == str(country_id)
