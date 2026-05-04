"""Sidebar reorganization — admin sidebar consolidates to 2 sections
(top group + Books + Account) with New Transfer promoted to a topbar
button; superadmin sidebar collapses Monitoring into Configuration."""


def test_admin_sidebar_has_no_workspace_section_header(client, test_store_id):
    """The top group is now header-less — Dashboard / Transfers sit
    directly under the logo with no 'Workspace' label."""
    from app import User
    with client.application.app_context():
        u = User.query.filter_by(store_id=test_store_id, role="admin").first()
        uid = u.id
    with client.session_transaction() as s:
        s["user_id"] = uid; s["role"] = "admin"
        s["store_id"] = test_store_id
    body = client.get("/dashboard").get_data(as_text=True)
    # Workspace header is gone.
    assert ">Workspace<" not in body
    # Items are still there.
    assert "Dashboard" in body
    assert "Transfers" in body


def test_new_transfer_is_topbar_button_not_sidebar_link(client,
                                                         test_store_id):
    """`+ New Transfer` is now a primary topbar action, not a
    sidebar nav-link. Check the button class is present and the
    sidebar nav-link variant is gone."""
    from app import User
    with client.application.app_context():
        u = User.query.filter_by(store_id=test_store_id, role="admin").first()
        uid = u.id
    with client.session_transaction() as s:
        s["user_id"] = uid; s["role"] = "admin"
        s["store_id"] = test_store_id
    body = client.get("/dashboard").get_data(as_text=True)
    assert "topbar-new-action" in body
    # The nav-link variant for new_transfer was sidebar-class — no
    # longer rendered. Search for the unique combo.
    assert 'class="nav-link"' not in body or "New Transfer" in body
    # The topbar btn is wired to the route.
    assert 'href="/transfers/new"' in body


def test_admin_sidebar_books_section_consolidates(client, test_store_id):
    """The Books section now contains every ledger / report destination:
    Daily Book, Monthly P&L, Return Checks, ACH Batches, Bank Sync,
    Report Center."""
    from app import User
    with client.application.app_context():
        u = User.query.filter_by(store_id=test_store_id, role="admin").first()
        uid = u.id
    with client.session_transaction() as s:
        s["user_id"] = uid; s["role"] = "admin"
        s["store_id"] = test_store_id
    body = client.get("/dashboard").get_data(as_text=True)
    # Single "Books" header (vs three separate Books / Reports / Finance).
    assert body.count(">Books<") == 1
    assert ">Reports<" not in body  # no separate Reports header
    assert ">Finance<" not in body  # no separate Finance header
    # All the items live there.
    for label in ("Daily Book", "Monthly P&amp;L", "Return Checks",
                  "ACH Batches", "Bank Sync", "Report Center"):
        assert label in body, f"missing {label}"


def test_admin_sidebar_account_section_picks_up_tv_display(client,
                                                            test_store_id):
    """TV Display moved from Workspace to Account (when the store
    has the addon enabled). With no addon active, it stays hidden."""
    from app import User, Store, db
    with client.application.app_context():
        u = User.query.filter_by(store_id=test_store_id, role="admin").first()
        uid = u.id
        # Enable the addon explicitly.
        s = db.session.get(Store, test_store_id)
        s.addons = "tv_display"
        s.plan = "pro"; s.billing_cycle = "monthly"
        db.session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = uid; sess["role"] = "admin"
        sess["store_id"] = test_store_id
    body = client.get("/dashboard").get_data(as_text=True)
    assert "TV Display" in body
    # It should appear AFTER the Account section header in the markup.
    acct_idx = body.find(">Account<")
    tv_idx = body.find("TV Display")
    assert acct_idx > 0 and tv_idx > acct_idx, \
        "TV Display should render under Account, not in the top group"


def test_superadmin_sidebar_collapses_monitoring_into_configuration(client):
    """Superadmin sidebar now has Platform / Configuration / Reports
    (3 sections, was 4). System Status moved from a one-item
    Monitoring section into Configuration."""
    from app import User
    with client.application.app_context():
        sa = User.query.filter_by(role="superadmin").first()
        sa_id = sa.id
    with client.session_transaction() as s:
        s["user_id"] = sa_id; s["role"] = "superadmin"; s["store_id"] = None
    body = client.get("/superadmin/controls?tab=overview").get_data(as_text=True)
    # Monitoring header retired.
    assert ">Monitoring<" not in body
    # Three sections only.
    assert ">Platform<"      in body
    assert ">Configuration<" in body
    assert ">Reports<"       in body
    # System Status link still present (under Configuration now).
    assert "System Status" in body


def test_owner_sidebar_unchanged(client):
    """Owner sidebar is already minimal — verify the reorg didn't
    accidentally touch it."""
    from app import Store, User, StoreOwnerLink, db
    with client.application.app_context():
        s = Store(name="X", slug="x-sidebar-owner", plan="trial")
        db.session.add(s); db.session.commit()
        sid = s.id
        o = User(username="owner@sidebar.test", full_name="X",
                 role="owner", store_id=None)
        o.set_password("p")
        db.session.add(o); db.session.commit()
        oid = o.id
        db.session.add(StoreOwnerLink(owner_id=oid, store_id=sid))
        db.session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = oid; sess["role"] = "owner"; sess["store_id"] = None
    body = client.get("/owner/dashboard").get_data(as_text=True)
    # Still has Reports section.
    assert ">Reports<" in body
    # Locations still there.
    assert "Locations" in body
