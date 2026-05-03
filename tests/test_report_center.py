"""Report Center scaffold tests.

The /reports + /owner/reports pages are a UI shell built on top of
the _REPORT_CATEGORIES registry. Reports flip from "Coming soon"
to "View" once their endpoint is wired. These tests cover the
scaffold itself: route auth, rendering of a known wired report
(Monthly P&L), and rendering of a known unwired one (Top Senders).
"""


def _admin_login(client, store_id):
    from app import User, Store, db
    with client.application.app_context():
        u = User.query.filter_by(store_id=store_id, role="admin").first()
        uid = u.id
        s = db.session.get(Store, store_id)
        s.plan = "pro"
        s.billing_cycle = "monthly"
        db.session.commit()
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["role"] = "admin"
        s["store_id"] = store_id


def test_admin_reports_page_renders(client, test_store_id):
    _admin_login(client, test_store_id)
    resp = client.get("/reports")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # Header + every category label render.
    assert "Report Center" in body
    for label in ("Sales", "Financial", "Operations", "Customers", "Audit"):
        assert label in body


def test_wired_report_links_to_existing_route(client, test_store_id):
    """Monthly P&L is wired to monthly_list — its card should have
    a real <a href> to the route, not a Coming-soon pill."""
    _admin_login(client, test_store_id)
    resp = client.get("/reports")
    body = resp.get_data(as_text=True)
    assert 'href="/monthly"' in body or "monthly_list" in body
    # Ensure the wired card has a button, not the pill.
    # The Monthly P&L block is identified by its label; we just check
    # that at least one View button appears (proves wiring works).
    assert ">View<" in body


def test_unwired_reports_show_coming_soon(client, test_store_id):
    """Reports without an endpoint render the Coming-soon pill."""
    _admin_login(client, test_store_id)
    resp = client.get("/reports")
    body = resp.get_data(as_text=True)
    assert "Coming soon" in body
    # Top Senders is currently unwired — its label should appear
    # alongside a coming-soon pill (we only assert label presence;
    # the row-level pairing is exercised visually).
    assert "Top Senders" in body


def test_reports_route_requires_admin(client):
    """Anonymous user gets bounced to login."""
    resp = client.get("/reports", follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert "/login" in resp.headers.get("Location", "")


def test_owner_reports_page_renders(client):
    """Owner gets the same scaffold under /owner/reports."""
    from app import User, Store, StoreOwnerLink, db
    with client.application.app_context():
        s = Store(name="Owner Store", slug="rc-owner-store", plan="trial")
        db.session.add(s); db.session.commit()
        sid = s.id
        o = User(username="owner@reports.test", full_name="Reporter",
                 role="owner", store_id=None)
        o.set_password("ownerpass123")
        db.session.add(o); db.session.commit()
        oid = o.id
        db.session.add(StoreOwnerLink(owner_id=oid, store_id=sid))
        db.session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = oid
        sess["role"] = "owner"
        sess["store_id"] = None
    resp = client.get("/owner/reports")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Report Center" in body
    assert "Sales" in body
    assert "Coming soon" in body
