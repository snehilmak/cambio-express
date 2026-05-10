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


def test_pl_rollup_redirects_to_spa(owner_client):
    """Page-render moved to React; the legacy URL 301s to the SPA
    page that reads /api/v2/owner/pl-rollup. Query string (year +
    month) is preserved so a deep-link to a specific month still
    lands on the right page."""
    today = date.today()
    resp = owner_client.get(
        f"/owner/pl-rollup?year={today.year}&month={today.month}",
        follow_redirects=False,
    )
    assert resp.status_code == 301
    loc = resp.headers["Location"]
    assert loc.startswith("/app/owner/pl-rollup")
    assert f"year={today.year}" in loc
    assert f"month={today.month}" in loc


def test_pl_rollup_admin_role_blocked(client, test_store_id):
    """Admin (non-owner) shouldn't be able to hit the owner-scoped
    rollup page — the @owner_required decorator gates the route
    BEFORE the 301 redirect runs, so the bounce target is /login (or
    a 403), never the SPA page."""
    from app import User, db  # noqa: F401
    with client.application.app_context():
        u = User.query.filter_by(store_id=test_store_id, role="admin").first()
        uid = u.id
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "admin"
        sess["store_id"] = test_store_id

    resp = client.get("/owner/pl-rollup", follow_redirects=False)
    # @owner_required bounces non-owners — anything but the SPA 301.
    assert resp.status_code != 200
    if resp.status_code in (301, 302, 303):
        assert "/app/owner/pl-rollup" not in resp.headers.get("Location", "")
