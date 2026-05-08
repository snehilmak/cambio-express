"""Tests for the SPA cutover redirect layer.

Every legacy GET path that has an SPA equivalent should 302 to
the matching `/app/*` URL. Routes still on legacy (Stripe billing,
bank-sync write side, owner dashboard, superadmin controls, etc.)
keep serving the Jinja UI. POST/PUT/DELETE bypass the redirect so
in-flight form submits on cached pages still complete.

Set `SPA_CUTOVER_ENABLED=0` to flip the layer off in production
for emergency rollback. The test suite checks both states.
"""
import os

import pytest

import app as app_module


@pytest.fixture
def cutover_on(monkeypatch):
    monkeypatch.setattr(app_module, "SPA_CUTOVER_ENABLED", True)


@pytest.fixture
def cutover_off(monkeypatch):
    monkeypatch.setattr(app_module, "SPA_CUTOVER_ENABLED", False)


# ── Static path mappings ────────────────────────────────────


@pytest.mark.parametrize("legacy,spa", [
    ("/login",                "/app/login"),
    ("/signup",               "/app/signup"),
    ("/forgot-password",      "/app/forgot-password"),
    ("/dashboard",            "/app/dashboard"),
    ("/transfers",            "/app/transfers"),
    ("/transfers/new",        "/app/transfers/new"),
    ("/daily",                "/app/daily"),
    ("/reports",              "/app/reports"),
    ("/batches",              "/app/batches"),
    ("/batches/new",          "/app/batches/new"),
    ("/monthly",              "/app/monthly"),
    ("/return-checks",        "/app/return-checks"),
    ("/owner/locations",      "/app/owner/locations"),
    ("/superadmin/stores",    "/app/superadmin/stores"),
    ("/superadmin/reports/audit-log", "/app/superadmin/audit-log"),
    ("/admin/settings",       "/app/settings"),
    ("/bank/transactions",    "/app/bank-transactions"),
])
def test_legacy_get_redirects_to_spa(client, cutover_on, legacy, spa):
    resp = client.get(legacy, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].split("?")[0].endswith(spa)


# ── Dynamic path mappings ───────────────────────────────────


def test_reset_password_path_param_becomes_query(client, cutover_on):
    resp = client.get("/reset-password/abc123token", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/app/reset-password?token=abc123token"


def test_transfers_detail_redirects(client, cutover_on):
    resp = client.get("/transfers/42", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/app/transfers/42"


def test_transfers_edit_redirects(client, cutover_on):
    resp = client.get("/transfers/42/edit", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/app/transfers/42/edit"


def test_batches_edit_redirects(client, cutover_on):
    resp = client.get("/batches/7/edit", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/app/batches/7/edit"


def test_daily_dated_redirects_to_edit_with_query(client, cutover_on):
    resp = client.get("/daily/2026-05-08", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/app/daily/edit?date=2026-05-08"


def test_monthly_year_month_redirects_to_edit(client, cutover_on):
    resp = client.get("/monthly/2026/3", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/app/monthly/edit?year=2026&month=3"


# ── Query string preservation ───────────────────────────────


def test_query_string_preserved_on_static_redirect(client, cutover_on):
    resp = client.get(
        "/transfers?company=Intermex&q=jane", follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith(
        "/app/transfers?company=Intermex&q=jane"
    )


# ── Negative paths (must NOT redirect) ──────────────────────


def test_static_assets_not_redirected(client, cutover_on):
    resp = client.get("/static/design-tokens.css", follow_redirects=False)
    # Either 200 (file present) or 404, but never a 302 to /app/*
    assert resp.status_code != 302


def test_api_v2_not_redirected(client, cutover_on):
    """`/api/v2/*` is the FastAPI dispatcher target — must never
    bounce through the SPA redirect or it would break every API
    call from the SPA itself."""
    resp = client.get("/api/v2/health", follow_redirects=False)
    # Could be 200 (OK), 401 (auth required), etc — never 302/SPA.
    assert resp.status_code != 302


def test_app_paths_not_redirected(client, cutover_on):
    """Hitting `/app/*` should never re-redirect — that would loop."""
    resp = client.get("/app/login", follow_redirects=False)
    assert resp.status_code != 302


def test_unmigrated_legacy_route_keeps_serving(client, cutover_on):
    """A legacy page that has no SPA equivalent today (Stripe
    subscribe, owner dashboard, TV display, superadmin controls,
    etc.) must NOT redirect — it keeps serving Jinja so the
    feature stays reachable until SPA parity ships."""
    # /privacy is a public page on legacy with no SPA twin.
    resp = client.get("/privacy", follow_redirects=False)
    assert resp.status_code != 302


def test_post_does_not_redirect(client, cutover_on):
    """An in-flight form submit (POST) on a cached legacy page
    must NOT be intercepted — let the legacy handler process it
    so the user's data isn't lost mid-flow."""
    resp = client.post("/login", data={"username": "x", "password": "y"},
                       follow_redirects=False)
    # Legacy /login POST returns either 200 (re-render with error)
    # or 302 to a Flask URL like /dashboard or /login/2fa — but
    # never to /app/*.
    if resp.status_code == 302:
        assert not resp.headers["Location"].startswith("/app/")


# ── Feature flag off ────────────────────────────────────────


def test_cutover_disabled_keeps_legacy_serving(client, cutover_off):
    """SPA_CUTOVER_ENABLED=0 → legacy GET serves Jinja, no redirect."""
    resp = client.get("/login", follow_redirects=False)
    # Legacy /login GET returns 200 with the login HTML.
    assert resp.status_code == 200
    assert b"<form" in resp.data or b"login" in resp.data.lower()
