"""HTTP integration tests for /bank/rules (PR 25)."""
from datetime import datetime

from fastapi.testclient import TestClient


def _seed_rule(store_id, *, target_kind="bank_charge_210",
                priority=100, enabled=True, desc_match_value="",
                account_filter_id=None):
    from app import BankRule, db
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
    from app import StripeBankAccount, db
    a = StripeBankAccount(
        store_id=store_id,
        stripe_account_id=f"fcacc_{last4}",
        institution_name="Bank",
        last4=last4,
        nickname=nickname,
    )
    db.session.add(a); db.session.commit()
    return a.id


def _client():
    from api.main import api_app
    return TestClient(api_app)


def test_rules_endpoint_requires_store_ids():
    resp = _client().get("/bank/rules")
    assert resp.status_code == 422


def test_rules_endpoint_returns_empty_envelope(test_store_id):
    resp = _client().get(
        "/bank/rules", params={"store_ids": str(test_store_id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"rows": [], "total": 0}


def test_rules_endpoint_lists_rules_in_priority_order(test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        r_low = _seed_rule(test_store_id, priority=100,
                             desc_match_value="LOW")
        r_high = _seed_rule(test_store_id, priority=10,
                             desc_match_value="HIGH")
    resp = _client().get(
        "/bank/rules", params={"store_ids": str(test_store_id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    # priority asc: HIGH (10) first, then LOW (100)
    assert [r["id"] for r in body["rows"]] == [r_high, r_low]


def test_rules_endpoint_enabled_only_filter(test_store_id):
    from app import app as flask_app
    with flask_app.app_context():
        r_on = _seed_rule(test_store_id, desc_match_value="ON",
                           enabled=True)
        _seed_rule(test_store_id, desc_match_value="OFF",
                     enabled=False)
    resp = _client().get(
        "/bank/rules",
        params={"store_ids": str(test_store_id), "enabled_only": "true"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert [r["id"] for r in body["rows"]] == [r_on]


def test_rules_endpoint_decorates_account_filter_label(test_store_id):
    """Rules with account_filter_id get the label decorated so the
    UI doesn't follow the FK separately."""
    from app import app as flask_app
    with flask_app.app_context():
        a = _seed_account(test_store_id, last4="9999",
                            nickname="Operating")
        _seed_rule(
            test_store_id, desc_match_value="X",
            account_filter_id=a,
        )
    resp = _client().get(
        "/bank/rules", params={"store_ids": str(test_store_id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows"][0]["account_filter_id"] == a
    assert body["rows"][0]["account_filter_label"] == "Operating"


def test_rules_endpoint_excludes_other_stores(test_store_id):
    from app import app as flask_app, db, Store
    with flask_app.app_context():
        s2 = Store(name="Other", slug="other-rules",
                    email="o@x.com", plan="trial")
        db.session.add(s2); db.session.commit()
        _seed_rule(s2.id, desc_match_value="HIDDEN")
    resp = _client().get(
        "/bank/rules", params={"store_ids": str(test_store_id)},
    )
    assert resp.status_code == 200
    assert resp.json()["rows"] == []


def test_openapi_includes_rules_path():
    resp = _client().get("/openapi.json")
    paths = set(resp.json()["paths"].keys())
    assert "/bank/rules" in paths
