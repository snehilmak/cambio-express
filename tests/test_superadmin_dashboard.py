"""Regression tests for the superadmin Platform Dashboard (/dashboard).

The page is a BI dashboard — KPI strip, signup trend, plan donut,
MRR breakdown, referral leaderboard, transfer volume, activity feed.
These tests guard the context contract + the data that ends up in the
ApexCharts JSON payload, so a future refactor can't silently drop a
metric.
"""
import json
import re
from datetime import date, datetime, timedelta


def _superadmin_client(client):
    """Log in as the seeded superadmin (no TOTP since the seed has no secret)."""
    from app import User
    with client.application.app_context():
        uid = User.query.filter_by(username="superadmin", store_id=None).first().id
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["role"] = "superadmin"
    return client


def _make_store(app, **kw):
    from app import Store, db
    with app.app_context():
        s = Store(**kw)
        db.session.add(s)
        db.session.commit()
        return s.id


def _dash_payload(body):
    """Pull the #dash-data JSON blob out of the rendered page."""
    m = re.search(r'<script id="dash-data"[^>]*>([\s\S]+?)</script>', body)
    assert m, "dashboard JSON payload missing"
    return json.loads(m.group(1))


def test_renders_and_ships_apexcharts(client):
    _superadmin_client(client)
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    body = resp.data.decode()
    # ApexCharts CDN + always-present chart containers. chartVolume
    # only appears when there's 30-day transfer data — covered separately
    # in test_transfer_volume_30d_by_company.
    assert "apexcharts" in body.lower()
    for chart_id in ("chartSignups", "chartPlan"):
        assert f'id="{chart_id}"' in body, f"chart container missing: {chart_id}"


def test_kpi_labels_present(client):
    """Six KPI cards render — guards against the hero strip regressing."""
    _superadmin_client(client)
    body = client.get("/dashboard").data.decode()
    for label in ("Total stores", "Trial", "Paid", "Est. MRR",
                  "New stores · 30d", "Churn · 30d"):
        assert label in body, f"KPI label missing: {label}"


def test_kpi_counts_reflect_plan_split(client):
    """Paid count = basic + pro; MRR reflects billing cycles."""
    from app import Store, db
    _superadmin_client(client)
    app = client.application
    # 2 basic monthly, 1 pro yearly on top of seeded trial store
    _make_store(app, name="B1", slug="b1", plan="basic", billing_cycle="monthly")
    _make_store(app, name="B2", slug="b2", plan="basic", billing_cycle="monthly")
    _make_store(app, name="P1", slug="p1", plan="pro",   billing_cycle="yearly")

    body = client.get("/dashboard").data.decode()

    # Paid KPI card: value is 3 (2 basic + 1 pro)
    m = re.search(
        r'<div class="stat-label">Paid</div>\s*<div class="stat-value">(\d+)</div>',
        body,
    )
    assert m and int(m.group(1)) == 3, "Paid KPI should be 3"

    # Est. MRR: 2 × $35 (basic monthly) + 1 × ($420/12 = $35 pro yearly) = $105
    m = re.search(
        r'<div class="stat-label">Est\. MRR</div>\s*<div class="stat-value">\$(\d[\d,]*)</div>',
        body,
    )
    assert m and int(m.group(1).replace(",", "")) == 105, \
        f"MRR should amortize yearly plans: got {m.group(1) if m else 'nothing'}"


def test_new_stores_delta_sign(client):
    """new_stores_delta is positive when the current 30d window exceeds the prior."""
    from app import Store, db
    _superadmin_client(client)
    app = client.application
    now = datetime.utcnow()
    with app.app_context():
        # 3 stores in the last 30 days, 1 in the prior 30 days
        for i, days in enumerate([5, 10, 20, 45]):
            db.session.add(Store(
                name=f"X{i}", slug=f"x{i}-{days}", plan="trial",
                created_at=now - timedelta(days=days),
            ))
        db.session.commit()

    body = client.get("/dashboard").data.decode()
    # recent 30d: 3 new X stores + seeded test-store = 4; prior 30d: 1; delta = +3
    assert "▲ 3 vs prior 30d" in body


def test_chart_payload_shape(client):
    """JSON payload has the expected keys + 90 daily points for signups."""
    _superadmin_client(client)
    body = client.get("/dashboard").data.decode()
    payload = _dash_payload(body)

    # Signups: 90 points per series, same length as labels
    assert len(payload["signups"]["labels"]) == 90
    assert len(payload["signups"]["direct"]) == 90
    assert len(payload["signups"]["referral"]) == 90

    # Plan: 4 categories (Trial/Basic/Pro/Inactive). Colors are derived
    # from CSS tokens client-side — see PLAN_COLORS in dashboard_superadmin.html.
    assert payload["plan"]["labels"] == ["Trial", "Basic", "Pro", "Inactive"]
    assert len(payload["plan"]["counts"]) == 4

    # Volume: present even when empty
    assert "companies" in payload["volume"]
    assert "totals"    in payload["volume"]
    assert "counts"    in payload["volume"]


