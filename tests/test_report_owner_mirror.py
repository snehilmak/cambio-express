"""Owner Report Center end-to-end coverage.

After the route refactor:
  - admin /reports/<slug>(.csv)? are unchanged; admin keeps single-
    store scope.
  - owner /owner/reports/<slug>(.csv)? are auto-registered mirrors of
    every admin /reports/<slug> route. Same handler; scope widens to
    the owner's umbrella store list via _report_scope_ids() reading
    role from the session.

These tests verify the mirror registration covers every report,
that owners actually see umbrella data (transfers logged in linked
sibling stores show up), that the back-link target on the report
page swaps to /owner/reports, and that the CSV export points at the
owner-prefixed CSV endpoint.
"""
from datetime import date


# Reports without explicit `endpoint` in the registry are Coming-soon
# (none today) — every wired admin report should have an owner mirror.
_ADMIN_REPORT_PATHS = [
    "/reports/sales-by-company",
    "/reports/sales-by-service-type",
    "/reports/sales-by-employee",
    "/reports/top-customers",
    "/reports/top-senders",
    "/reports/top-recipients",
    "/reports/by-destination-country",
    "/reports/new-vs-returning",
    "/reports/returned-check-status",
    "/reports/bank-transactions-breakdown",
    "/reports/daily-drops",
    "/reports/check-deposits",
    "/reports/high-value-transfers",
    "/reports/employee-activity",
    "/reports/bank-rule-audit",
    "/reports/cancelled-transfers",
    "/reports/period-pl",
    "/reports/ach-volume",
    "/reports/bank-charges-by-account",
    "/reports/period-comparison",
    "/reports/fees-vs-tax",
]


def _owner_with_two_stores(client):
    """Build an owner linked to two stores; return (client, owner_id,
    [store_a_id, store_b_id]) with the client logged in as owner."""
    from app import User, Store, StoreOwnerLink, db
    with client.application.app_context():
        a = Store(name="A", slug="reports-owner-a", plan="trial")
        b = Store(name="B", slug="reports-owner-b", plan="trial")
        db.session.add_all([a, b]); db.session.commit()
        a_id, b_id = a.id, b.id
        o = User(username="reports-owner@x.com", full_name="Reports Owner",
                 role="owner", store_id=None)
        o.set_password("ownerpass123")
        db.session.add(o); db.session.commit()
        oid = o.id
        db.session.add(StoreOwnerLink(owner_id=oid, store_id=a_id))
        db.session.add(StoreOwnerLink(owner_id=oid, store_id=b_id))
        db.session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = oid
        sess["role"] = "owner"
        sess["store_id"] = None
    return client, oid, [a_id, b_id]


def _make_transfer(client, store_id, *, send_date, amount, fee=0.0,
                   federal_tax=0.0, company="Intermex",
                   sender_name="S", recipient_name="R",
                   confirm="X", status="Sent"):
    from app import Transfer, db
    with client.application.app_context():
        t = Transfer(
            store_id=store_id, send_date=send_date,
            sender_name=sender_name, recipient_name=recipient_name,
            country="MX", confirm_number=confirm,
            company=company, send_amount=amount,
            fee=fee, federal_tax=federal_tax, status=status,
        )
        db.session.add(t); db.session.commit()
        return t.id


def test_every_admin_report_has_owner_mirror(client):
    """Every admin /reports/<slug> route was paired with a
    /owner/reports/<slug> mirror by _register_owner_report_mirrors."""
    from app import app as flask_app
    rule_paths = {r.rule for r in flask_app.url_map.iter_rules()}
    for admin_path in _ADMIN_REPORT_PATHS:
        owner_path = "/owner" + admin_path
        assert owner_path in rule_paths, \
            f"Missing owner mirror for {admin_path}"
        # CSV variant too.
        assert (owner_path + ".csv") in rule_paths, \
            f"Missing owner CSV mirror for {admin_path}.csv"


def test_owner_routes_reject_admin_session(client, test_store_id):
    """The owner mirror routes use @owner_required — store-admins
    can't slip in via the owner URL."""
    from app import User, Store, db
    with client.application.app_context():
        u = User.query.filter_by(store_id=test_store_id, role="admin").first()
        uid = u.id
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "admin"
        sess["store_id"] = test_store_id
    resp = client.get("/owner/reports/sales-by-company",
                      follow_redirects=False)
    # Owner-required routes bounce admins (same gate that protects
    # /owner/dashboard). Either redirect to /dashboard or 403.
    assert resp.status_code in (302, 303, 403)


