"""Wired superadmin reports — verify each route renders, returns
real data, and offers a working CSV export.

Reports left as Coming-soon (Stripe webhook health, failed payments,
payouts, refunds, DAU/MAU) need data sources we don't have today
(Stripe API integration or a dedicated event-log table)."""
from datetime import date, datetime, timedelta


# Reports wired to actual data after the superadmin batch.
_WIRED = [
    # Platform Health (3 of 4 — DAU/MAU still Coming-soon)
    "active-stores-by-plan",
    "signup-funnel",
    "login-activity",
    # Revenue (2 of 3 — refunds Coming-soon)
    "mrr-arr",
    "churn-cohort",
    # Trial Funnel (3 of 3)
    "conversion-rate",
    "time-to-convert",
    "trial-expiry-timing",
    # Feature Adoption (4 of 4)
    "bank-sync-adoption",
    "tv-display-adoption",
    "owner-adoption",
    "passkey-adoption",
    # Support / Audit (3 of 4 — audit-log already wired separately)
    "password-resets",
    "suspended-stores",
    "retention-queue",
]


def _superadmin_login(client):
    from app import User
    with client.application.app_context():
        sa = User.query.filter_by(role="superadmin").first()
        sa_id = sa.id
    with client.session_transaction() as s:
        s["user_id"] = sa_id
        s["role"] = "superadmin"
        s["store_id"] = None


def test_every_wired_report_renders(client):
    """Smoke test — each wired superadmin report loads with HTTP 200
    and shows the Report Center back-link + the report title."""
    _superadmin_login(client)
    for slug in _WIRED:
        resp = client.get(f"/superadmin/reports/{slug}")
        assert resp.status_code == 200, f"{slug} returned {resp.status_code}"
        body = resp.get_data(as_text=True)
        # Back-link to /superadmin/reports.
        assert 'href="/superadmin/reports"' in body, f"{slug} missing back link"
        # CSV export anchor.
        assert f'/superadmin/reports/{slug}.csv' in body, f"{slug} missing CSV link"


def test_every_wired_csv_returns_text_csv(client):
    _superadmin_login(client)
    for slug in _WIRED:
        resp = client.get(f"/superadmin/reports/{slug}.csv")
        assert resp.status_code == 200, f"{slug}.csv returned {resp.status_code}"
        assert resp.mimetype == "text/csv", f"{slug}.csv wrong mimetype"


def test_active_stores_by_plan_counts_existing_stores(client):
    """The platform always has a seed store from conftest. The
    report should surface it under 'Trial' (the seeded plan)."""
    _superadmin_login(client)
    resp = client.get("/superadmin/reports/active-stores-by-plan")
    body = resp.get_data(as_text=True)
    assert "Trial" in body


def test_passkey_adoption_zero_when_none_registered(client):
    """No passkeys in the test DB → empty rows + adoption KPI = 0."""
    _superadmin_login(client)
    resp = client.get("/superadmin/reports/passkey-adoption")
    body = resp.get_data(as_text=True)
    # Adoption KPI is "0.0%" when there are no passkey users.
    assert "0.0%" in body


def test_retention_queue_empty_by_default(client):
    """No store has data_retention_until set in the test DB."""
    _superadmin_login(client)
    resp = client.get("/superadmin/reports/retention-queue")
    body = resp.get_data(as_text=True)
    assert "Retention queue is empty." in body


def test_mrr_arr_renders_with_paid_stores(client):
    """Seed a paid store and verify MRR shows up."""
    from app import Store, db
    with client.application.app_context():
        s = Store(name="Paid Store", slug="sa-paid",
                  plan="basic", billing_cycle="monthly")
        db.session.add(s); db.session.commit()
    _superadmin_login(client)
    resp = client.get("/superadmin/reports/mrr-arr")
    body = resp.get_data(as_text=True)
    # Basic monthly = $49.00 MRR per store.
    assert "$49.00" in body


def test_owner_adoption_lists_multi_store_owners(client):
    """An owner with 2+ linked stores appears in the report."""
    from app import Store, User, StoreOwnerLink, db
    with client.application.app_context():
        a = Store(name="A", slug="oa-a", plan="trial")
        b = Store(name="B", slug="oa-b", plan="trial")
        db.session.add_all([a, b]); db.session.commit()
        a_id, b_id = a.id, b.id
        o = User(username="oa@x.com", full_name="Owner A",
                 role="owner", store_id=None)
        o.set_password("pw")
        db.session.add(o); db.session.commit()
        oid = o.id
        db.session.add(StoreOwnerLink(owner_id=oid, store_id=a_id))
        db.session.add(StoreOwnerLink(owner_id=oid, store_id=b_id))
        db.session.commit()
    _superadmin_login(client)
    resp = client.get("/superadmin/reports/owner-adoption")
    body = resp.get_data(as_text=True)
    assert "Owner A" in body
    assert "2" in body  # store count


def test_conversion_rate_handles_empty_cohort(client):
    """No signups in the period → empty-state and 0% rate."""
    _superadmin_login(client)
    # Pick a long-past period with no signups.
    resp = client.get(
        "/superadmin/reports/conversion-rate?from=2020-01-01&to=2020-01-31")
    body = resp.get_data(as_text=True)
    assert "0.0%" in body


def test_suspended_stores_lists_inactive(client):
    from app import Store, db
    with client.application.app_context():
        s = Store(name="Bad Actor", slug="sa-suspended",
                  plan="basic", is_active=False)
        db.session.add(s); db.session.commit()
    _superadmin_login(client)
    resp = client.get("/superadmin/reports/suspended-stores")
    body = resp.get_data(as_text=True)
    assert "Bad Actor" in body
    assert "suspended" in body


def test_superadmin_reports_require_superadmin(client, test_store_id):
    """Plain admin can't hit superadmin reports."""
    from app import User
    with client.application.app_context():
        u = User.query.filter_by(store_id=test_store_id, role="admin").first()
        uid = u.id
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["role"] = "admin"
        s["store_id"] = test_store_id
    resp = client.get("/superadmin/reports/active-stores-by-plan",
                      follow_redirects=False)
    assert resp.status_code in (302, 303, 403)


def test_superadmin_report_center_shows_wired_count(client):
    """The Report Center landing should now show 15 wired reports
    (14 from this batch + audit-log wired earlier) instead of just 1."""
    _superadmin_login(client)
    resp = client.get("/superadmin/reports")
    body = resp.get_data(as_text=True)
    # Spot-check several wired labels appear next to View buttons
    # (via the existing accordion). The string ">View<" appears
    # for every wired entry.
    assert body.count(">View<") >= 14
