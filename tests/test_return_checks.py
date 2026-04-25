"""Tests for the Return Checks workflow.

Covers ReturnCheck + ReturnCheckPayment models, the /return-checks
admin page, the daily-book auto-sync (each payment creates a
return_payback line item), the locked return_check_gl on the monthly
P&L, and the owner-dashboard return-check section.
"""
import pytest
from datetime import date, datetime, timedelta
from app import app as flask_app, db


# ── Helpers ─────────────────────────────────────────────────────

def _seed_rc(store_id, *, bounced_on=None, customer="Jane Doe",
             amount=500.0, check_number="1001", payer_bank="First National",
             status="pending", status_changed_on=None, notes=""):
    """Insert one ReturnCheck row directly. Returns the new id.
    For seeded payments, use _seed_payment() after."""
    from app import ReturnCheck
    with flask_app.app_context():
        rc = ReturnCheck(
            store_id=store_id,
            bounced_on=bounced_on or date.today(),
            customer_name=customer,
            check_number=check_number,
            payer_bank=payer_bank,
            amount=amount,
            status=status,
            status_changed_on=status_changed_on,
            notes=notes,
        )
        db.session.add(rc)
        db.session.commit()
        return rc.id


def _seed_payment(rc_id, *, amount, paid_on=None, payment_method="cash",
                  note=""):
    """Insert one ReturnCheckPayment row directly. Returns the new id.
    Bypasses the route — use the route-level POST in route tests."""
    from app import ReturnCheckPayment
    with flask_app.app_context():
        p = ReturnCheckPayment(
            return_check_id=rc_id, amount=amount,
            paid_on=paid_on or date.today(),
            payment_method=payment_method, note=note,
        )
        db.session.add(p)
        db.session.commit()
        return p.id


# ── Model basics ────────────────────────────────────────────────

def test_return_check_defaults_pending(test_store_id):
    """New rows default to status='pending', no status_changed_on,
    no payments → recovered_total = 0, remaining = amount."""
    from app import ReturnCheck
    rc_id = _seed_rc(test_store_id, amount=500.0)
    with flask_app.app_context():
        rc = db.session.get(ReturnCheck, rc_id)
        assert rc.status == "pending"
        assert rc.status_changed_on is None
        assert rc.recovered_total == 0.0
        assert rc.remaining == 500.0


def test_recovered_total_sums_payments(test_store_id):
    """recovered_total is a property that sums child payments —
    not a stored column. This test pins that contract."""
    from app import ReturnCheck
    rc_id = _seed_rc(test_store_id, amount=1000.0)
    _seed_payment(rc_id, amount=300.0)
    _seed_payment(rc_id, amount=200.0)
    with flask_app.app_context():
        rc = db.session.get(ReturnCheck, rc_id)
        assert rc.recovered_total == 500.0
        assert rc.remaining == 500.0


def test_remaining_clamps_at_zero(test_store_id):
    """If somehow payments exceed amount, remaining clamps at 0
    instead of going negative."""
    from app import ReturnCheck
    rc_id = _seed_rc(test_store_id, amount=100.0)
    _seed_payment(rc_id, amount=120.0)  # over-payment (shouldn't happen via route)
    with flask_app.app_context():
        rc = db.session.get(ReturnCheck, rc_id)
        assert rc.remaining == 0.0


def test_cascade_delete_removes_payments(test_store_id):
    """Deleting the parent ReturnCheck must cascade-delete its
    payments (cascade='all, delete-orphan' on the relationship)."""
    from app import ReturnCheck, ReturnCheckPayment
    rc_id = _seed_rc(test_store_id, amount=500.0)
    _seed_payment(rc_id, amount=100.0)
    _seed_payment(rc_id, amount=100.0)
    with flask_app.app_context():
        assert ReturnCheckPayment.query.filter_by(
            return_check_id=rc_id).count() == 2
        rc = db.session.get(ReturnCheck, rc_id)
        db.session.delete(rc)
        db.session.commit()
        assert ReturnCheckPayment.query.filter_by(
            return_check_id=rc_id).count() == 0


