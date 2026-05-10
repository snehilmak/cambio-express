"""Redirect-contract tests for the legacy `/monthly` Flask URLs.

The list page (`/monthly`), the per-month editor
(`/monthly/<year>/<month>`), and the "go to current month" shortcut
(`/monthly/new`) all moved to React (`/app/monthly[...]`) backed by
`/api/v2/monthly/*`. The data-shape contracts the legacy tests
pinned — locked fields, daily-summed auto-derivation, return-check
G/L net, bank-charge rollup, cross-store 404 — are exercised
against the JSON endpoints in
`tests/Modules/Monthly/test_monthly_controllers.py`.

These tests guard:
  - Legacy URLs return 301 to the right `/app/*` target.
  - Auth gate (admin_required) runs *before* the redirect, so a
    non-admin still sees the bounce-to-login.
  - GET on a far-future month doesn't accidentally create a
    MonthlyFinancial row (the legacy invariant — kept here as a
    sanity check that the new redirect does NO database work).
"""
from app import db


def _admin_login(client, store_id, *, plan="pro"):
    from app import User, Store
    with client.application.app_context():
        u = User.query.filter_by(store_id=store_id, role="admin").first()
        uid = u.id
        s = db.session.get(Store, store_id)
        s.plan = plan
        s.billing_cycle = "monthly"
        db.session.commit()
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["role"] = "admin"
        s["store_id"] = store_id
    return client


def _row_for(client, store_id, year, month):
    from app import MonthlyFinancial
    with client.application.app_context():
        return MonthlyFinancial.query.filter_by(
            store_id=store_id, year=year, month=month).first()


# ── 301 contract ─────────────────────────────────────────────


def test_monthly_list_redirects_to_spa(logged_in_client):
    resp = logged_in_client.get("/monthly", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/monthly"


def test_monthly_get_year_month_redirects_to_editor(logged_in_client):
    """`/monthly/<year>/<month>` 301s to the SPA editor with the
    year + month preserved as query params (the SPA expects
    `/app/monthly/edit?year=&month=`)."""
    resp = logged_in_client.get("/monthly/2099/3", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/monthly/edit?year=2099&month=3"


def test_monthly_post_year_month_redirects_to_editor(logged_in_client):
    """Legacy form POSTs also 301. The SPA PUTs to
    /api/v2/monthly/<y>/<m> directly — the legacy form path is
    dead. Any in-flight Jinja submission lands on the SPA editor."""
    resp = logged_in_client.post(
        "/monthly/2099/4", data={"notes": "x"}, follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/monthly/edit?year=2099&month=4"


def test_monthly_new_redirects_to_current_month_editor(logged_in_client):
    """`/monthly/new` historically bounced to the current year+month
    editor. New behaviour: bounce to the SPA editor with the same
    semantics."""
    from datetime import date
    today = date.today()
    resp = logged_in_client.get("/monthly/new", follow_redirects=False)
    assert resp.status_code == 301
    target = (
        f"/app/monthly/edit?year={today.year}&month={today.month}"
    )
    assert resp.headers["Location"] == target


# ── No-side-effects sanity ───────────────────────────────────


def test_monthly_get_no_row_persists_no_row(logged_in_client, test_store_id):
    """The legacy /monthly/<year>/<month> GET intentionally did NOT
    create a MonthlyFinancial row — only POST did. With the 301,
    the redirect never touches the DB at all, so the same invariant
    holds (and is now even cheaper to verify)."""
    logged_in_client.get("/monthly/2099/2")
    assert _row_for(logged_in_client, test_store_id, 2099, 2) is None


# ── Auth gate ────────────────────────────────────────────────


def test_monthly_requires_login(client):
    """Unauthed → /login. The @admin_required decorator runs before
    the redirect, so an anonymous request bounces to login (NOT to
    the SPA — we don't want unauthed users landing on /app routes
    that immediately bounce them again)."""
    resp = client.get("/monthly/2099/9", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_monthly_list_requires_login(client):
    resp = client.get("/monthly", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
