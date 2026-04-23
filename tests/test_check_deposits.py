"""Check Deposits line-item widget mirrors the Outside Cash & Drops
widget: each day can have multiple CheckDeposit rows that sum into
DailyReport.checks_deposit. The daily-book field is derived, so a
stale form submit can't override the truth. Tests also guard the
JSON-dual-mode AJAX add/delete flow.
"""
import json
from datetime import date, time


def _today_ds():
    return date.today().isoformat()


def test_daily_report_renders_check_deposits_widget(logged_in_client, test_store_id):
    """Template exposes the disclosure widget, the POST URLs, and any
    existing rows. Guards against a refactor accidentally dropping the
    widget or re-introducing the plain editable field."""
    from app import CheckDeposit, db
    ds = _today_ds()
    with logged_in_client.application.app_context():
        db.session.add(CheckDeposit(
            store_id=test_store_id, report_date=date.today(),
            deposit_time=time(9, 30), amount=250.0, note="Morning run",
        ))
        db.session.add(CheckDeposit(
            store_id=test_store_id, report_date=date.today(),
            deposit_time=time(15, 0), amount=500.0, note="Afternoon BoA",
        ))
        db.session.commit()

    resp = logged_in_client.get(f"/daily/{ds}")
    assert resp.status_code == 200
    body = resp.data.decode()
    # Disclosure wiring
    assert 'id="checksDetails"' in body
    assert f"/daily/{ds}/check-deposits/new" in body
    # Existing rows rendered
    assert "Morning run" in body
    assert "Afternoon BoA" in body
    assert "$250.00" in body and "$500.00" in body
    # Derived total + count badge
    assert "2 deposits" in body
    # Field is readonly (derived)
    assert 'id="checks_deposit_field"' in body
    assert "readonly" in body.split('id="checks_deposit_field"')[1].split(">")[0]


def test_checks_deposit_is_derived_on_daily_save(logged_in_client, test_store_id):
    """POSTing a spoofed checks_deposit value must NOT overwrite the
    derived total from CheckDeposit rows."""
    from app import CheckDeposit, DailyReport, db
    ds = _today_ds()
    with logged_in_client.application.app_context():
        db.session.add(CheckDeposit(
            store_id=test_store_id, report_date=date.today(),
            deposit_time=time(9, 0), amount=300.0,
        ))
        db.session.add(CheckDeposit(
            store_id=test_store_id, report_date=date.today(),
            deposit_time=time(16, 0), amount=200.0,
        ))
        db.session.commit()

    # Attempt to override the derived field via form post
    resp = logged_in_client.post(f"/daily/{ds}",
                                 data={"checks_deposit": "999999"})
    assert resp.status_code in (200, 302)

    with logged_in_client.application.app_context():
        rpt = DailyReport.query.filter_by(
            store_id=test_store_id, report_date=date.today()
        ).first()
        assert rpt is not None
        assert rpt.checks_deposit == 500.0, \
            f"expected derived total 500.0, got {rpt.checks_deposit}"


def test_ajax_add_and_delete_recomputes_total(logged_in_client, test_store_id):
    """Mirror of the Drops AJAX contract: add + delete return fresh
    {ok, total, check_deposits} payloads and keep DailyReport.checks_deposit
    in sync."""
    from app import CheckDeposit, DailyReport, db
    ds = _today_ds()

    # Add
    r1 = logged_in_client.post(
        f"/daily/{ds}/check-deposits/new",
        data={"deposit_time": "09:15", "amount": "250.50", "note": "First"},
        headers={"Accept": "application/json"},
    )
    assert r1.status_code == 200
    p1 = json.loads(r1.data)
    assert p1["ok"] is True
    assert p1["total"] == 250.5
    assert len(p1["check_deposits"]) == 1
    first_id = p1["check_deposits"][0]["id"]

    # Add a second
    r2 = logged_in_client.post(
        f"/daily/{ds}/check-deposits/new",
        data={"deposit_time": "14:45", "amount": "100.00", "note": "Second"},
        headers={"Accept": "application/json"},
    )
    p2 = json.loads(r2.data)
    assert p2["total"] == 350.5
    assert len(p2["check_deposits"]) == 2

    # DailyReport.checks_deposit should have been updated server-side
    with logged_in_client.application.app_context():
        rpt = DailyReport.query.filter_by(
            store_id=test_store_id, report_date=date.today()
        ).first()
        assert rpt.checks_deposit == 350.5

    # Delete the first row
    r3 = logged_in_client.post(
        f"/daily/{ds}/check-deposits/{first_id}/delete",
        headers={"Accept": "application/json"},
    )
    p3 = json.loads(r3.data)
    assert p3["ok"] is True
    assert p3["total"] == 100.0

    with logged_in_client.application.app_context():
        rpt = DailyReport.query.filter_by(
            store_id=test_store_id, report_date=date.today()
        ).first()
        assert rpt.checks_deposit == 100.0


def test_ajax_rejects_invalid_time_and_amount(logged_in_client):
    """Input validation matches the Drops widget — no row persists when
    inputs are invalid."""
    from app import CheckDeposit
    ds = _today_ds()

    # Bad time
    r = logged_in_client.post(
        f"/daily/{ds}/check-deposits/new",
        data={"deposit_time": "not-a-time", "amount": "50"},
        headers={"Accept": "application/json"},
    )
    assert r.status_code == 400
    assert json.loads(r.data)["ok"] is False

    # Non-positive amount
    r = logged_in_client.post(
        f"/daily/{ds}/check-deposits/new",
        data={"deposit_time": "09:00", "amount": "0"},
        headers={"Accept": "application/json"},
    )
    assert r.status_code == 400

    with logged_in_client.application.app_context():
        assert CheckDeposit.query.count() == 0


def test_check_deposits_isolated_per_store(logged_in_client, test_store_id):
    """A CheckDeposit owned by a different store must not leak into
    this store's daily report or AJAX payload."""
    from app import Store, CheckDeposit, db
    ds = _today_ds()
    with logged_in_client.application.app_context():
        other = Store(name="Other Store", slug="other-store", plan="trial")
        db.session.add(other); db.session.flush()
        db.session.add(CheckDeposit(
            store_id=other.id, report_date=date.today(),
            deposit_time=time(12, 0), amount=9999.0, note="NOT MINE",
        ))
        db.session.add(CheckDeposit(
            store_id=test_store_id, report_date=date.today(),
            deposit_time=time(10, 0), amount=75.0, note="mine",
        ))
        db.session.commit()

    resp = logged_in_client.get(f"/daily/{ds}")
    body = resp.data.decode()
    assert "NOT MINE" not in body
    assert "mine" in body
    # Widget total reflects this store only
    assert "75.00" in body
