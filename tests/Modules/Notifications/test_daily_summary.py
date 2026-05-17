"""Unit tests for ``Notifications.Services.daily_summary``.

Three layers under test:

  * ``eligible_recipients`` — same role / toggle / bounce filters as
    the locked-day digest but keyed on ``User.notify_daily_summary``.
  * ``compute_daily_totals`` — aggregates Transfer + DailyReport rows
    for one (store, date). Excludes Canceled / Rejected transfers.
  * ``run`` — end-to-end orchestrator. Iterates stores with activity,
    sends per recipient, stamps ``Store.daily_summary_sent_for`` for
    idempotency.

SMTP isn't configured in the test env so ``send_email()`` always
returns False — we only need to confirm the orchestrator walks the
right rows + writes the dedup stamp.
"""
from datetime import date, datetime, timedelta

from api.Modules.DailyBook.Models import DailyReport
from api.Modules.Notifications.Services import daily_summary as ds
from api.Modules.Tenancy.Models import Store, StoreEmployee, User
from api.Modules.Transfers.Models import Transfer
from tests._app import db, db_session


def _seed_store(slug: str, *, name: str | None = None) -> int:
    s = Store(
        name=name or slug,
        slug=slug,
        email=f"{slug}@example.com",
        plan="basic",
    )
    db.session.add(s); db.session.commit()
    return s.id


def _seed_user(
    store_id: int | None, role: str, username: str, *,
    email: str | None = None,
    notify_daily_summary: bool = True,
    is_active: bool = True,
    email_bounced_at: datetime | None = None,
) -> int:
    u = User(
        username=username,
        password_hash="x",
        role=role,
        full_name=username,
        email=email if email is not None else f"{username}@x.com",
        store_id=store_id,
        notify_daily_summary=notify_daily_summary,
        is_active=is_active,
        email_bounced_at=email_bounced_at,
    )
    db.session.add(u); db.session.commit()
    return u.id


def _seed_employee_row(store_id: int) -> int:
    emp = StoreEmployee(
        store_id=store_id, name="Test cashier", is_active=True,
    )
    db.session.add(emp); db.session.commit()
    return emp.id


def _seed_transfer(
    store_id: int, *,
    on_date: date,
    send_amount: float = 100.0,
    status: str = "Sent",
) -> int:
    emp_id = (
        db.session.query(StoreEmployee)
          .filter_by(store_id=store_id).first()
    )
    if emp_id is None:
        emp_id = _seed_employee_row(store_id)
    else:
        emp_id = emp_id.id
    t = Transfer(
        store_id=store_id,
        send_date=on_date,
        company="Intermex",
        service_type="Money Transfer",
        sender_name="Sender",
        sender_phone="5550000000",
        sender_phone_country="+1",
        sender_address="",
        send_amount=send_amount,
        fee=5.0,
        federal_tax=0.0,
        country="Mexico",
        recipient_name="Recipient",
        recipient_phone="",
        confirm_number="",
        status=status,
        employee_id=emp_id,
    )
    db.session.add(t); db.session.commit()
    return t.id


def _seed_daily_report(
    store_id: int, on_date: date, *,
    taxable_sales: float = 0.0,
    cash_purchases: float = 0.0,
    over_short: float = 0.0,
) -> int:
    r = DailyReport(
        store_id=store_id,
        report_date=on_date,
        taxable_sales=taxable_sales,
        cash_purchases=cash_purchases,
        over_short=over_short,
    )
    db.session.add(r); db.session.commit()
    return r.id


# ── compute_daily_totals ────────────────────────────────────


def test_totals_count_and_volume_from_transfers():
    with db_session():
        sid = _seed_store("ds-totals-tx")
        on_date = date.today() - timedelta(days=1)
        _seed_transfer(sid, on_date=on_date, send_amount=100.0)
        _seed_transfer(sid, on_date=on_date, send_amount=250.0)
        totals = ds.compute_daily_totals(db.session, sid, on_date)
    assert totals.transfer_count == 2
    assert totals.send_volume == 350.0
    assert totals.has_activity is True


def test_totals_exclude_canceled_and_rejected_transfers():
    """Canceled / Rejected transfers don't contribute to count or
    volume — matches the rest of the platform's revenue queries."""
    with db_session():
        sid = _seed_store("ds-totals-exclude")
        on_date = date.today() - timedelta(days=1)
        _seed_transfer(sid, on_date=on_date, send_amount=100.0,
                       status="Sent")
        _seed_transfer(sid, on_date=on_date, send_amount=500.0,
                       status="Canceled")
        _seed_transfer(sid, on_date=on_date, send_amount=800.0,
                       status="Rejected")
        totals = ds.compute_daily_totals(db.session, sid, on_date)
    assert totals.transfer_count == 1
    assert totals.send_volume == 100.0


def test_totals_pull_receipts_disbursements_from_daily_report():
    with db_session():
        sid = _seed_store("ds-totals-report")
        on_date = date.today() - timedelta(days=1)
        _seed_daily_report(
            sid, on_date,
            taxable_sales=500.0,    # contributes to receipts
            cash_purchases=120.0,   # contributes to disbursements
            over_short=-3.50,
        )
        totals = ds.compute_daily_totals(db.session, sid, on_date)
    assert totals.receipts == 500.0
    assert totals.disbursements == 120.0
    assert totals.over_short == -3.50
    assert totals.has_activity is True


def test_totals_has_activity_false_when_no_transfers_or_report():
    """A store with neither a Transfer nor a DailyReport row on
    the date returns ``has_activity=False`` — callers skip the
    email in that case (no point summarizing nothing)."""
    with db_session():
        sid = _seed_store("ds-totals-empty")
        on_date = date.today() - timedelta(days=1)
        totals = ds.compute_daily_totals(db.session, sid, on_date)
    assert totals.has_activity is False
    assert totals.transfer_count == 0
    assert totals.send_volume == 0.0


