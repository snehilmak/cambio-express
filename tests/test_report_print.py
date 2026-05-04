"""Print / PDF export — every report page surfaces a button that
calls window.print(), and the print stylesheet strips chrome so
the result is page-ready."""


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


def test_print_button_renders_on_report_pages(client, test_store_id):
    """Every report page should have the Print / PDF button."""
    _admin_login(client, test_store_id)
    for slug in ("sales-by-company", "period-pl",
                 "high-value-transfers", "fees-vs-tax"):
        body = client.get(f"/reports/{slug}").get_data(as_text=True)
        assert 'class="btn btn-outline btn-sm js-report-print"' in body, slug
        assert 'window.print()' in body, slug
        assert "Print / PDF" in body, slug


def test_print_button_on_owner_reports(client):
    """Owner mirror pages should also have the Print button."""
    from app import User, Store, StoreOwnerLink, db
    with client.application.app_context():
        s = Store(name="P", slug="print-owner", plan="trial")
        db.session.add(s); db.session.commit()
        sid = s.id
        o = User(username="po@x.com", full_name="P Owner",
                 role="owner", store_id=None)
        o.set_password("pw")
        db.session.add(o); db.session.commit()
        oid = o.id
        db.session.add(StoreOwnerLink(owner_id=oid, store_id=sid))
        db.session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = oid; sess["role"] = "owner"; sess["store_id"] = None
    body = client.get("/owner/reports/sales-by-company").get_data(as_text=True)
    assert "Print / PDF" in body
    assert "window.print()" in body


def test_print_button_on_superadmin_reports(client):
    from app import User
    with client.application.app_context():
        sa = User.query.filter_by(role="superadmin").first()
        sa_id = sa.id
    with client.session_transaction() as s:
        s["user_id"] = sa_id; s["role"] = "superadmin"; s["store_id"] = None
    body = client.get(
        "/superadmin/reports/active-stores-by-plan").get_data(as_text=True)
    assert "Print / PDF" in body


def test_print_css_rules_present():
    """The print stylesheet block exists in content.css and hides
    the obvious chrome elements when printing."""
    with open("static/content.css") as f:
        css = f.read()
    assert "@media print" in css
    # Sample rules.
    assert ".sidebar" in css and "display: none !important" in css
    assert ".js-report-print" in css
    assert ".report-page__view-tabs" in css
    assert "@page" in css