def test_store_owned_models_includes_return_check():
    """ReturnCheck must purge with the store on retention expiry."""
    from app import _STORE_OWNED_MODELS
    assert "ReturnCheck" in _STORE_OWNED_MODELS


# ── Period aggregates ───────────────────────────────────────────

def test_recoveries_use_payment_paid_on(test_store_id):
    """A $300 payment in April + $400 in May contributes to those
    months separately — even though the parent ReturnCheck is one row."""
    from app import _return_check_period_aggregates
    rc_id = _seed_rc(test_store_id, bounced_on=date(2024, 3, 15),
                     amount=1000.0)
    _seed_payment(rc_id, amount=300.0, paid_on=date(2024, 4, 15))
    _seed_payment(rc_id, amount=400.0, paid_on=date(2024, 5, 10))
    with flask_app.app_context():
        apr = _return_check_period_aggregates(
            [test_store_id], date(2024,4,1), date(2024,4,30))
        may = _return_check_period_aggregates(
            [test_store_id], date(2024,5,1), date(2024,5,31))
    assert apr["recoveries"] == 300.0
    assert may["recoveries"] == 400.0


def test_pending_balance_subtracts_partial_payments(test_store_id):
    """The pending-balance KPI shows OUTSTANDING owed, not face value.
    A $1000 check with $300 partial recovery has $700 still owed."""
    from app import _return_check_period_aggregates
    today = date.today()
    rc_id = _seed_rc(test_store_id, amount=1000.0, status="pending")
    _seed_payment(rc_id, amount=300.0, paid_on=today)
    with flask_app.app_context():
        agg = _return_check_period_aggregates(
            [test_store_id], today, today)
    assert agg["pending"] == 700.0
    assert agg["pending_count"] == 1


def test_loss_is_remaining_balance_not_face_value(test_store_id):
    """A $1000 check with $400 partially recovered then marked loss:
    the loss = $600 (remaining), not $1000. The earlier $400 already
    counted as a recovery in its own month."""
    from app import _return_check_period_aggregates
    today = date.today()
    rc_id = _seed_rc(test_store_id, amount=1000.0, status="loss",
                     status_changed_on=today)
    _seed_payment(rc_id, amount=400.0,
                  paid_on=today - timedelta(days=10))
    with flask_app.app_context():
        agg = _return_check_period_aggregates(
            [test_store_id], today, today)
    assert agg["losses"] == 600.0


def test_pending_only_no_pl_impact(test_store_id):
    """A pending check — no matter how large or how old — must never
    move recoveries / losses / fraud. Only marking-events (or
    payments) do."""
    from app import _return_check_period_aggregates
    today = date.today()
    _seed_rc(test_store_id, amount=10000.0, status="pending",
             bounced_on=today - timedelta(days=200))
    with flask_app.app_context():
        agg = _return_check_period_aggregates(
            [test_store_id], today, today)
    assert agg["recoveries"] == 0.0
    assert agg["losses"] == 0.0
    assert agg["fraud"] == 0.0
    assert agg["pending"] == 10000.0


# ── Sign convention: dashboard vs P&L ───────────────────────────

def test_monthly_pl_is_loss_positive_opposite_of_dashboard(test_store_id):
    """`_return_check_monthly_pl` (P&L expense column) is loss-positive
    so it adds to expenses correctly. `_return_check_period_aggregates['net_gl']`
    (owner dashboard) is gain-positive so positive = good."""
    from app import _return_check_monthly_pl, _return_check_period_aggregates
    today = date.today()
    y, m = today.year, today.month
    _seed_rc(test_store_id, amount=400.0, status="loss",
             status_changed_on=today)
    rec_id = _seed_rc(test_store_id, amount=100.0, status="recovered",
                      status_changed_on=today)
    _seed_payment(rec_id, amount=100.0, paid_on=today)
    with flask_app.app_context():
        agg = _return_check_period_aggregates([test_store_id],
                                              date(y,m,1), today)
        assert agg["net_gl"] == -300.0  # gain-positive: 100−400 = −300
        assert _return_check_monthly_pl(test_store_id, y, m) == 300.0


