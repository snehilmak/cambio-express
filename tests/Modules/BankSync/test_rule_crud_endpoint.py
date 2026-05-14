"""HTTP integration tests for the BankRule CRUD endpoints.

  POST   /api/v2/bank/rules
  PUT    /api/v2/bank/rules/{id}
  POST   /api/v2/bank/rules/{id}/toggle
  DELETE /api/v2/bank/rules/{id}

Mirrors the legacy /bank/rules/* form handlers but returns JSON
envelopes the SPA renders directly.
"""
from tests._app import db, db_session


def _login(client, store_id):
    resp = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


def _seed_account(store_id, *, last4="0000"):
    from api.Modules.BankSync.Models import StripeBankAccount
    from tests._app import db
    a = StripeBankAccount(
        store_id=store_id,
        stripe_account_id=f"fcacc_{last4}",
        institution_name="Bank",
        last4=last4,
    )
    db.session.add(a); db.session.commit()
    return a.id


def _seed_rule(store_id, *, target_kind="bank_charge_210", enabled=True,
               desc_match_value=""):
    from api.Modules.BankSync.Models import BankRule
    from tests._app import db
    r = BankRule(
        store_id=store_id, target_kind=target_kind, enabled=enabled,
        desc_match_type="contains" if desc_match_value else "",
        desc_match_value=desc_match_value,
    )
    db.session.add(r); db.session.commit()
    return r.id


# ── Auth ────────────────────────────────────────────────────


def test_create_requires_jwt(client):
    resp = client.post("/api/v2/bank/rules",
                       json={"target_kind": "bank_charge_210"})
    assert resp.status_code == 401


def test_update_requires_jwt(client):
    resp = client.put("/api/v2/bank/rules/1",
                      json={"target_kind": "bank_charge_210"})
    assert resp.status_code == 401


def test_toggle_requires_jwt(client):
    resp = client.post("/api/v2/bank/rules/1/toggle",
                       json={"enabled": False})
    assert resp.status_code == 401


def test_delete_requires_jwt(client):
    resp = client.delete("/api/v2/bank/rules/1")
    assert resp.status_code == 401


# ── Schema validation ───────────────────────────────────────


def test_create_rejects_missing_target_kind(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/bank/rules",
        json={"priority": 100},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_create_rejects_invalid_desc_match_type(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/bank/rules",
        json={"target_kind": "bank_charge_210",
              "desc_match_type": "fuzzy"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_create_rejects_extra_fields(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/bank/rules",
        json={"target_kind": "bank_charge_210", "secret_flag": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_create_rejects_match_type_without_value(client, test_store_id):
    """desc_match_type set but no value → 422 with field hint."""
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/bank/rules",
        json={"target_kind": "bank_charge_210",
              "desc_match_type": "contains", "desc_match_value": "  "},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    detail = resp.get_json()["detail"]
    assert detail["field"] == "desc_match_value"


def test_create_rejects_min_greater_than_max(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/bank/rules",
        json={"target_kind": "bank_charge_210",
              "amount_min_cents": 5000, "amount_max_cents": 100},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    assert resp.get_json()["detail"]["field"] == "amount_max_cents"


def test_create_rejects_account_from_other_store(client, test_store_id):
    """Cross-tenant safety: can't attach a rule to an account in
    another store."""
    from api.Modules.Tenancy.Models import Store
    from tests._app import db
    with db_session():
        other = Store(name="Other", slug="other-rule",
                      email="o@x.com", plan="trial")
        db.session.add(other); db.session.commit()
        oid = _seed_account(other.id)
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/bank/rules",
        json={"target_kind": "bank_charge_210",
              "account_filter_id": oid},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    assert resp.get_json()["detail"]["field"] == "account_filter_id"


# ── Happy paths ─────────────────────────────────────────────


def test_create_persists_and_returns_row(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/bank/rules",
        json={
            "target_kind": "bank_charge_210",
            "desc_match_type": "contains",
            "desc_match_value": "REMOTE DEPOSIT FEE",
            "sign_filter": "debit",
            "priority": 50,
            "auto_post": False,
            "description": "Bank ZZZ RDC fee",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    rule = resp.get_json()["rule"]
    assert rule["desc_match_value"] == "REMOTE DEPOSIT FEE"
    assert rule["priority"] == 50
    assert rule["auto_post"] is False


def test_update_changes_fields(client, test_store_id):
    with db_session():
        rid = _seed_rule(test_store_id, target_kind="bank_charge_210")
    token = _login(client, test_store_id)
    resp = client.put(
        f"/api/v2/bank/rules/{rid}",
        json={
            "target_kind": "bank_charge_230",
            "priority": 999,
            "enabled": False,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    rule = resp.get_json()["rule"]
    assert rule["target_kind"] == "bank_charge_230"
    assert rule["priority"] == 999
    assert rule["enabled"] is False


def test_toggle_flips_enabled(client, test_store_id):
    with db_session():
        rid = _seed_rule(test_store_id, enabled=True)
    token = _login(client, test_store_id)
    resp = client.post(
        f"/api/v2/bank/rules/{rid}/toggle",
        json={"enabled": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["rule"]["enabled"] is False


def test_delete_removes_row(client, test_store_id):
    from api.Modules.BankSync.Models import BankRule
    with db_session():
        rid = _seed_rule(test_store_id)
    token = _login(client, test_store_id)
    resp = client.delete(
        f"/api/v2/bank/rules/{rid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204
    with db_session():
        assert db.session.query(BankRule).filter_by(id=rid).first() is None


# ── Cross-tenant safety on update / toggle / delete ─────────


def test_update_404_for_other_stores_rule(client, test_store_id):
    from api.Modules.Tenancy.Models import Store
    from tests._app import db
    with db_session():
        other = Store(name="X", slug="x-rule", plan="trial")
        db.session.add(other); db.session.commit()
        rid = _seed_rule(other.id)
    token = _login(client, test_store_id)
    resp = client.put(
        f"/api/v2/bank/rules/{rid}",
        json={"target_kind": "bank_charge_210"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_toggle_404_for_other_stores_rule(client, test_store_id):
    from api.Modules.Tenancy.Models import Store
    from tests._app import db
    with db_session():
        other = Store(name="Y", slug="y-rule", plan="trial")
        db.session.add(other); db.session.commit()
        rid = _seed_rule(other.id)
    token = _login(client, test_store_id)
    resp = client.post(
        f"/api/v2/bank/rules/{rid}/toggle",
        json={"enabled": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_delete_404_for_other_stores_rule(client, test_store_id):
    from api.Modules.Tenancy.Models import Store
    from tests._app import db
    with db_session():
        other = Store(name="Z", slug="z-rule", plan="trial")
        db.session.add(other); db.session.commit()
        rid = _seed_rule(other.id)
    token = _login(client, test_store_id)
    resp = client.delete(
        f"/api/v2/bank/rules/{rid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