def test_owner_sales_by_company_aggregates_across_linked_stores(client):
    """Owner hitting /owner/reports/sales-by-company sees the sum
    across both linked stores; an admin in just one of them only sees
    that store's slice."""
    c, oid, (a_id, b_id) = _owner_with_two_stores(client)
    today = date.today()
    _make_transfer(c, a_id, send_date=today, amount=500,
                   company="Intermex", confirm="A1")
    _make_transfer(c, b_id, send_date=today, amount=300,
                   company="Maxi", confirm="B1")
    resp = c.get("/owner/reports/sales-by-company")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # Both companies surfaced — totals sum across the umbrella.
    assert "Intermex" in body
    assert "Maxi" in body
    assert "$800.00" in body  # 500 + 300


def test_owner_back_link_targets_owner_reports(client):
    """The report page's back link should send owners back to
    /owner/reports, not /reports."""
    c, *_ = _owner_with_two_stores(client)
    resp = c.get("/owner/reports/sales-by-company")
    body = resp.get_data(as_text=True)
    # url_for('owner_reports') resolves to /owner/reports.
    assert 'href="/owner/reports"' in body
    # And NOT the admin /reports.
    assert 'href="/reports"' not in body


def test_owner_csv_export_link_targets_owner_endpoint(client):
    """The CSV export anchor on the owner page should point at the
    owner CSV endpoint, not the admin one."""
    c, *_ = _owner_with_two_stores(client)
    resp = c.get("/owner/reports/sales-by-company")
    body = resp.get_data(as_text=True)
    assert 'href="/owner/reports/sales-by-company.csv' in body
    assert 'href="/reports/sales-by-company.csv' not in body


def test_owner_csv_export_returns_umbrella_data(client):
    """The owner CSV pulls data from every linked store, same scope
    as the HTML view."""
    c, oid, (a_id, b_id) = _owner_with_two_stores(client)
    today = date.today()
    _make_transfer(c, a_id, send_date=today, amount=500,
                   company="Intermex", confirm="A1")
    _make_transfer(c, b_id, send_date=today, amount=300,
                   company="Intermex", confirm="B1")
    resp = c.get("/owner/reports/sales-by-company.csv")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    body = resp.get_data(as_text=True)
    # Both transfers (across both stores) sum into the single Intermex
    # row.
    assert "Intermex,2,800.00" in body


def test_owner_report_center_link_resolves_to_owner_endpoints(client):
    """The owner Report Center moved to React in PR #406. The
    invariant — owner-side report cards link to /owner/reports/*,
    not the admin /reports/* — is now an API contract on
    /api/v2/owner/reports."""
    from app import User, Store, StoreOwnerLink, db
    with client.application.app_context():
        s = Store(name="Owner Mirror", slug="reports-owner-mirror",
                  plan="pro", billing_cycle="monthly")
        db.session.add(s); db.session.commit()
        sid = s.id
        o = User(username="reports-owner-mirror@x.com",
                 full_name="Reports Owner",
                 role="owner", store_id=None)
        o.set_password("ownerpass123")
        db.session.add(o); db.session.commit()
        oid = o.id
        db.session.add(StoreOwnerLink(owner_id=oid, store_id=sid))
        db.session.commit()
    jwt = client.post(
        "/api/v2/auth/login",
        json={"username": "reports-owner-mirror@x.com",
              "password": "ownerpass123",
              "store_id": None},
    ).get_json()["access_token"]
    resp = client.get(
        "/api/v2/owner/reports",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    rows = [r for cat in resp.get_json()["categories"] for r in cat["reports"]]
    sales = next((r for r in rows if r["key"] == "sales_by_company"), None)
    assert sales is not None
    assert sales["url"] == "/owner/reports/sales-by-company"
    # No admin-side paths leak through the owner-prefix lookup.
    for r in rows:
        if r.get("url"):
            assert not r["url"].startswith("/reports/"), r


def test_admin_reports_still_store_scoped(client, test_store_id):
    """Refactor regression check — admin must still see only their
    store's data (not data from other stores in the DB)."""
    from app import User, Store, db
    # Setup: log admin into test_store_id, but also create a sibling
    # store with transfers; the admin must NOT see them.
    sibling = None
    with client.application.app_context():
        s = Store(name="Sibling", slug="reports-admin-sibling", plan="trial")
        db.session.add(s); db.session.commit()
        sibling = s.id
        u = User.query.filter_by(store_id=test_store_id,
                                  role="admin").first()
        uid = u.id
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "admin"
        sess["store_id"] = test_store_id
    today = date.today()
    _make_transfer(client, test_store_id, send_date=today, amount=100,
                   sender_name="Mine", confirm="MINE")
    _make_transfer(client, sibling, send_date=today, amount=999,
                   sender_name="Other Store", confirm="OTHER")
    resp = client.get("/reports/sales-by-company")
    body = resp.get_data(as_text=True)
    # Admin only sees their store's $100.
    assert "$100.00" in body
    # The sibling store's $999 must NOT bleed through.
    assert "$999.00" not in body