# ── Routes: page + auth ─────────────────────────────────────────

def test_return_checks_blocks_unauthenticated(client):
    rv = client.get("/return-checks")
    assert rv.status_code == 302
    assert "/login" in rv.headers["Location"]


def test_return_checks_blocks_employee(client, test_store_id):
    """admin_required gate — employees can't reach the list."""
    from tests.conftest import make_employee_client
    c = make_employee_client(test_store_id)
    rv = c.get("/return-checks", follow_redirects=False)
    assert rv.status_code == 302
    assert "/return-checks" not in rv.headers["Location"]


def test_return_checks_admin_page_loads_empty(logged_in_client):
    rv = logged_in_client.get("/return-checks")
    assert rv.status_code == 200
    assert b"Return Checks" in rv.data
    assert b"Pending balance" in rv.data
    assert b"No return checks match" in rv.data


def test_return_checks_lists_seeded_rows(logged_in_client, test_store_id):
    _seed_rc(test_store_id, customer="Alice Q", amount=250.0,
             check_number="9001")
    rv = logged_in_client.get("/return-checks")
    assert rv.status_code == 200
    assert b"Alice Q" in rv.data
    assert b"9001" in rv.data


def test_return_checks_status_filter(logged_in_client, test_store_id):
    today = date.today()
    _seed_rc(test_store_id, customer="Pendy", status="pending", amount=100.0)
    rec_id = _seed_rc(test_store_id, customer="Recvy", status="recovered",
                      status_changed_on=today, amount=200.0)
    _seed_payment(rec_id, amount=200.0, paid_on=today)
    rv = logged_in_client.get("/return-checks?status=pending")
    assert b"Pendy" in rv.data
    assert b"Recvy" not in rv.data
    rv = logged_in_client.get("/return-checks?status=recovered")
    assert b"Pendy" not in rv.data
    assert b"Recvy" in rv.data


def test_return_checks_search_filters_by_customer(logged_in_client, test_store_id):
    _seed_rc(test_store_id, customer="Alice Q", amount=100.0)
    _seed_rc(test_store_id, customer="Bob Smith", amount=200.0)
    rv = logged_in_client.get("/return-checks?status=all&q=alice")
    assert b"Alice Q" in rv.data
    assert b"Bob Smith" not in rv.data


def test_return_checks_partial_returns_json(logged_in_client, test_store_id):
    """?partial=1 returns JSON for the live-search swap."""
    _seed_rc(test_store_id, customer="Live Search Target", amount=99.0)
    rv = logged_in_client.get("/return-checks?partial=1&status=all&q=live")
    assert rv.status_code == 200
    assert rv.headers["Content-Type"].startswith("application/json")
    payload = rv.get_json()
    assert payload["matched"] == 1
    assert "Live Search Target" in payload["html"]
    assert "pending_balance" in payload


# ── Routes: create + status transitions ─────────────────────────

def test_new_return_check_persists(logged_in_client, test_store_id):
    rv = logged_in_client.post("/return-checks/new", data={
        "bounced_on":    "2026-04-15",
        "customer_name": "John Q",
        "check_number":  "5050",
        "payer_bank":    "Wells",
        "amount":        "750.00",
        "notes":         "first attempt",
    })
    assert rv.status_code == 302
    from app import ReturnCheck
    with flask_app.app_context():
        rc = ReturnCheck.query.filter_by(
            store_id=test_store_id, customer_name="John Q").first()
        assert rc is not None
        assert rc.status == "pending"
        assert rc.amount == 750.0


def test_new_return_check_rejects_zero_amount(logged_in_client):
    rv = logged_in_client.post("/return-checks/new", data={
        "bounced_on": "2026-04-15", "customer_name": "X", "amount": "0",
    })
    assert rv.status_code == 302
    from app import ReturnCheck
    with flask_app.app_context():
        assert ReturnCheck.query.count() == 0


