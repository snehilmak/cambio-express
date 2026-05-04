"""Tests for the year-end Tax Export Pack.

Verifies the route renders, the ZIP download is a valid archive,
and each file inside has the expected shape.
"""
import csv
import io
import zipfile
from datetime import date


def _admin_login(client, store_id):
    from app import User, Store, db
    with client.application.app_context():
        u = User.query.filter_by(store_id=store_id, role="admin").first()
        uid = u.id
        s = db.session.get(Store, store_id)
        s.plan = "pro"
        db.session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "admin"
        sess["store_id"] = store_id


def _seed_transfer(store_id, *, send_date, amount=500.0, fee=5.0,
                    sender="Maria"):
    from app import Transfer, db
    with db.session.no_autoflush:
        t = Transfer(
            store_id=store_id, send_date=send_date,
            sender_name=sender, recipient_name="Carlos",
            country="MX", confirm_number="X",
            company="Intermex", send_amount=amount,
            fee=fee, federal_tax=round(amount * 0.01, 2),
            status="Sent",
        )
        db.session.add(t); db.session.commit()


def test_tax_export_landing_renders(client, test_store_id):
    _admin_login(client, test_store_id)
    resp = client.get("/admin/tax-export")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Tax Export Pack" in body
    assert "Download" in body
    # Year picker should default to last year.
    last_year = date.today().year - 1
    assert str(last_year) in body


def test_tax_export_zip_returns_valid_archive(client, test_store_id):
    _admin_login(client, test_store_id)
    from app import app as flask_app
    with flask_app.app_context():
        # Seed a transfer last year so the export has content.
        last_year = date.today().year - 1
        _seed_transfer(test_store_id,
                        send_date=date(last_year, 6, 15),
                        amount=750.0, fee=10.0)

    resp = client.get(f"/admin/tax-export.zip?year={date.today().year - 1}")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == "application/zip"
    assert "attachment" in resp.headers["Content-Disposition"]
    assert ".zip" in resp.headers["Content-Disposition"]

    # Open the ZIP and verify file contents.
    buf = io.BytesIO(resp.data)
    with zipfile.ZipFile(buf, mode="r") as zf:
        names = zf.namelist()
        last_year = date.today().year - 1
        assert f"transfers_{last_year}.csv" in names
        assert f"monthly_pl_{last_year}.csv" in names
        assert f"daily_summary_{last_year}.csv" in names
        assert f"customers_{last_year}.csv" in names
        assert "README.txt" in names

        # Transfers CSV has the seeded row.
        transfers = zf.read(f"transfers_{last_year}.csv").decode("utf-8")
        rows = list(csv.reader(io.StringIO(transfers)))
        assert rows[0][0] == "Date"   # header
        assert any("Maria" in r for r in rows[1:]), "seeded sender missing"

        # Monthly P&L CSV has 12 month rows (one per month).
        pl = zf.read(f"monthly_pl_{last_year}.csv").decode("utf-8")
        pl_rows = list(csv.reader(io.StringIO(pl)))
        # 1 header + 12 month rows
        assert len(pl_rows) == 13

        # README mentions the store and year.
        readme = zf.read("README.txt").decode("utf-8")
        assert str(last_year) in readme


def test_tax_export_filename_includes_store_slug_and_year(client, test_store_id):
    _admin_login(client, test_store_id)
    resp = client.get("/admin/tax-export.zip?year=2024")
    assert resp.status_code == 200
    cd = resp.headers["Content-Disposition"]
    assert "test-store" in cd
    assert "2024" in cd


def test_tax_export_employee_role_blocked(client, test_store_id):
    """Employees can't download the tax pack — admin-only by decorator."""
    from app import User, db
    with client.application.app_context():
        # Create an employee user.
        u = User(username="cashier@test.com", store_id=test_store_id,
                 role="employee", full_name="Cashier")
        u.set_password("p"); db.session.add(u); db.session.commit()
        uid = u.id
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "employee"
        sess["store_id"] = test_store_id

    resp = client.get("/admin/tax-export.zip?year=2024",
                       follow_redirects=False)
    # @admin_required redirects, abort(403)s, or 302s — anything not 200.
    assert resp.status_code != 200


def test_tax_export_invalid_year_falls_back(client, test_store_id):
    """A garbage year query string shouldn't crash; route should default
    to last year."""
    _admin_login(client, test_store_id)
    resp = client.get("/admin/tax-export.zip?year=not-a-year")
    assert resp.status_code == 200
    last_year = date.today().year - 1
    assert str(last_year) in resp.headers["Content-Disposition"]
