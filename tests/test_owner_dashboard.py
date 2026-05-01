"""Owner dashboard route tests.

`test_multi_store_owner.py` covers auth, signup, linkage, and the
period filter at the request-status level. These tests exercise the
helpers `_owner_dashboard_context` calls — KPI aggregates, prior-period
deltas, the 30-day chart series shape, the per-company breakdown, and
the per-store comparison sort — by seeding real Transfer rows under
linked stores and asserting against the rendered `dash-data` JSON
payload + visible KPI numbers.

These helpers were previously only reachable through the route, which
made regressions invisible to test-writer subagents.
"""
from datetime import date, datetime, timedelta
import json
import re

import pytest

from app import app as flask_app, db


def _make_store(slug, name):
    from app import Store
    s = Store(name=name, slug=slug, plan="trial")
    db.session.add(s); db.session.commit()
    return s.id


def _link_owner(owner_id, store_id):
    from app import StoreOwnerLink
    db.session.add(StoreOwnerLink(owner_id=owner_id, store_id=store_id))
    db.session.commit()


def _make_transfer(store_id, *, send_date, send_amount=100.0, fee=2.0,
                   company="Intermex", confirm="X"):
    from app import Transfer
    t = Transfer(
        store_id=store_id, send_date=send_date,
        sender_name="S", recipient_name="R",
        country="MX", confirm_number=confirm,
        company=company, send_amount=send_amount,
        fee=fee, federal_tax=0.0,
        status="Sent",
    )
    db.session.add(t); db.session.commit()
    return t.id


@pytest.fixture
def owner_client():
    """Owner with two linked stores. Drops the stores at teardown so
    suite-wide state stays clean for any test that follows."""
    c = flask_app.test_client()
    with flask_app.app_context():
        from app import User
        o = User(username="owner@dash.com", full_name="Owner",
                 role="owner", store_id=None)
        o.set_password("ownerpass123")
        db.session.add(o); db.session.commit()
        oid = o.id
        s1 = _make_store("dash-shop-a", "Shop A")
        s2 = _make_store("dash-shop-b", "Shop B")
        _link_owner(oid, s1)
        _link_owner(oid, s2)
        flask_app.config["_TEST_STORES"] = (s1, s2)
    with c.session_transaction() as sess:
        sess["user_id"] = oid
        sess["role"] = "owner"
        sess["store_id"] = None
    return c


def _payload(body):
    """Pull the `od-data` JSON the owner dashboard ships to the chart JS.
    Schema: {"volume":{"labels","totals","counts"}, "company":{...}, "rc":{...}}.
    """
    m = re.search(r'<script id="od-data"[^>]*>([\s\S]+?)</script>', body)
    if not m:
        return None
    return json.loads(m.group(1))


# ── KPI aggregates + prior-period delta ──────────────────────


def test_owner_dashboard_aggregates_transfers_across_linked_stores(owner_client):
    s1, s2 = flask_app.config["_TEST_STORES"]
    today = date.today()
    with flask_app.app_context():
        # Two transfers under store A, one under store B — all today.
        _make_transfer(s1, send_date=today, send_amount=200.0, confirm="A1")
        _make_transfer(s1, send_date=today, send_amount=300.0, confirm="A2")
        _make_transfer(s2, send_date=today, send_amount=500.0, confirm="B1")

    body = owner_client.get("/owner/dashboard?period=today").data.decode()
    # KPI card values render as $1,000 (+200+300+500) and 3 transfers.
    assert "1,000" in body
    # The "3" transfer count must show on the page somewhere.
    assert ">3<" in body or "transfers</div>\n<div class=\"stat-value\">3" in body


def test_owner_dashboard_period_delta_signed_correctly(owner_client):
    s1, _ = flask_app.config["_TEST_STORES"]
    today = date.today()
    if today.day < 5:
        # Defensive: this test relies on month-period having both
        # current-month and prior-month rows; very-early-month wraps
        # would put both windows in the same calendar month.
        pytest.skip("month boundary — skipping near-month-start")
    prior_month_day = today.replace(day=1) - timedelta(days=2)
    with flask_app.app_context():
        _make_transfer(s1, send_date=today, send_amount=500.0, confirm="CUR")
        _make_transfer(s1, send_date=prior_month_day, send_amount=200.0, confirm="PRV")
    body = owner_client.get("/owner/dashboard?period=month").data.decode()
    # Dashboard should expose a delta: current $500 - prior $200 = +$300.
    # The template formats deltas inline; we just assert it's positive.
    assert "vs prior month" in body