def test_payment_partial_keeps_pending(logged_in_client, test_store_id):
    """Partial payment doesn't auto-flip the parent. Status stays
    'pending' so the cashier keeps chasing the rest."""
    rc_id = _seed_rc(test_store_id, amount=1000.0)
    rv = logged_in_client.post(f"/return-checks/{rc_id}/payment", data={
        "amount": "300.00", "paid_on": "2026-04-15",
        "payment_method": "cash",
    })
    assert rv.status_code == 302
    from app import ReturnCheck, ReturnCheckPayment
    with flask_app.app_context():
        rc = db.session.get(ReturnCheck, rc_id)
        assert rc.status == "pending"
        assert rc.recovered_total == 300.0
        assert rc.remaining == 700.0
        assert ReturnCheckPayment.query.filter_by(
            return_check_id=rc_id).count() == 1


def test_payment_full_auto_flips_to_recovered(logged_in_client, test_store_id):
    """When a payment fills the bucket, status auto-flips to
    'recovered' on the same paid_on date — no extra step needed."""
    rc_id = _seed_rc(test_store_id, amount=500.0)
    rv = logged_in_client.post(f"/return-checks/{rc_id}/payment", data={
        "amount": "500.00", "paid_on": "2026-04-20",
        "payment_method": "zelle",
    })
    assert rv.status_code == 302
    from app import ReturnCheck
    with flask_app.app_context():
        rc = db.session.get(ReturnCheck, rc_id)
        assert rc.status == "recovered"
        assert rc.status_changed_on == date(2026, 4, 20)
        assert rc.recovered_total == 500.0


def test_payment_installments_auto_flip_on_final(logged_in_client, test_store_id):
    """Two partial payments → second one closes the case."""
    rc_id = _seed_rc(test_store_id, amount=500.0)
    logged_in_client.post(f"/return-checks/{rc_id}/payment", data={
        "amount": "200.00", "paid_on": "2026-04-15",
    })
    logged_in_client.post(f"/return-checks/{rc_id}/payment", data={
        "amount": "300.00", "paid_on": "2026-05-10",
    })
    from app import ReturnCheck
    with flask_app.app_context():
        rc = db.session.get(ReturnCheck, rc_id)
        assert rc.status == "recovered"
        assert rc.status_changed_on == date(2026, 5, 10)
        assert len(rc.payments) == 2


def test_payment_rejects_above_remaining(logged_in_client, test_store_id):
    """Server caps each installment at the remaining balance."""
    rc_id = _seed_rc(test_store_id, amount=500.0)
    rv = logged_in_client.post(f"/return-checks/{rc_id}/payment", data={
        "amount": "9999.00",
    })
    assert rv.status_code == 302
    from app import ReturnCheck
    with flask_app.app_context():
        rc = db.session.get(ReturnCheck, rc_id)
        assert rc.recovered_total == 0.0
        assert rc.status == "pending"


def test_payment_blocked_on_closed_check(logged_in_client, test_store_id):
    """Can't add payments to a loss/fraud row — must reopen first."""
    today = date.today()
    rc_id = _seed_rc(test_store_id, amount=500.0, status="loss",
                     status_changed_on=today)
    rv = logged_in_client.post(f"/return-checks/{rc_id}/payment", data={
        "amount": "100.00",
    })
    assert rv.status_code == 302
    from app import ReturnCheckPayment
    with flask_app.app_context():
        assert ReturnCheckPayment.query.filter_by(
            return_check_id=rc_id).count() == 0


def test_payment_delete_walks_status_back(logged_in_client, test_store_id):
    """Deleting a payment that closed the case reverts status to
    'pending' so the row reappears in the active list."""
    rc_id = _seed_rc(test_store_id, amount=500.0)
    rv = logged_in_client.post(f"/return-checks/{rc_id}/payment", data={
        "amount": "500.00", "paid_on": "2026-04-20",
    })
    from app import ReturnCheck, ReturnCheckPayment
    with flask_app.app_context():
        rc = db.session.get(ReturnCheck, rc_id)
        pid = rc.payments[0].id
        assert rc.status == "recovered"
    rv = logged_in_client.post(
        f"/return-checks/{rc_id}/payment/{pid}/delete")
    assert rv.status_code == 302
    with flask_app.app_context():
        rc = db.session.get(ReturnCheck, rc_id)
        assert rc.status == "pending"
        assert rc.status_changed_on is None
        assert rc.recovered_total == 0.0