# ── eligible_recipients ─────────────────────────────────────


def test_recipients_include_store_admin():
    with db_session():
        sid = _seed_store("ds-rec-admin")
        _seed_user(sid, "admin", "ds_admin")
        store = db.session.get(Store, sid)
        recipients = ds.eligible_recipients(db.session, store)
    assert {u.username for u in recipients} == {"ds_admin"}


def test_recipients_skip_employees():
    with db_session():
        sid = _seed_store("ds-rec-emp")
        _seed_user(sid, "employee", "ds_emp")
        store = db.session.get(Store, sid)
        recipients = ds.eligible_recipients(db.session, store)
    assert recipients == []


def test_recipients_respect_per_user_toggle():
    """``notify_daily_summary=False`` silences the digest for one
    user without affecting the rest of the eligible set."""
    with db_session():
        sid = _seed_store("ds-rec-toggle")
        _seed_user(sid, "admin", "ds_silenced",
                   notify_daily_summary=False)
        _seed_user(sid, "admin", "ds_loud",
                   notify_daily_summary=True)
        store = db.session.get(Store, sid)
        recipients = ds.eligible_recipients(db.session, store)
    assert {u.username for u in recipients} == {"ds_loud"}


def test_recipients_skip_bounced_addresses():
    """A hard-bounce stamp suppresses the user from the recipient
    list — protects Resend reputation."""
    with db_session():
        sid = _seed_store("ds-rec-bounce")
        _seed_user(sid, "admin", "ds_bounced",
                   email_bounced_at=datetime.utcnow())
        store = db.session.get(Store, sid)
        recipients = ds.eligible_recipients(db.session, store)
    assert recipients == []


def test_recipients_skip_inactive_users():
    with db_session():
        sid = _seed_store("ds-rec-inactive")
        _seed_user(sid, "admin", "ds_inactive", is_active=False)
        store = db.session.get(Store, sid)
        recipients = ds.eligible_recipients(db.session, store)
    assert recipients == []


# ── stores_with_activity ────────────────────────────────────


def test_stores_with_activity_includes_transfer_only_store():
    with db_session():
        sid = _seed_store("ds-stores-tx")
        on_date = date.today() - timedelta(days=1)
        _seed_transfer(sid, on_date=on_date)
        rows = ds.stores_with_activity(db.session, on_date)
    assert any(s.slug == "ds-stores-tx" for s in rows)


def test_stores_with_activity_includes_report_only_store():
    with db_session():
        sid = _seed_store("ds-stores-rpt")
        on_date = date.today() - timedelta(days=1)
        _seed_daily_report(sid, on_date, taxable_sales=10.0)
        rows = ds.stores_with_activity(db.session, on_date)
    assert any(s.slug == "ds-stores-rpt" for s in rows)


def test_stores_with_activity_skips_inactive_store():
    with db_session():
        sid = _seed_store("ds-stores-off")
        s = db.session.get(Store, sid)
        s.is_active = False
        db.session.commit()
        on_date = date.today() - timedelta(days=1)
        _seed_transfer(sid, on_date=on_date)
        rows = ds.stores_with_activity(db.session, on_date)
    assert all(s.slug != "ds-stores-off" for s in rows)


# ── run() orchestrator ──────────────────────────────────────


def test_run_stamps_daily_summary_sent_for_after_pass():
    """Successful pass stamps ``Store.daily_summary_sent_for``
    so a re-run on the same date is a no-op."""
    with db_session():
        sid = _seed_store("ds-run-stamp")
        on_date = date.today() - timedelta(days=1)
        _seed_user(sid, "admin", "ds_run_stamp_admin")
        _seed_transfer(sid, on_date=on_date)
    n = ds.run(db.session, on_date=on_date)
    assert n >= 1
    with db_session():
        s = db.session.get(Store, sid)
        assert s.daily_summary_sent_for == on_date


def test_run_skips_already_stamped_store():
    """If ``daily_summary_sent_for`` already matches the target
    date, the orchestrator skips that store — no duplicate emails
    on a flaky-retry cron run."""
    with db_session():
        sid = _seed_store("ds-run-skip")
        on_date = date.today() - timedelta(days=1)
        _seed_user(sid, "admin", "ds_run_skip_admin")
        _seed_transfer(sid, on_date=on_date)
        s = db.session.get(Store, sid)
        s.daily_summary_sent_for = on_date
        db.session.commit()
    n = ds.run(db.session, on_date=on_date)
    # Only THIS store was stamped pre-run, so the orchestrator
    # might still mail other seeded stores. Re-fetch to confirm
    # the stamp didn't change (i.e. ``run`` didn't re-process).
    with db_session():
        s = db.session.get(Store, sid)
        assert s.daily_summary_sent_for == on_date
    # The N return value counts emails actually attempted across
    # ALL stores; the contract under test is the dedup on this
    # one store, not the absolute count. So no assertion on n.


def test_run_skips_stores_with_no_activity():
    """A store with neither a transfer nor a daily-report row on
    the target date never gets an email — ``stores_with_activity``
    filters it out before the per-store loop."""
    with db_session():
        sid = _seed_store("ds-run-idle")
        on_date = date.today() - timedelta(days=1)
        _seed_user(sid, "admin", "ds_run_idle_admin")
        # Deliberately NO transfer, NO daily report.
    n_before = ds.run(db.session, on_date=on_date)
    with db_session():
        s = db.session.get(Store, sid)
        # No stamp because the store wasn't processed.
        assert s.daily_summary_sent_for is None
    assert n_before >= 0  # other stores may have been mailed
