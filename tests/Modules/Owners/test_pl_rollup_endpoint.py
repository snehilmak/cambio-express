"""HTTP integration tests for /api/v2/owner/pl-rollup."""
from datetime import date
from tests._app import db


def _make_owner(*, username="boss-pl@example.com", password="ownerpass1!",
                home_store_slug="boss-pl-home"):
    from api.Modules.Tenancy.Models import Store, User
    from tests._app import db
    s = Store(name="Boss PL Home", slug=home_store_slug,
              email=username, plan="basic")
    db.session.add(s); db.session.commit()
    u = User(
        store_id=s.id, username=username, full_name="Boss",
        email=username, role="owner",
    )
    u.set_password(password)
    db.session.add(u); db.session.commit()
    return u.id, s.id, password


def _link(owner_id, *, store_name, store_slug, plan="basic"):
    from api.Modules.Tenancy.Models import Store, StoreOwnerLink
    from tests._app import db
    s = Store(name=store_name, slug=store_slug,
              email=f"{store_slug}@x.com", plan=plan)
    db.session.add(s); db.session.commit()
    db.session.add(StoreOwnerLink(owner_id=owner_id, store_id=s.id))
    db.session.commit()
    return s.id


def _seed_pl(store_id, year, month, *, revenue=0.0, purchases=0.0,
             expenses=0.0, over_short=0.0):
    """Seed a MonthlyFinancial row. revenue / purchases / expenses are
    SQL-summed properties on the model — we route them to the
    canonical raw columns (`taxable_sales`, `cash_purchases`,
    `cash_expenses`) so the response carries the expected totals.
    `net_income` is derived: rev - pur - exp + over_short."""
    from api.Modules.Monthly.Models import MonthlyFinancial
    from tests._app import db
    mf = MonthlyFinancial(
        store_id=store_id, year=year, month=month,
        taxable_sales=revenue,
        cash_purchases=purchases,
        cash_expenses=expenses,
        over_short=over_short,
    )
    db.session.add(mf); db.session.commit()


def _login_owner(client, username, password):
    resp = client.post(
        "/api/v2/auth/login-cross-store",
        json={"username": username, "password": password},
    )
    return resp.get_json()["access_token"]


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


def test_pl_rollup_requires_jwt(client):
    resp = client.get("/api/v2/owner/pl-rollup")
    assert resp.status_code == 401


def test_pl_rollup_rejects_admin_role(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.get(
        "/api/v2/owner/pl-rollup",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_pl_rollup_rejects_invalid_month(client):
    from tests._app import app as flask_app
    with flask_app.app_context():
        _, _, pw = _make_owner()
    token = _login_owner(client, "boss-pl@example.com", pw)
    resp = client.get(
        "/api/v2/owner/pl-rollup?month=13",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_pl_rollup_returns_envelope_for_unlinked_owner(client):
    """An owner with no linked stores still gets a valid envelope."""
    from tests._app import app as flask_app
    with flask_app.app_context():
        _, _, pw = _make_owner()
    token = _login_owner(client, "boss-pl@example.com", pw)
    resp = client.get(
        "/api/v2/owner/pl-rollup",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    today = date.today()
    assert body["year"] == today.year
    assert body["month"] == today.month
    assert body["rows"] == []
    assert body["totals"]["net"] == 0.0


def test_pl_rollup_lists_per_store_with_totals(client):
    from tests._app import app as flask_app
    with flask_app.app_context():
        owner_id, _, pw = _make_owner()
        s1 = _link(owner_id, store_name="Alpha", store_slug="alpha-pl")
        s2 = _link(owner_id, store_name="Beta",  store_slug="beta-pl")
        _seed_pl(s1, 2026, 3, revenue=1000.0, expenses=400.0)
        _seed_pl(s2, 2026, 3, revenue=500.0,  expenses=300.0)
    token = _login_owner(client, "boss-pl@example.com", pw)
    resp = client.get(
        "/api/v2/owner/pl-rollup?year=2026&month=3",
        headers={"Authorization": f"Bearer {token}"},
    )
    body = resp.get_json()
    assert body["year"] == 2026
    assert body["month"] == 3
    assert len(body["rows"]) == 2
    # Sorted by net income desc — Alpha (600) first, Beta (200) second.
    assert body["rows"][0]["store_slug"] == "alpha-pl"
    assert body["rows"][1]["store_slug"] == "beta-pl"
    assert body["rows"][0]["has_pl"] is True
    assert body["totals"]["revenue"] == 1500.0
    assert body["totals"]["expenses"] == 700.0
    # Net = Σ (revenue - purchases - expenses + over_short)
    #     = (1000 - 0 - 400) + (500 - 0 - 300) = 600 + 200 = 800
    assert body["totals"]["net"] == 800.0


def test_pl_rollup_marks_missing_pl_rows_with_has_pl_false(client):
    """A store without a MonthlyFinancial row for the requested
    period gets has_pl=False + zero values."""
    from tests._app import app as flask_app
    with flask_app.app_context():
        owner_id, _, pw = _make_owner()
        _link(owner_id, store_name="Empty", store_slug="empty-pl")
    token = _login_owner(client, "boss-pl@example.com", pw)
    body = client.get(
        "/api/v2/owner/pl-rollup?year=2026&month=3",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert len(body["rows"]) == 1
    assert body["rows"][0]["has_pl"] is False
    assert body["rows"][0]["net"] == 0.0


def test_pl_rollup_year_choices_includes_distinct_years(client):
    from tests._app import app as flask_app
    with flask_app.app_context():
        owner_id, _, pw = _make_owner()
        s1 = _link(owner_id, store_name="A", store_slug="a-pl")
        _seed_pl(s1, 2024, 6, revenue=10.0)
        _seed_pl(s1, 2025, 6, revenue=10.0)
        _seed_pl(s1, 2026, 6, revenue=10.0)
    token = _login_owner(client, "boss-pl@example.com", pw)
    body = client.get(
        "/api/v2/owner/pl-rollup",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    # Always at least the current year, plus every distinct year on file.
    assert 2024 in body["year_choices"]
    assert 2025 in body["year_choices"]
    assert 2026 in body["year_choices"]
    # Sorted desc.
    assert body["year_choices"] == sorted(body["year_choices"], reverse=True)


def test_pl_rollup_excludes_unrelated_stores(client):
    from api.Modules.Tenancy.Models import Store
    from tests._app import app as flask_app, db
    with flask_app.app_context():
        owner_id, _, pw = _make_owner()
        s1 = _link(owner_id, store_name="Mine", store_slug="mine-pl")
        _seed_pl(s1, 2026, 3, revenue=100.0)
        # Unrelated store with a P&L — should NOT appear
        other = Store(name="Theirs", slug="theirs-pl",
                      email="t@x.com", plan="basic")
        db.session.add(other); db.session.commit()
        _seed_pl(other.id, 2026, 3, revenue=999999.0)
    token = _login_owner(client, "boss-pl@example.com", pw)
    body = client.get(
        "/api/v2/owner/pl-rollup?year=2026&month=3",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    slugs = {r["store_slug"] for r in body["rows"]}
    assert slugs == {"mine-pl"}
    assert body["totals"]["revenue"] == 100.0