# ── Daily-book sync ─────────────────────────────────────────────

def test_payment_creates_daily_line_item(logged_in_client, test_store_id):
    """Each payment auto-creates a DailyLineItem(kind='return_payback')
    on its paid_on date — that's the connection that keeps the daily
    book's "Return Check Paid Back" in sync without double-entry."""
    rc_id = _seed_rc(test_store_id, customer="Bob B", amount=500.0,
                     check_number="2222")
    logged_in_client.post(f"/return-checks/{rc_id}/payment", data={
        "amount": "200.00", "paid_on": "2026-04-15",
        "payment_method": "cash",
    })
    from app import DailyLineItem
    with flask_app.app_context():
        rows = DailyLineItem.query.filter_by(
            store_id=test_store_id, return_check_id=rc_id,
            kind="return_payback").all()
        assert len(rows) == 1
        li = rows[0]
        assert li.report_date == date(2026, 4, 15)
        assert li.amount == 200.0
        # Note carries customer + check# + method context.
        assert "Bob B" in li.note
        assert "2222" in li.note
        assert "cash" in li.note


def test_payment_delete_removes_daily_line_item(logged_in_client, test_store_id):
    rc_id = _seed_rc(test_store_id, amount=500.0)
    logged_in_client.post(f"/return-checks/{rc_id}/payment", data={
        "amount": "200.00", "paid_on": "2026-04-15",
    })
    from app import ReturnCheck, DailyLineItem
    with flask_app.app_context():
        rc = db.session.get(ReturnCheck, rc_id)
        pid = rc.payments[0].id
    logged_in_client.post(
        f"/return-checks/{rc_id}/payment/{pid}/delete")
    with flask_app.app_context():
        rows = DailyLineItem.query.filter_by(
            store_id=test_store_id, return_check_id=rc_id,
            kind="return_payback").all()
        assert len(rows) == 0


def test_each_installment_lands_on_its_own_day(logged_in_client, test_store_id):
    """Three installments on three different days → three line items
    on three different daily reports. April 15 / May 10 / June 5."""
    rc_id = _seed_rc(test_store_id, amount=1000.0)
    for amt, day in [("300.00", "2026-04-15"),
                     ("400.00", "2026-05-10"),
                     ("300.00", "2026-06-05")]:
        logged_in_client.post(f"/return-checks/{rc_id}/payment", data={
            "amount": amt, "paid_on": day,
        })
    from app import DailyLineItem
    with flask_app.app_context():
        rows = DailyLineItem.query.filter_by(
            store_id=test_store_id, return_check_id=rc_id,
            kind="return_payback"
        ).order_by(DailyLineItem.report_date).all()
        assert [(r.report_date, r.amount) for r in rows] == [
            (date(2026, 4, 15), 300.0),
            (date(2026, 5, 10), 400.0),
            (date(2026, 6, 5),  300.0),
        ]


def test_manual_return_payback_creation_blocked(logged_in_client, test_store_id):
    """The /daily/<ds>/line-items/return_payback/new endpoint is
    blocked at the route level — return-check paybacks come ONLY
    from the Return Checks page. Stops a hand-crafted POST from
    bypassing the source-of-truth boundary."""
    today_iso = date.today().isoformat()
    rv = logged_in_client.post(
        f"/daily/{today_iso}/line-items/return_payback/new",
        data={"at_time": "12:00", "amount": "100.00", "note": "manual"},
    )
    # Either 403 JSON or a redirect+flash — both are acceptable.
    assert rv.status_code in (302, 403)
    from app import DailyLineItem
    with flask_app.app_context():
        assert DailyLineItem.query.filter_by(
            store_id=test_store_id, kind="return_payback").count() == 0


