"""Unit tests for Reports.Services.ach_volume (PR 88)."""
from datetime import date

from api.Modules.Batches.Models import ACHBatch
from api.Modules.Tenancy.Models import Store
from tests._app import db, db_session


def _add_store(db, *, slug="ach-store"):
    s = Store(name=slug, slug=slug, plan="basic",
              email=f"{slug}@example.com")
    db.add(s); db.flush()
    return s


_BATCH_COUNTER = 0


def _add_batch(db, store_id, *, ach_date, company="Intermex",
               ach_amount=100.0):
    global _BATCH_COUNTER
    _BATCH_COUNTER += 1
    b = ACHBatch(
        store_id=store_id,
        ach_date=ach_date,
        company=company,
        ach_amount=ach_amount,
        batch_ref=f"REF-{_BATCH_COUNTER}",
    )
    db.add(b); db.flush()
    return b


# ── shape ────────────────────────────────────────────────


def test_returns_rows_and_totals_tuple():
    """Service returns (rows, totals); rows is a list of dicts;
    totals dict has count + amount keys."""
    from tests._app import db
    from api.Modules.Reports.Services import ach_volume
    with db_session():
        s = _add_store(db.session, slug="ach-shape")
        rows, totals = ach_volume(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert isinstance(rows, list)
        assert isinstance(totals, dict)
        assert set(totals) == {"count", "amount"}


def test_row_shape_has_company_count_amount_avg():
    from tests._app import db
    from api.Modules.Reports.Services import ach_volume
    with db_session():
        db.session.query(ACHBatch).delete()
        db.session.commit()
        s = _add_store(db.session, slug="ach-shape2")
        _add_batch(db.session, s.id, ach_date=date(2026, 5, 5),
                   company="Maxi", ach_amount=200.0)
        rows, _ = ach_volume(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert len(rows) == 1
        assert set(rows[0]) == {"company", "count", "amount", "avg"}


# ── grouping ─────────────────────────────────────────────


def test_groups_by_company():
    from tests._app import db
    from api.Modules.Reports.Services import ach_volume
    with db_session():
        db.session.query(ACHBatch).delete()
        db.session.commit()
        s = _add_store(db.session, slug="ach-group")
        _add_batch(db.session, s.id, ach_date=date(2026, 5, 5),
                   company="Intermex", ach_amount=100.0)
        _add_batch(db.session, s.id, ach_date=date(2026, 5, 6),
                   company="Intermex", ach_amount=200.0)
        _add_batch(db.session, s.id, ach_date=date(2026, 5, 7),
                   company="Maxi", ach_amount=50.0)
        rows, totals = ach_volume(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        by_company = {r["company"]: r for r in rows}
        assert by_company["Intermex"]["count"] == 2
        assert by_company["Intermex"]["amount"] == 300.0
        assert by_company["Maxi"]["count"] == 1
        assert by_company["Maxi"]["amount"] == 50.0
        assert totals == {"count": 3, "amount": 350.0}


def test_avg_is_amount_over_count():
    from tests._app import db
    from api.Modules.Reports.Services import ach_volume
    with db_session():
        db.session.query(ACHBatch).delete()
        db.session.commit()
        s = _add_store(db.session, slug="ach-avg")
        _add_batch(db.session, s.id, ach_date=date(2026, 5, 5),
                   company="Intermex", ach_amount=100.0)
        _add_batch(db.session, s.id, ach_date=date(2026, 5, 6),
                   company="Intermex", ach_amount=200.0)
        rows, _ = ach_volume(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert rows[0]["avg"] == 150.0  # 300 / 2


def test_blank_company_displayed_as_no_company_label():
    """ACHBatch with blank company is rendered as '(no company)'
    so the template can still show a row instead of a blank cell."""
    from tests._app import db
    from api.Modules.Reports.Services import ach_volume
    with db_session():
        db.session.query(ACHBatch).delete()
        db.session.commit()
        s = _add_store(db.session, slug="ach-null")
        _add_batch(db.session, s.id, ach_date=date(2026, 5, 5),
                   company="", ach_amount=100.0)
        rows, _ = ach_volume(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert len(rows) == 1
        assert rows[0]["company"] == "(no company)"


# ── ordering ─────────────────────────────────────────────


def test_rows_sorted_by_amount_descending():
    """Biggest mover lands first — the report's headline view."""
    from tests._app import db
    from api.Modules.Reports.Services import ach_volume
    with db_session():
        db.session.query(ACHBatch).delete()
        db.session.commit()
        s = _add_store(db.session, slug="ach-sort")
        _add_batch(db.session, s.id, ach_date=date(2026, 5, 5),
                   company="Small", ach_amount=10.0)
        _add_batch(db.session, s.id, ach_date=date(2026, 5, 6),
                   company="Big", ach_amount=1000.0)
        _add_batch(db.session, s.id, ach_date=date(2026, 5, 7),
                   company="Medium", ach_amount=100.0)
        rows, _ = ach_volume(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert [r["company"] for r in rows] == ["Big", "Medium", "Small"]


# ── scoping ─────────────────────────────────────────────


def test_filters_by_store_list():
    from tests._app import db
    from api.Modules.Reports.Services import ach_volume
    with db_session():
        db.session.query(ACHBatch).delete()
        db.session.commit()
        s1 = _add_store(db.session, slug="ach-store-1")
        s2 = _add_store(db.session, slug="ach-store-2")
        _add_batch(db.session, s1.id, ach_date=date(2026, 5, 5),
                   company="Intermex", ach_amount=100.0)
        _add_batch(db.session, s2.id, ach_date=date(2026, 5, 5),
                   company="Intermex", ach_amount=999.0)
        rows, totals = ach_volume(
            db.session, [s1.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["amount"] == 100.0


def test_filters_by_date_window():
    from tests._app import db
    from api.Modules.Reports.Services import ach_volume
    with db_session():
        db.session.query(ACHBatch).delete()
        db.session.commit()
        s = _add_store(db.session, slug="ach-window")
        _add_batch(db.session, s.id, ach_date=date(2026, 4, 30),
                   company="Intermex", ach_amount=999.0)
        _add_batch(db.session, s.id, ach_date=date(2026, 6, 1),
                   company="Intermex", ach_amount=999.0)
        _add_batch(db.session, s.id, ach_date=date(2026, 5, 15),
                   company="Intermex", ach_amount=100.0)
        _, totals = ach_volume(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["amount"] == 100.0


def test_empty_window_returns_empty_rows_and_zero_totals():
    from tests._app import db
    from api.Modules.Reports.Services import ach_volume
    with db_session():
        db.session.query(ACHBatch).delete()
        db.session.commit()
        s = _add_store(db.session, slug="ach-empty")
        rows, totals = ach_volume(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert rows == []
        assert totals == {"count": 0, "amount": 0.0}


# ── legacy wrapper ───────────────────────────────────────


