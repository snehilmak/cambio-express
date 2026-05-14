"""Unit tests for Reports.Services daily_drops + check_deposits (PR 92)."""
from datetime import date, time

from api.Modules.DailyBook.Models import CheckDeposit, DailyDrop
from api.Modules.Tenancy.Models import Store
from tests._app import db, db_session


def _add_store(db, *, slug="da-store"):
    s = Store(name=slug, slug=slug, plan="basic",
              email=f"{slug}@example.com")
    db.add(s); db.flush()
    return s


def _add_drop(db, store_id, *, report_date, amount=100.0,
              drop_time=time(9, 0)):
    r = DailyDrop(
        store_id=store_id,
        report_date=report_date,
        drop_time=drop_time,
        amount=amount,
    )
    db.add(r); db.flush()
    return r


def _add_check(db, store_id, *, report_date, amount=100.0,
               check_time=time(9, 0)):
    r = CheckDeposit(
        store_id=store_id,
        report_date=report_date,
        deposit_time=check_time,
        amount=amount,
    )
    db.add(r); db.flush()
    return r


# ── daily_drops ─────────────────────────────────────────


def test_daily_drops_returns_rows_and_totals():
    from tests._app import db
    from api.Modules.Reports.Services import daily_drops
    with db_session():
        db.session.query(DailyDrop).delete()
        db.session.commit()
        s = _add_store(db.session, slug="da-drops-shape")
        rows, totals = daily_drops(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert isinstance(rows, list)
        assert set(totals) == {"count", "amount", "avg_per_day"}


def test_daily_drops_groups_by_report_date():
    """Multiple drops on same date → one bucket; multiple dates →
    multiple buckets."""
    from tests._app import db
    from api.Modules.Reports.Services import daily_drops
    with db_session():
        db.session.query(DailyDrop).delete()
        db.session.commit()
        s = _add_store(db.session, slug="da-drops-group")
        _add_drop(db.session, s.id, report_date=date(2026, 5, 5),
                  amount=100.0, drop_time=time(9, 0))
        _add_drop(db.session, s.id, report_date=date(2026, 5, 5),
                  amount=200.0, drop_time=time(14, 0))
        _add_drop(db.session, s.id, report_date=date(2026, 5, 6),
                  amount=50.0)
        rows, totals = daily_drops(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        # 2 distinct dates → 2 rows.
        assert len(rows) == 2
        by_date = {r["date"]: r for r in rows}
        assert by_date[date(2026, 5, 5)]["count"] == 2
        assert by_date[date(2026, 5, 5)]["amount"] == 300.0
        assert by_date[date(2026, 5, 6)]["count"] == 1
        assert totals["count"] == 3
        assert totals["amount"] == 350.0


def test_daily_drops_sorted_newest_first():
    """Newest date first — the daily-drops table is most recent
    on top."""
    from tests._app import db
    from api.Modules.Reports.Services import daily_drops
    with db_session():
        db.session.query(DailyDrop).delete()
        db.session.commit()
        s = _add_store(db.session, slug="da-drops-sort")
        for d in (5, 20, 10):
            _add_drop(db.session, s.id, report_date=date(2026, 5, d))
        rows, _ = daily_drops(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        dates = [r["date"] for r in rows]
        assert dates == [
            date(2026, 5, 20), date(2026, 5, 10), date(2026, 5, 5),
        ]


def test_daily_drops_avg_per_day_uses_distinct_date_count():
    """avg_per_day divides by distinct date count, not row count.
    Two drops on the same date → still 1 day in the divisor."""
    from tests._app import db
    from api.Modules.Reports.Services import daily_drops
    with db_session():
        db.session.query(DailyDrop).delete()
        db.session.commit()
        s = _add_store(db.session, slug="da-drops-avg")
        _add_drop(db.session, s.id, report_date=date(2026, 5, 5),
                  amount=100.0, drop_time=time(9, 0))
        _add_drop(db.session, s.id, report_date=date(2026, 5, 5),
                  amount=200.0, drop_time=time(14, 0))
        _, totals = daily_drops(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        # 1 distinct date with $300 total → avg_per_day = $300.
        assert totals["avg_per_day"] == 300.0


def test_daily_drops_avg_per_day_zero_when_no_rows():
    """No drops → avg_per_day = 0 (no divide-by-zero)."""
    from tests._app import db
    from api.Modules.Reports.Services import daily_drops
    with db_session():
        db.session.query(DailyDrop).delete()
        db.session.commit()
        s = _add_store(db.session, slug="da-drops-empty")
        _, totals = daily_drops(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["avg_per_day"] == 0.0
        assert totals["count"] == 0


def test_daily_drops_filters_by_store_and_window():
    from tests._app import db
    from api.Modules.Reports.Services import daily_drops
    with db_session():
        db.session.query(DailyDrop).delete()
        db.session.commit()
        s1 = _add_store(db.session, slug="da-drops-store-1")
        s2 = _add_store(db.session, slug="da-drops-store-2")
        # Wrong store.
        _add_drop(db.session, s2.id, report_date=date(2026, 5, 5),
                  amount=999.0)
        # Outside window.
        _add_drop(db.session, s1.id, report_date=date(2026, 4, 30),
                  amount=999.0)
        # Inside.
        _add_drop(db.session, s1.id, report_date=date(2026, 5, 15),
                  amount=100.0)
        _, totals = daily_drops(
            db.session, [s1.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["amount"] == 100.0


# ── check_deposits ─────────────────────────────────────


def test_check_deposits_returns_rows_and_totals():
    from tests._app import db
    from api.Modules.Reports.Services import check_deposits
    with db_session():
        db.session.query(CheckDeposit).delete()
        db.session.commit()
        s = _add_store(db.session, slug="da-checks-shape")
        rows, totals = check_deposits(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert isinstance(rows, list)
        assert set(totals) == {"count", "amount", "avg_per_day"}


def test_check_deposits_groups_by_report_date():
    from tests._app import db
    from api.Modules.Reports.Services import check_deposits
    with db_session():
        db.session.query(CheckDeposit).delete()
        db.session.commit()
        s = _add_store(db.session, slug="da-checks-group")
        _add_check(db.session, s.id, report_date=date(2026, 5, 5),
                   amount=200.0, check_time=time(9, 0))
        _add_check(db.session, s.id, report_date=date(2026, 5, 5),
                   amount=300.0, check_time=time(14, 0))
        rows, totals = check_deposits(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert len(rows) == 1
        assert rows[0]["count"] == 2
        assert rows[0]["amount"] == 500.0


# ── legacy wrappers ─────────────────────────────────────