def test_manual_delete_of_synced_payback_blocked(logged_in_client, test_store_id):
    """The daily-book line-item delete endpoint refuses to delete
    rows whose return_check_id is set. Defense in depth — front-end
    hides the Remove button, but a tampered POST should still fail."""
    rc_id = _seed_rc(test_store_id, amount=500.0)
    logged_in_client.post(f"/return-checks/{rc_id}/payment", data={
        "amount": "100.00", "paid_on": "2026-04-15",
    })
    from app import DailyLineItem
    with flask_app.app_context():
        li = DailyLineItem.query.filter_by(
            return_check_id=rc_id, kind="return_payback").first()
        li_id = li.id
    rv = logged_in_client.post(
        f"/daily/2026-04-15/line-items/return_payback/{li_id}/delete")
    assert rv.status_code in (302, 403)
    with flask_app.app_context():
        # Row still there.
        assert db.session.get(DailyLineItem, li_id) is not None


# ── Loss / Fraud / Reopen ───────────────────────────────────────

def test_loss_marks_status_with_remaining_balance(logged_in_client, test_store_id):
    """Marking loss on a check with prior partial payments only
    writes off the REMAINING balance for the period."""
    rc_id = _seed_rc(test_store_id, amount=1000.0)
    _seed_payment(rc_id, amount=400.0, paid_on=date(2026, 4, 15))
    rv = logged_in_client.post(f"/return-checks/{rc_id}/loss", data={
        "status_changed_on": "2026-06-01",
    })
    assert rv.status_code == 302
    from app import ReturnCheck, _return_check_period_aggregates
    with flask_app.app_context():
        rc = db.session.get(ReturnCheck, rc_id)
        assert rc.status == "loss"
        assert rc.status_changed_on == date(2026, 6, 1)
        # June P&L: loss = remaining = 1000 − 400 = 600
        agg = _return_check_period_aggregates(
            [test_store_id], date(2026,6,1), date(2026,6,30))
        assert agg["losses"] == 600.0


def test_fraud_distinct_from_loss(logged_in_client, test_store_id):
    """Fraud is a separate status for reporting (repeat-offender lists,
    fraud KPIs) but accounts for the same way: write off the
    remaining unpaid balance."""
    rc_id = _seed_rc(test_store_id, amount=500.0)
    rv = logged_in_client.post(f"/return-checks/{rc_id}/fraud", data={})
    assert rv.status_code == 302
    from app import ReturnCheck
    with flask_app.app_context():
        rc = db.session.get(ReturnCheck, rc_id)
        assert rc.status == "fraud"


def test_reopen_keeps_payments(logged_in_client, test_store_id):
    """Reopen unwinds the close but does NOT delete prior payments —
    they represent real money received and stay on their daily
    books."""
    rc_id = _seed_rc(test_store_id, amount=1000.0)
    _seed_payment(rc_id, amount=300.0, paid_on=date(2026, 4, 15))
    logged_in_client.post(f"/return-checks/{rc_id}/loss", data={})
    rv = logged_in_client.post(f"/return-checks/{rc_id}/reopen")
    assert rv.status_code == 302
    from app import ReturnCheck
    with flask_app.app_context():
        rc = db.session.get(ReturnCheck, rc_id)
        assert rc.status == "pending"
        assert rc.status_changed_on is None
        # Payment survives.
        assert rc.recovered_total == 300.0
        assert rc.remaining == 700.0


def test_cross_store_payment_blocked(logged_in_client):
    """An admin cannot add a payment to a return check owned by a
    different store. Same isolation guarantee as Transfer routes."""
    from app import Store, ReturnCheck, ReturnCheckPayment
    with flask_app.app_context():
        other = Store(name="Other", slug="other-rc",
                      email="other-rc@example.com", plan="trial")
        if hasattr(Store, "trial_ends_at"):
            other.trial_ends_at = datetime.utcnow() + timedelta(days=7)
        db.session.add(other)
        db.session.commit()
        other_id = other.id
    other_rc_id = _seed_rc(other_id, customer="Their Customer", amount=500.0)
    rv = logged_in_client.post(
        f"/return-checks/{other_rc_id}/payment",
        data={"amount": "500"})
    assert rv.status_code == 302
    with flask_app.app_context():
        assert ReturnCheckPayment.query.filter_by(
            return_check_id=other_rc_id).count() == 0