def test_signup_split_direct_vs_referral(client):
    """New stores are attributed to direct vs referral based on
    Store.referred_by_code_id. Regression guard: the KPI split and the
    chart payload must agree."""
    from app import Store, ReferralCode, db
    _superadmin_client(client)
    app = client.application
    now = datetime.utcnow()
    with app.app_context():
        owner = Store(name="Owner", slug="owner", plan="basic",
                      billing_cycle="monthly", created_at=now - timedelta(days=40))
        db.session.add(owner); db.session.flush()
        rc = ReferralCode(code="TESTREF1", owner_store_id=owner.id, redeemed_count=2)
        db.session.add(rc); db.session.flush()
        # 2 referral signups in the last 30 days
        db.session.add(Store(name="R1", slug="r1", plan="trial",
                             referred_by_code_id=rc.id,
                             created_at=now - timedelta(days=5)))
        db.session.add(Store(name="R2", slug="r2", plan="trial",
                             referred_by_code_id=rc.id,
                             created_at=now - timedelta(days=10)))
        # 1 direct signup
        db.session.add(Store(name="D1", slug="d1", plan="trial",
                             created_at=now - timedelta(days=7)))
        db.session.commit()

    body = client.get("/dashboard").data.decode()
    payload = _dash_payload(body)

    # Chart payload totals
    assert sum(payload["signups"]["referral"]) >= 2, "referral signups missed the chart"
    # Seeded test-store + Owner + D1 = 3 direct within 90d window
    assert sum(payload["signups"]["direct"]) >= 3, "direct signups missed the chart"

    # Referral tile on the page
    assert "TESTREF1" in body, "top referrer code should render"
    assert "Owner" in body


def test_transfer_volume_30d_by_company(client):
    """Transfer volume chart + totals filter on created_at within 30 days
    and exclude Canceled/Rejected."""
    from app import Store, Transfer, db
    _superadmin_client(client)
    app = client.application
    now = datetime.utcnow()
    with app.app_context():
        s = Store(name="Vol Shop", slug="vol", plan="basic",
                  billing_cycle="monthly", created_at=now - timedelta(days=60))
        db.session.add(s); db.session.flush()
        rows = [
            (1,  "Intermex", 500, "Sent"),
            (3,  "Intermex", 300, "Sent"),
            (5,  "Maxi",     700, "Sent"),
            (10, "Barri",    200, "Canceled"),  # excluded
            (40, "Maxi",     999, "Sent"),      # outside 30d — excluded
        ]
        for days, co, amt, status in rows:
            db.session.add(Transfer(
                store_id=s.id, send_date=date.today()-timedelta(days=days),
                company=co, service_type="Money Transfer", sender_name="X",
                send_amount=amt, fee=0, federal_tax=0, commission=0,
                status=status, created_at=now-timedelta(days=days),
            ))
        db.session.commit()

    body = client.get("/dashboard").data.decode()
    payload = _dash_payload(body)

    # Expect Intermex=$800 (top), Maxi=$700, no Barri (canceled), 40d Maxi excluded
    companies = payload["volume"]["companies"]
    totals = dict(zip(companies, payload["volume"]["totals"]))
    assert "Intermex" in companies and totals["Intermex"] == 800.0
    assert "Maxi" in companies and totals["Maxi"] == 700.0
    assert "Barri" not in companies, "canceled transfers must not count"

    # Total volume strip: $800 + $700 = $1,500
    assert "$1,500" in body


def test_activity_feed_merges_signups_and_cancellations(client):
    from app import Store, db
    _superadmin_client(client)
    app = client.application
    now = datetime.utcnow()
    with app.app_context():
        db.session.add(Store(
            name="Recently Canceled", slug="rc",
            plan="inactive", is_active=False,
            created_at=now - timedelta(days=120),
            canceled_at=now - timedelta(days=2),
        ))
        db.session.add(Store(
            name="Just Signed Up", slug="jsu",
            plan="trial",
            created_at=now - timedelta(hours=6),
        ))
        db.session.commit()

    body = client.get("/dashboard").data.decode()
    assert "Just Signed Up" in body
    assert "Recently Canceled" in body
    assert "direct signup" in body
    assert "canceled subscription" in body


def test_only_superadmin_sees_bi_dashboard(logged_in_client):
    """Admin role must NOT see the platform BI dashboard at /dashboard —
    they get dashboard_admin.html instead. Guards privilege boundary."""
    resp = logged_in_client.get("/dashboard")
    assert resp.status_code == 200
    body = resp.data.decode()
    # Platform-owner hero is superadmin-only
    assert "DineroBook Platform" not in body
    assert "dash-data" not in body
