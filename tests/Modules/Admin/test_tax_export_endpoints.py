"""HTTP integration tests for the Admin tax-export endpoints.

  GET /api/v2/admin/tax-export/years  → picker dropdown payload
  GET /api/v2/admin/tax-export.zip    → year-end packet ZIP

The matching React page (frontend/src/routes/AdminTaxExport.tsx)
calls both endpoints — the year picker on mount, the ZIP on the
download button.
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


# ── /tax-export.zip ─────────────────────────────────────────


def test_tax_pack_requires_jwt(client):
    resp = client.get("/api/v2/admin/tax-export.zip?year=2024")
    assert resp.status_code == 401


def test_tax_pack_returns_zip_with_expected_files(
    client, test_store_id,
):
    """Happy path — admin downloads the ZIP, gets a non-empty
    archive with each expected file."""
    import io
    import zipfile
    token = _login(client, test_store_id)
    resp = client.get(
        f"/api/v2/admin/tax-export.zip?year={date.today().year}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == "application/zip"
    cd = resp.headers["Content-Disposition"]
    assert "attachment" in cd
    assert ".zip" in cd
    payload = resp.get_data()
    assert len(payload) > 0
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        names = set(zf.namelist())
        year = date.today().year
        assert f"transfers_{year}.csv" in names
        assert f"monthly_pl_{year}.csv" in names
        assert f"daily_summary_{year}.csv" in names
        assert f"customers_{year}.csv" in names
        assert "README.txt" in names


def test_tax_pack_transfers_csv_has_header_row(client, test_store_id):
    """The transfers CSV always has a header row even when there
    are zero rows for the year."""
    import io
    import zipfile
    token = _login(client, test_store_id)
    resp = client.get(
        f"/api/v2/admin/tax-export.zip?year={date.today().year}",
        headers={"Authorization": f"Bearer {token}"},
    )
    payload = resp.get_data()
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        year = date.today().year
        text = zf.read(f"transfers_{year}.csv").decode("utf-8")
    first_line = text.splitlines()[0]
    assert "Send Date" in first_line
    assert "Total Collected" in first_line


def test_tax_pack_rejects_cashier_role(client, test_store_id):
    """An employee-role JWT carries a store scope but can't
    download — same gating as /customers/export.csv."""
    from api.Modules.Tenancy.Models import User
    with db_session():
        u = User(
            store_id=test_store_id, username="cashier@test.com",
            full_name="Cashier", role="employee",
        )
        u.set_password("p123pass!")
        db.session.add(u); db.session.commit()
    login = client.post(
        "/api/v2/auth/login",
        json={
            "username": "cashier@test.com", "password": "p123pass!",
            "store_id": test_store_id,
        },
    )
    token = login.get_json()["access_token"]
    resp = client.get(
        "/api/v2/admin/tax-export.zip?year=2024",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_tax_pack_rejects_invalid_year(client, test_store_id):
    """Year validation: < 2000 or > 2100 → 422 from Pydantic."""
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/admin/tax-export.zip?year=1999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