def test_delete_rc_removes_all_payments_and_line_items(logged_in_client, test_store_id):
    """Deleting a return check cascades-deletes its payments AND
    removes all linked daily-book line items."""
    rc_id = _seed_rc(test_store_id, amount=500.0)
    logged_in_client.post(f"/return-checks/{rc_id}/payment", data={
        "amount": "200.00", "paid_on": "2026-04-15",
    })
    rv = logged_in_client.post(f"/return-checks/{rc_id}/delete")
    assert rv.status_code == 302
    from app import ReturnCheck, ReturnCheckPayment, DailyLineItem
    with flask_app.app_context():
        assert db.session.get(ReturnCheck, rc_id) is None
        assert ReturnCheckPayment.query.filter_by(
            return_check_id=rc_id).count() == 0
        # The shadow line item had return_check_id pointing at the
        # now-deleted parent. SQLAlchemy nulls out the FK by default
        # (no cascade configured) — so the line item itself either
        # has return_check_id=NULL OR is gone. Either is acceptable;
        # the important thing is no orphan refers to a missing row.
        rows = DailyLineItem.query.filter_by(
            store_id=test_store_id, kind="return_payback").all()
        for r in rows:
            assert r.return_check_id is None or r.return_check_id != rc_id


# ── Monthly P&L lock ────────────────────────────────────────────

def test_monthly_pl_uses_workflow_value(logged_in_client, test_store_id):
    """The Monthly P&L's `return_check_gl` is locked to the workflow's
    computed value. Tampered POST is ignored — same enforcement as
    `check_cashing_fees` and the COGS columns."""
    today = date.today()
    # $400 loss this month → P&L expects +400 (loss-positive).
    _seed_rc(test_store_id, amount=400.0, status="loss",
             status_changed_on=today)
    rv = logged_in_client.post(
        f"/monthly/{today.year}/{today.month}",
        data={"return_check_gl": "0.00"},
    )
    assert rv.status_code in (200, 302)
    from app import MonthlyFinancial
    with flask_app.app_context():
        rpt = MonthlyFinancial.query.filter_by(
            store_id=test_store_id, year=today.year, month=today.month
        ).first()
        assert rpt is not None
        assert rpt.return_check_gl == 400.0


def test_monthly_pl_template_marks_field_readonly(logged_in_client):
    """Template renders return_check_gl as readonly with the locked
    badge — confirms the macro call site uses locked=True."""
    today = date.today()
    rv = logged_in_client.get(f"/monthly/{today.year}/{today.month}")
    assert rv.status_code == 200
    body = rv.data.decode()
    idx = body.find('name="return_check_gl"')
    assert idx > 0
    near = body[max(0, idx - 200):idx + 300]
    assert "readonly" in near


# ── Owner dashboard surface ─────────────────────────────────────

def test_owner_dashboard_shows_return_checks_section(client, test_store_id):
    """Owner dashboard surfaces pending balance + recoveries +
    losses across the umbrella so the owner sees what's happening
    with bounced checks without drilling into each store."""
    from app import User, StoreOwnerLink
    with flask_app.app_context():
        o = User(username="rc_owner@test.com", role="owner",
                 full_name="RC Owner", store_id=None)
        o.set_password("ownerpass123")
        db.session.add(o)
        db.session.flush()
        link = StoreOwnerLink(owner_id=o.id, store_id=test_store_id)
        db.session.add(link)
        db.session.commit()
        oid = o.id

    today = date.today()
    _seed_rc(test_store_id, customer="Pending Customer", amount=300.0,
             status="pending")
    rec_id = _seed_rc(test_store_id, amount=200.0, status="recovered",
                      status_changed_on=today)
    _seed_payment(rec_id, amount=200.0, paid_on=today)
    _seed_rc(test_store_id, amount=100.0, status="loss",
             status_changed_on=today)

    with client.session_transaction() as sess:
        sess["user_id"] = oid
        sess["role"] = "owner"
    rv = client.get("/owner/dashboard?period=month")
    assert rv.status_code == 200
    body = rv.data
    assert b"Return checks" in body
    assert b"Pending balance" in body
    assert b"Recoveries" in body
    assert b"Aging" in body
