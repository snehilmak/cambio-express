"""Custom Period Comparison — operator can pick an arbitrary second
period via `?compare_from=YYYY-MM-DD&compare_to=YYYY-MM-DD`. Both
must be set; if either is missing or invalid the report falls back
to the auto-prior same-length window."""
from datetime import date


def _admin_login(client, store_id):
    from api.Modules.Tenancy.Models import Store
    from tests._app import db
    with client.application.app_context():
        s = db.session.get(Store, store_id)
        s.plan = "pro"; s.billing_cycle = "monthly"
        db.session.commit()


def _make_transfer(client, store_id, *, send_date, amount, fee=0.0,
                   federal_tax=0.0, company="Intermex",
                   confirm="X", status="Sent"):
    from api.Modules.Transfers.Models import Transfer
    from tests._app import db
    with client.application.app_context():
        t = Transfer(
            store_id=store_id, send_date=send_date,
            sender_name="S", recipient_name="R",
            country="MX", confirm_number=confirm,
            company=company, send_amount=amount,
            fee=fee, federal_tax=federal_tax, status=status,
        )
        db.session.add(t); db.session.commit()
        return t.id














def test_custom_compare_csv_export_includes_period_columns(client,
                                                            test_store_id):
    """The CSV column headers use the dynamic period labels — verify
    the custom compare window shows up as a column header."""
    from tests.conftest import login_admin
    _make_transfer(client, test_store_id, send_date=date(2026, 5, 5),
                   amount=100, confirm="X1")
    jwt = login_admin(client, test_store_id)
    resp = client.get(
        f"/api/v2/reports/period-comparison.csv"
        f"?store_ids={test_store_id}"
        f"&from=2026-05-01&to=2026-05-31"
        f"&compare_from=2025-05-01&compare_to=2025-05-31",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_data(as_text=True)
    # Custom compare window appears as a CSV column header.
    assert "May 01" in body and "May 31, 2025" in body
