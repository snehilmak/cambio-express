"""Redirect-contract tests for the legacy `/daily` Flask URLs.

The calendar list, per-day editor, line-item AJAX endpoints, and
lock/unlock POSTs all moved to React (`/app/daily[/edit?date=...]`)
backed by `/api/v2/daily/<store>/<date>/*`. Behaviours the legacy
test suite pinned (locked-day rejection, line-item validation, lock
audit-log row, full save round-trip) are now exercised against the
JSON endpoints in `tests/Modules/DailyBook/test_dailybook_controllers.py`
and (for the audit row) `tests/test_operator_audit.py`.

These tests guard:
  - Each legacy URL returns a 301 to the right `/app/*` target.
  - Auth gate (`@admin_required`) runs *before* the redirect, so a
    non-admin still bounces to login (NOT to the SPA).
  - Query strings on the calendar (year + month) are preserved.
"""
from datetime import date

from tests.conftest import make_employee_client


# ── Auth gate (runs BEFORE the 301) ─────────────────────────


def test_daily_list_requires_login(client):
    resp = client.get("/daily", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_daily_list_employee_blocked(client, test_store_id):
    """@admin_required gates daily on the admin role; employees
    bounce to /dashboard, not the SPA."""
    c = make_employee_client(test_store_id)
    resp = c.get("/daily", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" not in resp.headers["Location"]
    assert "/app/daily" not in resp.headers["Location"]


# ── 301 contract: calendar ──────────────────────────────────


def test_daily_list_redirects_to_spa(logged_in_client):
    resp = logged_in_client.get("/daily", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/daily"


def test_daily_list_preserves_year_month_query_string(logged_in_client):
    resp = logged_in_client.get(
        "/daily?year=2026&month=3", follow_redirects=False,
    )
    assert resp.status_code == 301
    loc = resp.headers["Location"]
    assert loc.startswith("/app/daily")
    assert "year=2026" in loc
    assert "month=3" in loc


# ── 301 contract: per-day editor ────────────────────────────


def test_daily_report_get_redirects_to_editor(logged_in_client):
    """`/daily/<ds>` 301s to `/app/daily/edit?date=<ds>`. The editor
    URL shape changed (path → query param) because the SPA's editor
    route is single-purpose and uses `?date=` for shareability."""
    ds = date.today().isoformat()
    resp = logged_in_client.get(f"/daily/{ds}", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == f"/app/daily/edit?date={ds}"


def test_daily_report_post_redirects_to_editor(logged_in_client):
    """Legacy form POSTs also 301. The SPA PUTs to
    /api/v2/daily/<store>/<date> directly. Locked-day rejection,
    auto-derived line-item totals, MT-summary grand total — all
    enforced server-side at the API layer (see
    tests/Modules/DailyBook/test_dailybook_controllers.py)."""
    ds = date.today().isoformat()
    resp = logged_in_client.post(
        f"/daily/{ds}", data={"taxable_sales": "100"},
        follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["Location"] == f"/app/daily/edit?date={ds}"


# ── 301 contract: line-item AJAX ────────────────────────────


def test_daily_line_item_new_redirects_to_editor(logged_in_client):
    ds = date.today().isoformat()
    resp = logged_in_client.post(
        f"/daily/{ds}/line-items/drop/new",
        data={"at_time": "10:00", "amount": "50"},
        follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["Location"] == f"/app/daily/edit?date={ds}"


def test_daily_line_item_delete_redirects_to_editor(logged_in_client):
    ds = date.today().isoformat()
    resp = logged_in_client.post(
        f"/daily/{ds}/line-items/drop/42/delete",
        follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["Location"] == f"/app/daily/edit?date={ds}"


# ── 301 contract: lock / unlock ─────────────────────────────


def test_daily_report_lock_post_redirects_to_editor(logged_in_client):
    ds = date.today().isoformat()
    resp = logged_in_client.post(
        f"/daily/{ds}/lock", follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["Location"] == f"/app/daily/edit?date={ds}"


def test_daily_report_unlock_post_redirects_to_editor(logged_in_client):
    ds = date.today().isoformat()
    resp = logged_in_client.post(
        f"/daily/{ds}/unlock", follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["Location"] == f"/app/daily/edit?date={ds}"
