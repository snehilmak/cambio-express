"""HTTP integration tests for /bank/rules.

After SPA-29 the endpoint derives `store_id` from the JWT
principal — explicit `store_ids` query params are gone.
"""


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


def _seed_rule(store_id, *, target_kind="bank_charge_210",
               priority=100, enabled=True, desc_match_value="",
               account_filter_id=None):
    from api.Modules.BankSync.Models import BankRule
    from tests._app import db
    r = BankRule(
        store_id=store_id,
        target_kind=target_kind,
        priority=priority,
        enabled=enabled,
        desc_match_type="contains" if desc_match_value else "",
        desc_match_value=desc_match_value,
        account_filter_id=account_filter_id,
    )
    db.session.add(r); db.session.commit()
    return r.id


def _seed_account(store_id, *, last4="0000", nickname=""):
    from api.Modules.BankSync.Models import StripeBankAccount
    from tests._app import db
    a = StripeBankAccount(
        store_id=store_id,
        stripe_account_id=f"fcacc_{last4}",
        institution_name="Bank",
        last4=last4,
        nickname=nickname,
    )
    db.session.add(a); db.session.commit()
    return a.id


def test_rules_endpoint_requires_jwt(client):
    resp = client.get("/api/v2/bank/rules")
    assert resp.status_code == 401


def test_rules_endpoint_returns_empty_envelope(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/bank/rules",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {"rows": [], "total": 0}


def test_rules_endpoint_lists_rules_in_priority_order(client, test_store_id):
    from tests._app import app as flask_app
    with flask_app.app_context():
        r_low = _seed_rule(test_store_id, priority=100,
                           desc_match_value="LOW")
        r_high = _seed_rule(test_store_id, priority=10,
                            desc_match_value="HIGH")
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/bank/rules",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 2
    assert [r["id"] for r in body["rows"]] == [r_high, r_low]


def test_rules_endpoint_enabled_only_filter(client, test_store_id):
    from tests._app import app as flask_app
    with flask_app.app_context():
        r_on = _seed_rule(test_store_id, desc_match_value="ON",
                          enabled=True)
        _seed_rule(test_store_id, desc_match_value="OFF", enabled=False)
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/bank/rules?enabled_only=true",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert [r["id"] for r in body["rows"]] == [r_on]


def test_rules_endpoint_decorates_account_filter_label(client, test_store_id):
    """Rules with account_filter_id get the label decorated so the
    UI doesn't follow the FK separately."""
    from tests._app import app as flask_app
    with flask_app.app_context():
        a = _seed_account(test_store_id, last4="9999",
                          nickname="Operating")
        _seed_rule(test_store_id, desc_match_value="X",
                   account_filter_id=a)
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/bank/rules",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["rows"][0]["account_filter_id"] == a
    assert body["rows"][0]["account_filter_label"] == "Operating"


def test_rules_endpoint_excludes_other_stores(client, test_store_id):
    from api.Modules.Tenancy.Models import Store
    from tests._app import app as flask_app, db
    with flask_app.app_context():
        s2 = Store(name="Other", slug="other-rules",
                   email="o@x.com", plan="trial")
        db.session.add(s2); db.session.commit()
        _seed_rule(s2.id, desc_match_value="HIDDEN")
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/bank/rules",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["rows"] == []


def test_openapi_includes_rules_path(client):
    resp = client.get("/api/v2/openapi.json")
    paths = set(resp.get_json()["paths"].keys())
    assert "/bank/rules" in paths
