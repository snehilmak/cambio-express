"""Bottom sub-tabs on individual reports — Summary / Graph / Detail.

Reports opt in via `views=` on _make_report_routes. Selected reports
(Sales by Company, by Service Type, by Employee, by Country, ACH
Volume) expose all three views; the rest stay summary-only and the
tab bar is hidden.

Switching is via `?view=summary|graph|detail`. Skeleton template
renders generic Graph + Detail bodies driven by `graph_label_field`
/ `graph_value_field` / `detail_columns` route config.
"""
from datetime import date


def _admin_login(client, store_id):
    from api.Modules.Tenancy.Models import Store, User
    from app import db
    with client.application.app_context():
        u = User.query.filter_by(store_id=store_id, role="admin").first()
        uid = u.id
        s = db.session.get(Store, store_id)
        s.plan = "pro"; s.billing_cycle = "monthly"
        db.session.commit()
    with client.session_transaction() as s:
        s["user_id"] = uid; s["role"] = "admin"
        s["store_id"] = store_id


def _make_transfer(client, store_id, *, send_date, amount, fee=2.0,
                   federal_tax=0.0, company="Intermex",
                   confirm="X", status="Sent"):
    from api.Modules.Transfers.Models import Transfer
    from app import db
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




def test_view_tabs_hidden_when_only_summary(client, test_store_id):
    """A report that didn't opt into Graph/Detail (e.g. Period P&L)
    should NOT render the tab bar."""
    _admin_login(client, test_store_id)
    resp = client.get("/reports/period-pl")
    body = resp.get_data(as_text=True)
    assert 'class="report-page__view-tabs"' not in body










