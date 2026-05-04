"""Tests for the platform anomaly detector surfaced on the superadmin
overview tab.

Covers the two v1 rules:
  - Quiet stores: previously-active stores that have gone silent
  - Big over/short: daily books with |over_short| over the threshold
"""
from datetime import date, timedelta


def _seed_store(name="anomaly-store", plan="pro"):
    from app import app as flask_app, db, Store, User
    with flask_app.app_context():
        s = Store(name=name, slug=name.replace(" ", "-"),
                  email=f"{name}@x.com", plan=plan, is_active=True,
                  billing_cycle="monthly")
        db.session.add(s); db.session.commit()
        return s.id


def _seed_transfers(store_id, *, days_ago_list, amount=100.0):
    from app import app as flask_app, db, Transfer
    with flask_app.app_context():
        today = date.today()
        for n in days_ago_list:
            t = Transfer(
                store_id=store_id, send_date=today - timedelta(days=n),
                sender_name="S", recipient_name="R", country="MX",
                confirm_number=f"X{n}", company="Intermex",
                send_amount=amount, fee=2.0, federal_tax=1.0,
                status="Sent",
            )
            db.session.add(t)
        db.session.commit()


def _seed_daily_report(store_id, *, days_ago, over_short):
    from app import app as flask_app, db, DailyReport
    with flask_app.app_context():
        today = date.today()
        r = DailyReport(store_id=store_id,
                        report_date=today - timedelta(days=days_ago),
                        over_short=over_short)
        db.session.add(r); db.session.commit()


def test_quiet_store_with_history_is_flagged():
    sid = _seed_store("quiet-once-active")
    # 5 transfers across days 5..9 — establishes "active" baseline.
    # Then nothing in days 0..4 — silent for 5 days.
    _seed_transfers(sid, days_ago_list=[5, 6, 7, 8, 9])
    from app import app as flask_app, _compute_platform_anomalies
    with flask_app.test_request_context():
        results = _compute_platform_anomalies()
    kinds = {(a["kind"], a["store"].id) for a in results}
    assert ("quiet_store", sid) in kinds


def test_recently_active_store_is_not_flagged():
    sid = _seed_store("still-busy")
    # Transfers including today — store is still active.
    _seed_transfers(sid, days_ago_list=[0, 1, 2, 3, 5])
    from app import app as flask_app, _compute_platform_anomalies
    with flask_app.test_request_context():
        results = _compute_platform_anomalies()
    kinds = {(a["kind"], a["store"].id) for a in results}
    assert ("quiet_store", sid) not in kinds


def test_tiny_store_below_min_threshold_not_flagged():
    """A store with only 2-3 lifetime transfers shouldn't trip the
    quiet-store rule — it never had a meaningful baseline."""
    sid = _seed_store("tiny-store")
    _seed_transfers(sid, days_ago_list=[10, 11])  # 2 transfers, then silence
    from app import app as flask_app, _compute_platform_anomalies
    with flask_app.test_request_context():
        results = _compute_platform_anomalies()
    kinds = {(a["kind"], a["store"].id) for a in results}
    assert ("quiet_store", sid) not in kinds


def test_big_over_short_high_severity():
    sid = _seed_store("over-short-store")
    _seed_daily_report(sid, days_ago=2, over_short=-275.0)
    from app import app as flask_app, _compute_platform_anomalies
    with flask_app.test_request_context():
        results = _compute_platform_anomalies()
    matches = [a for a in results
               if a["kind"] == "big_over_short" and a["store"].id == sid]
    assert len(matches) == 1
    assert matches[0]["severity"] == "high"
    assert "275" in matches[0]["description"]
    assert "short" in matches[0]["description"]


def test_small_over_short_below_threshold_not_flagged():
    sid = _seed_store("small-os-store")
    _seed_daily_report(sid, days_ago=1, over_short=-50.0)
    from app import app as flask_app, _compute_platform_anomalies
    with flask_app.test_request_context():
        results = _compute_platform_anomalies()
    matches = [a for a in results
               if a["kind"] == "big_over_short" and a["store"].id == sid]
    assert matches == []


def test_inactive_store_not_flagged_for_anomalies():
    """A store that's been deactivated shouldn't trigger anomaly
    alerts — superadmin can't take action on it anyway."""
    sid = _seed_store("disabled-store", plan="inactive")
    from app import app as flask_app, db, Store
    with flask_app.app_context():
        s = db.session.get(Store, sid)
        s.is_active = False
        db.session.commit()
    _seed_daily_report(sid, days_ago=2, over_short=-500.0)
    from app import _compute_platform_anomalies
    with flask_app.test_request_context():
        results = _compute_platform_anomalies()
    matches = [a for a in results if a["store"].id == sid]
    assert matches == []


def test_anomalies_sorted_high_severity_first():
    sid_high = _seed_store("h-severity")
    sid_med  = _seed_store("m-severity")
    _seed_daily_report(sid_med,  days_ago=1, over_short=-150.0)  # medium
    _seed_daily_report(sid_high, days_ago=1, over_short=-500.0)  # high
    from app import app as flask_app, _compute_platform_anomalies
    with flask_app.test_request_context():
        results = _compute_platform_anomalies()
    severities = [a["severity"] for a in results
                  if a["store"].id in (sid_high, sid_med)]
    # First match must be high.
    assert severities[0] == "high"
