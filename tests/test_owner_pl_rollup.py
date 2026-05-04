"""Tests for /owner/pl-rollup — multi-store P&L side-by-side view."""
from datetime import date

import pytest

from app import app as flask_app, db


def _make_store(slug, name, plan="pro"):
    from app import Store
    s = Store(name=name, slug=slug, plan=plan)
    db.session.add(s); db.session.commit()
    return s.id


def _link_owner(owner_id, store_id):
    from app import StoreOwnerLink
    db.session.add(StoreOwnerLink(owner_id=owner_id, store_id=store_id))
    db.session.commit()


def _make_pl(store_id, year, month, *, taxable=1000.0, expenses_cash=200.0):
    from app import MonthlyFinancial
    pl = MonthlyFinancial(store_id=store_id, year=year, month=month,
                           taxable_sales=taxable,
                           cash_expenses=expenses_cash)
    db.session.add(pl); db.session.commit()
    return pl.id


@pytest.fixture
def owner_client():
    c = flask_app.test_client()
    with flask_app.app_context():
        from app import User
        o = User(username="owner@rollup.com", full_name="Rollup Owner",
                 role="owner", store_id=None)
        o.set_password("ownerpass123")
        db.session.add(o); db.session.commit()
        oid = o.id
        s1 = _make_store("rollup-shop-a", "Shop A")
        s2 = _make_store("rollup-shop-b", "Shop B")
        _link_owner(oid, s1)
        _link_owner(oid, s2)
        flask_app.config["_TEST_ROLLUP_STORES"] = (s1, s2)
    with c.session_transaction() as sess:
        sess["user_id"] = oid
        sess["role"] = "owner"
        sess["store_id"] = None
    return c


def test_pl_rollup_renders_with_no_data(owner_client):
    """Empty umbrella month — page should still render with zeroed
    totals and per-store rows tagged 'No P&L yet'."""
    today = date.today()
    resp = owner_client.get(f"/owner/pl-rollup?year={today.year}&month={today.month}")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Multi-store P&amp;L Rollup" in body or "Multi-store P&L" in body
    assert "Shop A" in body
    assert "Shop B" in body
    assert "No P&L yet" in body


def test_pl_rollup_aggregates_per_store(owner_client):
    s1, s2 = flask_app.config["_TEST_ROLLUP_STORES"]
    today = date.today()
    with flask_app.app_context():
        _make_pl(s1, today.year, today.month, taxable=5000.0,
                  expenses_cash=300.0)
        _make_pl(s2, today.year, today.month, taxable=2000.0,
                  expenses_cash=100.0)
    resp = owner_client.get(f"/owner/pl-rollup?year={today.year}&month={today.month}")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # Total revenue across the two stores = 5000 + 2000 = 7000.
    assert "$7,000.00" in body
    # Per-store revenue figures are visible.
    assert "$5,000.00" in body
    assert "$2,000.00" in body


def test_pl_rollup_sorts_by_net_income_desc(owner_client):
    """Strongest performer floats to the top. Shop B has higher net
    income than Shop A here, so it should appear first in the rendered
    table even though Shop A is alphabetically before."""
    s1, s2 = flask_app.config["_TEST_ROLLUP_STORES"]
    today = date.today()
    with flask_app.app_context():
        _make_pl(s1, today.year, today.month, taxable=1000.0,
                  expenses_cash=900.0)   # net ~ +100
        _make_pl(s2, today.year, today.month, taxable=10000.0,
                  expenses_cash=200.0)   # net ~ +9800
    resp = owner_client.get(f"/owner/pl-rollup?year={today.year}&month={today.month}")
    body = resp.get_data(as_text=True)
    pos_a = body.find("Shop A")
    pos_b = body.find("Shop B")
    assert pos_b < pos_a, "Shop B (higher net) should render before Shop A"


def test_pl_rollup_invalid_month_falls_back_to_current(owner_client):
    """A nonsense ?month= query string shouldn't 500 — fall back to the
    current month silently."""
    resp = owner_client.get("/owner/pl-rollup?month=99")
    assert resp.status_code == 200


def test_pl_rollup_admin_role_blocked(client, test_store_id):
    """Admin (non-owner) shouldn't be able to hit the owner-scoped
    rollup page — the @owner_required decorator gates the route."""
    from app import User, db
    with client.application.app_context():
        u = User.query.filter_by(store_id=test_store_id, role="admin").first()
        uid = u.id
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "admin"
        sess["store_id"] = test_store_id

    resp = client.get("/owner/pl-rollup", follow_redirects=False)
    # @owner_required either 302s back or 403s — anything not 200.
    assert resp.status_code != 200
