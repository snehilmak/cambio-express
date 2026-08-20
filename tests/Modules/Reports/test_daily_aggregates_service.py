"""Unit tests for Reports.Services daily_drops + check_deposits.

Fixtures seed ``DailyLineItem`` rows (kind='drop' / 'check_deposit')
— the ONLY write path since the legacy ``DailyDrop`` /
``CheckDeposit`` tables were retired. The reports were reading the
legacy tables until the 2026-08 report audit (user-reported: Check
Deposits loaded nothing); these tests pin the corrected source.
"""
from datetime import date, time

from api.Modules.DailyBook.Models import DailyLineItem
from api.Modules.Tenancy.Models import Store
from tests._app import db, db_session


def _add_store(db, *, slug="da-store"):
    s = Store(name=slug, slug=slug, plan="basic",
              email=f"{slug}@example.com")
    db.add(s); db.flush()
    return s


def _add_item(db, store_id, *, kind, report_date, amount=100.0,
              at_time=time(9, 0)):
    r = DailyLineItem(
        store_id=store_id,
        report_date=report_date,
        kind=kind,
        at_time=at_time,
        amount=amount,
    )
    db.add(r); db.flush()
    return r


def _add_drop(db, store_id, *, report_date, amount=100.0,
              drop_time=time(9, 0)):
    return _add_item(db, store_id, kind="drop",
                     report_date=report_date, amount=amount,
                     at_time=drop_time)


def _add_check(db, store_id, *, report_date, amount=100.0,
               check_time=time(9, 0)):
    return _add_item(db, store_id, kind="check_deposit",
                     report_date=report_date, amount=amount,
                     at_time=check_time)


# ── daily_drops ─────────────────────────────────────────


def test_daily_drops_returns_rows_and_totals():
    from tests._app import db
    from api.Modules.Reports.Services import daily_drops
    with db_session():
        db.session.query(DailyLineItem).filter_by(kind="drop").delete()
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
        db.session.query(DailyLineItem).filter_by(kind="drop").delete()
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
        db.session.query(DailyLineItem).filter_by(kind="drop").delete()
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
        db.session.query(DailyLineItem).filter_by(kind="drop").delete()
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
        db.session.query(DailyLineItem).filter_by(kind="drop").delete()
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
        db.session.query(DailyLineItem).filter_by(kind="drop").delete()
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
        db.session.query(DailyLineItem).filter_by(kind="check_deposit").delete()
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
        db.session.query(DailyLineItem).filter_by(kind="check_deposit").delete()
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


# ── stale-source regression (2026-08 report audit) ────────────


def test_legacy_tables_are_not_read():
    """A row sitting ONLY in the retired DailyDrop / CheckDeposit
    tables (i.e. not yet copied by the boot-time backfill) must not
    be counted — the reports read daily_line_item exclusively, so a
    UNION would double-count all backfilled history."""
    from datetime import time as _time
    from tests._app import db
    from api.Modules.DailyBook.Models import CheckDeposit, DailyDrop
    from api.Modules.Reports.Services import check_deposits, daily_drops
    with db_session():
        db.session.query(DailyLineItem).filter(
            DailyLineItem.kind.in_(("drop", "check_deposit")),
        ).delete(synchronize_session=False)
        db.session.commit()
        s = _add_store(db.session, slug="da-legacy-only")
        db.session.add(DailyDrop(
            store_id=s.id, report_date=date(2026, 5, 5),
            drop_time=_time(9, 0), amount=500.0,
        ))
        db.session.add(CheckDeposit(
            store_id=s.id, report_date=date(2026, 5, 5),
            deposit_time=_time(9, 0), amount=700.0,
        ))
        db.session.commit()
        d_rows, d_totals = daily_drops(
            db.session, [s.id], date(2026, 5, 1), date(2026, 5, 31),
        )
        c_rows, c_totals = check_deposits(
            db.session, [s.id], date(2026, 5, 1), date(2026, 5, 31),
        )
        assert d_rows == [] and d_totals["amount"] == 0.0
        assert c_rows == [] and c_totals["amount"] == 0.0


def test_line_item_deposits_show_up():
    """The user-reported case: check deposits logged through the
    daily book (line items) must appear in the report."""
    from tests._app import db
    from api.Modules.Reports.Services import check_deposits
    with db_session():
        db.session.query(DailyLineItem).filter_by(
            kind="check_deposit",
        ).delete(synchronize_session=False)
        db.session.commit()
        s = _add_store(db.session, slug="da-li-deposits")
        _add_check(db.session, s.id,
                   report_date=date(2026, 8, 7), amount=47131.25)
        db.session.commit()
        rows, totals = check_deposits(
            db.session, [s.id], date(2026, 8, 1), date(2026, 8, 31),
        )
        assert totals["amount"] == 47131.25
        assert rows[0]["count"] == 1
