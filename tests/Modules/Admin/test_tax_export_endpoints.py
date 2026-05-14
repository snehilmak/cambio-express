"""HTTP integration tests for the Admin tax-export year picker.

The matching React page (frontend/src/routes/AdminTaxExport.tsx)
calls /api/v2/admin/tax-export/years on mount and renders the
year list. The actual ZIP build still lives on the legacy Flask
route /admin/tax-export.zip — we don't test that here (it streams
multi-MB files and would dominate the suite runtime).
"""
from datetime import date
from tests._app import db, db_session


def _login(client_, store_id):
    resp = client_.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


# ── auth gating ─────────────────────────────────────────────


def test_years_requires_jwt(client):
    resp = client.get("/api/v2/admin/tax-export/years")
    assert resp.status_code == 401


def test_years_rejects_superadmin(client):
    """Superadmin JWT carries no store scope — the year query
    needs a store_id, so it 403s."""
    from tests.conftest import login_superadmin
    token = login_superadmin(client)
    resp = client.get(
        "/api/v2/admin/tax-export/years",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── happy path ──────────────────────────────────────────────


def test_years_seeds_this_and_last_for_brand_new_store(
    client, test_store_id,
):
    """A store with no transfers + no daily reports still gets
    the current and previous years on the list — otherwise the
    picker would render empty on day one."""
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/admin/tax-export/years",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    today = date.today()
    assert today.year in body["years"]
    assert (today.year - 1) in body["years"]
    # Newest first — the SPA's <select> renders in this order.
    assert body["years"] == sorted(body["years"], reverse=True)
    # Default selection is last calendar year (the typical use
    # case is "do my taxes in February for last year").
    assert body["default_year"] == today.year - 1


def test_years_includes_year_from_existing_transfer(
    client, test_store_id,
):
    """A store with a transfer dated 2022-03-01 must see 2022 in
    the picker even though it's older than this/last year."""
    from api.Modules.Transfers.Models import Transfer
    from tests._app import db
    with db_session():
        # `total_collected` is a derived property (send + fee +
        # federal_tax — see CLAUDE.md invariant #9), not a column,
        # so we don't pass it.
        t = Transfer(
            store_id=test_store_id,
            customer_id=None,
            company="Intermex",
            send_date=date(2022, 3, 1),
            send_amount=100, fee=5, federal_tax=0,
            sender_name="Old Sender",
            recipient_name="Old Recipient",
            country="MX",
        )
        db.session.add(t); db.session.commit()
    token = _login(client, test_store_id)
    body = client.get(
        "/api/v2/admin/tax-export/years",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert 2022 in body["years"]


def test_years_includes_year_from_existing_daily_report(
    client, test_store_id,
):
    """A store with a closed daily report dated 2021-11-15 must
    see 2021 in the picker."""
    from api.Modules.DailyBook.Models import DailyReport
    from tests._app import db
    with db_session():
        dr = DailyReport(
            store_id=test_store_id,
            report_date=date(2021, 11, 15),
        )
        db.session.add(dr); db.session.commit()
    token = _login(client, test_store_id)
    body = client.get(
        "/api/v2/admin/tax-export/years",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert 2021 in body["years"]


# ── Flask redirect ──────────────────────────────────────────


def test_legacy_admin_tax_export_redirects_to_app(
    logged_in_client,
):
    """Flask /admin/tax-export 301s to /app/admin/tax-export so
    sidebar links + old bookmarks still work after the SPA
    migration."""
    resp = logged_in_client.get(
        "/admin/tax-export", follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["Location"].startswith("/app/admin/tax-export")


def test_legacy_admin_tax_export_preserves_query_string(
    logged_in_client,
):
    """If the user hits /admin/tax-export?year=2024 (e.g. an
    older email link), the redirect must carry the year through
    so the SPA pre-selects the same year."""
    resp = logged_in_client.get(
        "/admin/tax-export?year=2024", follow_redirects=False,
    )
    assert resp.status_code == 301
    assert "year=2024" in resp.headers["Location"]
