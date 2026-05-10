"""Custom Period Comparison — operator can pick an arbitrary second
period via `?compare_from=YYYY-MM-DD&compare_to=YYYY-MM-DD`. Both
must be set; if either is missing or invalid the report falls back
to the auto-prior same-length window."""
from datetime import date


def _admin_login(client, store_id):
    from app import User, Store, db
    with client.application.app_context():
        u = User.query.filter_by(store_id=store_id, role="admin").first()
        uid = u.id
        s = db.session.get(Store, store_id)
        s.plan = "pro"; s.billing_cycle = "monthly"
        db.session.commit()
    with client.session_transaction() as s:
        s["user_id"] = uid; s["role"] = "admin"
        s["store_id"] = store_id


def _make_transfer(client, store_id, *, send_date, amount, fee=0.0,
                   federal_tax=0.0, company="Intermex",
                   confirm="X", status="Sent"):
    from app import Transfer, db
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
    _admin_login(client, test_store_id)
    _make_transfer(client, test_store_id, send_date=date(2026, 5, 5),
                   amount=100, confirm="X1")
    resp = client.get(
        "/reports/period-comparison.csv?from=2026-05-01&to=2026-05-31"
        "&compare_from=2025-05-01&compare_to=2025-05-31"
    )
    body = resp.get_data(as_text=True)
    # Custom compare window appears as a CSV column header.
    assert "May 01" in body and "May 31, 2025" in body
