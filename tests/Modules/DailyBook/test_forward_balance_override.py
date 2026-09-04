"""Overriding the auto-carried forward balance (M-1).

The forward balance normally carries itself: today's opening cash is
yesterday's drops + safe, recomputed on every read so fixing
yesterday moves today before today is even re-saved. That
self-healing chain is worth keeping — but it has no answer for a
store migrating mid-month, cash moved outside the book, or a locked
prior day that is known wrong.

An override PINS one day. The rules that make it safe:

* the carry keeps being computed and returned, so a chain that has
  diverged is VISIBLE rather than silently ignored;
* a bare `forward_balance` in the payload is still ignored — the
  stale-form guard stays, and only the explicit
  `forward_balance_override` key pins anything;
* an override does NOT cascade: tomorrow carries from today's drops
  + safe, never from today's forward balance;
* it persists until explicitly released, or it isn't an override.
"""
from datetime import date, timedelta

import pytest

from api.Modules.DailyBook.Services.reports import (
    summarize_report, update_daily_report,
)
from tests._app import db, db_session

D1 = date(2026, 3, 2)
D2 = date(2026, 3, 3)
D3 = date(2026, 3, 4)


def _save(store_id, day, **fields):
    with db_session():
        update_daily_report(
            db.session, store_id=store_id, report_date=day,
            fields=fields, notes="",
        )
        db.session.commit()


def _read(store_id, day):
    with db_session():
        return summarize_report(db.session, store_id, day)


@pytest.fixture()
def chained(test_store_id):
    """Two logged days. The carry is drops + safe; `outside_cash_drops`
    is line-item-derived (it rolls up from the DailyDrop table, not
    this payload), so these fixtures move `safe_balance` — the
    operator-editable half — and the carry equals it."""
    _save(test_store_id, D1, safe_balance=350.0)
    _save(test_store_id, D2, taxable_sales=500.0)
    return test_store_id


# ── The carry still works ───────────────────────────────────


def test_the_carry_is_unchanged_without_an_override(chained):
    d2 = _read(chained, D2)
    assert d2.forward_balance == pytest.approx(350.0)
    assert d2.forward_balance_carry == pytest.approx(350.0)
    assert d2.forward_balance_overridden is False
    assert d2.forward_balance_auto is True


def test_a_bare_forward_balance_is_still_ignored(chained):
    """The stale-form guard stays: only the explicit override key
    pins anything."""
    _save(chained, D2, forward_balance=9999.0)
    d2 = _read(chained, D2)
    assert d2.forward_balance == pytest.approx(350.0)
    assert d2.forward_balance_overridden is False


# ── Overriding ──────────────────────────────────────────────


def test_an_override_pins_the_opening_balance(chained):
    _save(chained, D2, forward_balance_override=400.0)
    d2 = _read(chained, D2)
    assert d2.forward_balance == pytest.approx(400.0)
    assert d2.forward_balance_overridden is True
    # The field goes back into the operator's hands, so the editor
    # must stop rendering it read-only.
    assert d2.forward_balance_auto is False


def test_the_carry_is_still_reported_beside_the_override(chained):
    """The whole reason this is safe: the number the chain WOULD
    produce stays visible next to the pinned one."""
    _save(chained, D2, forward_balance_override=400.0)
    d2 = _read(chained, D2)
    assert d2.forward_balance == pytest.approx(400.0)
    assert d2.forward_balance_carry == pytest.approx(350.0)


def test_fixing_yesterday_moves_the_carry_not_the_pin(chained):
    """The trap this design exists to avoid: someone corrects
    yesterday and cannot see why today did not move. The carry
    updates, the pin does not, and the two are both on screen."""
    _save(chained, D2, forward_balance_override=400.0)
    # Correct yesterday's safe count: 350 → 700.
    _save(chained, D1, safe_balance=700.0)

    d2 = _read(chained, D2)
    assert d2.forward_balance == pytest.approx(400.0), (
        "the pin must survive an edit to the prior day"
    )
    assert d2.forward_balance_carry == pytest.approx(700.0), (
        "the carry must track the prior day so the divergence shows"
    )


def test_the_override_reaches_the_stored_totals(chained):
    """Downstream readers — owner dashboards, tax export, the daily
    summary email — read the stored column, not the summary. The pin
    has to land there too or they disagree with the screen."""
    from api.Modules.DailyBook.Models import DailyReport

    _save(chained, D2, forward_balance_override=400.0)
    with db_session():
        row = (
            db.session.query(DailyReport)
            .filter_by(store_id=chained, report_date=D2).one()
        )
        assert row.forward_balance == pytest.approx(400.0)
        # total_receipts is computed off the stored column.
        assert row.total_receipts == pytest.approx(900.0)


# ── Releasing ───────────────────────────────────────────────


def test_sending_null_releases_the_day_back_to_the_carry(chained):
    _save(chained, D2, forward_balance_override=400.0)
    assert _read(chained, D2).forward_balance == pytest.approx(400.0)

    _save(chained, D2, forward_balance_override=None)
    d2 = _read(chained, D2)
    assert d2.forward_balance == pytest.approx(350.0)
    assert d2.forward_balance_overridden is False
    assert d2.forward_balance_auto is True


def test_an_unrelated_save_does_not_release_the_pin(chained):
    """It persists until explicitly released — otherwise editing any
    other field would quietly un-pin the day."""
    _save(chained, D2, forward_balance_override=400.0)
    _save(chained, D2, taxable_sales=777.0)
    d2 = _read(chained, D2)
    assert d2.forward_balance == pytest.approx(400.0)
    assert d2.forward_balance_overridden is True


# ── No cascade ──────────────────────────────────────────────


def test_an_override_does_not_cascade_to_the_next_day(chained):
    """Tomorrow opens with what today actually CLOSED with — drops +
    safe — never with today's opening balance. So a pin stays a
    one-day correction instead of rewriting the rest of the month."""
    _save(chained, D2, safe_balance=30.0)
    _save(chained, D3, taxable_sales=1.0)
    assert _read(chained, D3).forward_balance == pytest.approx(30.0)

    _save(chained, D2, forward_balance_override=5000.0)
    d3 = _read(chained, D3)
    assert d3.forward_balance == pytest.approx(30.0), (
        "an override must not move the following day's carry"
    )
    assert d3.forward_balance_overridden is False


# ── Locking still wins ──────────────────────────────────────


def test_a_locked_day_refuses_an_override(chained):
    """The lock is the kill-switch; an override is still an edit."""
    from api.Modules.DailyBook.Services.reports import (
        DailyReportLockedError, lock_report,
    )

    with db_session():
        lock_report(db.session, chained, D2)
        db.session.commit()

    with pytest.raises(DailyReportLockedError):
        _save(chained, D2, forward_balance_override=400.0)