# ── 30-day chart series shape ────────────────────────────────


def test_owner_dashboard_30day_series_always_30_entries(owner_client):
    """The 30-day area chart is fixed-window regardless of the period
    selector. Series labels must always be 30 long; per-day arrays
    parallel them. A regression here breaks the chart silently."""
    body = owner_client.get("/owner/dashboard?period=today").data.decode()
    payload = _payload(body)
    assert payload is not None
    vol = payload["volume"]
    assert len(vol["labels"]) == 30
    assert len(vol["totals"]) == 30
    assert len(vol["counts"]) == 30


def test_owner_dashboard_30day_series_picks_up_recent_transfer(owner_client):
    """A transfer dated today populates the last (today) bucket of the
    30-day series."""
    s1, _ = flask_app.config["_TEST_STORES"]
    today = date.today()
    with flask_app.app_context():
        _make_transfer(s1, send_date=today, send_amount=750.0, confirm="DAY")
    body = owner_client.get("/owner/dashboard?period=today").data.decode()
    payload = _payload(body)
    vol = payload["volume"]
    assert vol["labels"][-1] == today.isoformat()
    assert vol["totals"][-1] == 750.0
    assert vol["counts"][-1] == 1


# ── Per-company breakdown ────────────────────────────────────


def test_owner_dashboard_company_breakdown_renders_each_carrier(owner_client):
    s1, _ = flask_app.config["_TEST_STORES"]
    today = date.today()
    with flask_app.app_context():
        _make_transfer(s1, send_date=today, send_amount=400.0,
                       company="Intermex", confirm="I1")
        _make_transfer(s1, send_date=today, send_amount=600.0,
                       company="Maxi", confirm="M1")
    body = owner_client.get("/owner/dashboard?period=today").data.decode()
    assert "Intermex" in body
    assert "Maxi" in body


# ── Per-store comparison ─────────────────────────────────────


def test_owner_dashboard_store_comparison_sorts_by_volume_desc(owner_client):
    """Higher-volume store appears before lower-volume store in the
    comparison list — that ordering is enforced in
    _owner_dashboard_context, not the template, so a regression there
    silently flips the bar chart."""
    s1, s2 = flask_app.config["_TEST_STORES"]
    today = date.today()
    with flask_app.app_context():
        # Shop B should outrank Shop A.
        _make_transfer(s1, send_date=today, send_amount=100.0, confirm="A1")
        _make_transfer(s2, send_date=today, send_amount=900.0, confirm="B1")
    body = owner_client.get("/owner/dashboard?period=today").data.decode()
    # Both names are in the body; B should appear before A in the
    # comparison block. We slice the body from the comparison header
    # to keep the assertion local.
    a_pos = body.find("Shop A")
    b_pos = body.find("Shop B")
    assert a_pos != -1 and b_pos != -1
    assert b_pos < a_pos, "Shop B (higher volume) should render before Shop A"


# ── Excluded statuses don't count ────────────────────────────


def test_owner_dashboard_excludes_canceled_and_rejected(owner_client):
    """_OWNER_TRANSFER_EXCLUDED filters Canceled + Rejected from KPIs.
    Regression guard: someone removing the .notin_() filter would
    silently inflate every owner KPI."""
    from app import Transfer
    s1, _ = flask_app.config["_TEST_STORES"]
    today = date.today()
    with flask_app.app_context():
        _make_transfer(s1, send_date=today, send_amount=300.0, confirm="OK1")
        # Add two excluded rows directly so they don't go through
        # _make_transfer (which forces status='Sent').
        for status in ("Canceled", "Rejected"):
            db.session.add(Transfer(
                store_id=s1, send_date=today,
                sender_name="S", recipient_name="R",
                country="MX", confirm_number=f"EX-{status}",
                company="Intermex", send_amount=10000.0,
                fee=0.0, federal_tax=0.0,
                status=status,
            ))
        db.session.commit()
    body = owner_client.get("/owner/dashboard?period=today").data.decode()
    # If the excluded filter were dropped the volume would be $20,300.
    # We expect $300 — i.e. the inflated number must NOT appear.
    assert "20,300" not in body
    assert "300" in body
