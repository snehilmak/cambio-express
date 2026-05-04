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


def _make_transfer(client, store_id, *, send_date, amount, fee=2.0,
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


def test_view_tabs_show_for_multi_view_report(client, test_store_id):
    """Sales by Company opted into 3 views — the bottom tab bar
    should render with all three labels."""
    _admin_login(client, test_store_id)
    resp = client.get("/reports/sales-by-company")
    body = resp.get_data(as_text=True)
    assert 'class="report-page__view-tabs"' in body
    assert "Summary" in body
    assert "Graph" in body
    assert "Detail" in body


def test_view_tabs_hidden_when_only_summary(client, test_store_id):
    """A report that didn't opt into Graph/Detail (e.g. Period P&L)
    should NOT render the tab bar."""
    _admin_login(client, test_store_id)
    resp = client.get("/reports/period-pl")
    body = resp.get_data(as_text=True)
    assert 'class="report-page__view-tabs"' not in body


def test_view_param_switches_template(client, test_store_id):
    """`?view=graph` should switch the body template; `?view=detail`
    too. The header / KPIs / period filter all stay the same."""
    _admin_login(client, test_store_id)
    today = date.today()
    _make_transfer(client, test_store_id, send_date=today,
                   amount=200, company="Intermex", confirm="A")
    _make_transfer(client, test_store_id, send_date=today,
                   amount=100, company="Maxi", confirm="B")

    summary = client.get("/reports/sales-by-company").get_data(as_text=True)
    graph   = client.get("/reports/sales-by-company?view=graph").get_data(as_text=True)
    detail  = client.get("/reports/sales-by-company?view=detail").get_data(as_text=True)

    # Graph view renders bar wrappers.
    assert 'class="report-graph"' in graph
    assert 'class="report-graph__bar"' in graph
    # Detail view renders the table.
    assert 'class="report-detail__table"' in detail
    # Summary view does NOT render either of those.
    assert 'class="report-graph"' not in summary
    assert 'class="report-detail__table"' not in summary


def test_active_view_tab_marked(client, test_store_id):
    """The currently-active tab should have the .is-active class."""
    _admin_login(client, test_store_id)
    body = client.get("/reports/sales-by-company?view=graph").get_data(as_text=True)
    # The Graph tab anchor should have is-active.
    assert "is-active" in body
    # And the link should preserve the view param.
    assert "view=graph" in body


def test_unknown_view_falls_back_to_first(client, test_store_id):
    """Bogus ?view= values default to the first registered view
    (summary), no 500."""
    _admin_login(client, test_store_id)
    resp = client.get("/reports/sales-by-company?view=nope")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # Summary tab is the active one.
    assert 'class="report-page__view-tab is-active"' in body


def test_graph_view_handles_empty_period(client, test_store_id):
    """No transfers in window — Graph view shows the empty-state."""
    _admin_login(client, test_store_id)
    resp = client.get("/reports/sales-by-company?view=graph")
    body = resp.get_data(as_text=True)
    assert "No data to chart" in body


def test_detail_view_uses_configured_columns(client, test_store_id):
    """Sales by Company configured detail_columns. The table headers
    should match those, not the raw row keys."""
    _admin_login(client, test_store_id)
    today = date.today()
    _make_transfer(client, test_store_id, send_date=today,
                   amount=42, company="Intermex", confirm="DC1")
    body = client.get(
        "/reports/sales-by-company?view=detail").get_data(as_text=True)
    # Custom column labels (Title-cased, friendly).
    assert "<th>Company</th>" in body
    assert "<th>Total Sent</th>" in body
    # Raw key like "sent" not used as header.
    assert "<th>sent</th>" not in body
