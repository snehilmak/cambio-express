"""Store Daily Book (D-2) — the sheet's arithmetic and write rules.

The page is three columns that must balance; over/short is the
difference between two of them. If that number is wrong the sheet
is worse than useless, so it is pinned from several directions.
"""
from datetime import date

import pytest

from api.Modules.StoreBook.Models import (
    COUNT_FIELDS, FIELD_COLUMN, FIELD_GROUPS, MONEY_FIELDS,
    StoreDailyEntry,
)
from api.Modules.StoreBook.Services import (
    DayLockedError, StoreBookError, apply_import, column_totals,
    get_or_create_entry, month_summary, originals_for,
    over_short_cents, restore_original, set_lock, update_entry,
)
from tests._app import db, db_session

DAY = date(2026, 8, 2)


def _store(slug):
    from api.Modules.Tenancy.Models import Store
    s = Store(name=slug, slug=slug, email=f"{slug}@x.com", plan="basic")
    db.session.add(s); db.session.commit()
    return s.id


# ── Field model ─────────────────────────────────────────────


def test_every_declared_field_has_a_column():
    """FIELD_GROUPS drives the page, the API and the totals. A key
    without a column would render an input that silently discards
    what the operator types."""
    for key in MONEY_FIELDS:
        assert hasattr(StoreDailyEntry, f"{key}_cents"), key
    for key in COUNT_FIELDS:
        assert hasattr(StoreDailyEntry, key), key


def test_field_keys_are_unique_across_the_sheet():
    """A duplicated key would make one input overwrite another."""
    assert len(MONEY_FIELDS) == len(set(MONEY_FIELDS))
    assert len(COUNT_FIELDS) == len(set(COUNT_FIELDS))
    assert not set(MONEY_FIELDS) & set(COUNT_FIELDS)


def test_every_field_belongs_to_exactly_one_column():
    for key in MONEY_FIELDS:
        assert FIELD_COLUMN[key] in ("sales", "tenders", "deposit")
    assert {c["column"] for c in FIELD_GROUPS} == {
        "sales", "tenders", "deposit",
    }


# ── The balance ─────────────────────────────────────────────


def test_over_short_is_tenders_minus_sales():
    """Reproduces the real figures from a live competitor sheet:
    sales 20,647.71 vs tenders 20,672.34 → 24.63 over."""
    with db_session():
        sid = _store("sdb-balance")
        e = get_or_create_entry(db.session, sid, DAY)
        update_entry(db.session, e, {
            "gross_sales": 2_064_771,   # the whole sales column
            "cards": 1_208_534,
            "closing_cash": 780_900,
            "lotto_paid_out": 54_800,
            "paid_out_purchases": 23_000,
        })
        totals = column_totals(e)
        assert totals["sales"] == 2_064_771
        assert totals["tenders"] == 2_067_234
        assert over_short_cents(e) == 2_463   # $24.63 over


def test_over_short_is_negative_when_short():
    with db_session():
        sid = _store("sdb-short")
        e = get_or_create_entry(db.session, sid, DAY)
        update_entry(db.session, e, {
            "gross_sales": 100_000, "closing_cash": 99_000,
        })
        assert over_short_cents(e) == -1_000


def test_empty_day_balances_at_zero():
    """A day nobody has touched must not look like a shortage."""
    with db_session():
        sid = _store("sdb-empty")
        e = get_or_create_entry(db.session, sid, DAY)
        assert column_totals(e) == {"sales": 0, "tenders": 0, "deposit": 0}
        assert over_short_cents(e) == 0


def test_column_totals_count_each_field_once():
    """Set every money field to $1 — each column total must equal
    its own field count exactly, catching a field summed twice or
    into the wrong column."""
    from collections import Counter
    with db_session():
        sid = _store("sdb-once")
        e = get_or_create_entry(db.session, sid, DAY)
        update_entry(db.session, e, {k: 100 for k in MONEY_FIELDS})
        expected = Counter(FIELD_COLUMN.values())
        totals = column_totals(e)
        for column, n in expected.items():
            assert totals[column] == n * 100, column


# ── Locking ─────────────────────────────────────────────────


def test_locked_day_rejects_operator_edits():
    with db_session():
        sid = _store("sdb-lock")
        e = get_or_create_entry(db.session, sid, DAY)
        set_lock(db.session, e, locked=True, user_id=None)
        with pytest.raises(DayLockedError):
            update_entry(db.session, e, {"gross_sales": 500})


def test_unlock_restores_editing():
    with db_session():
        sid = _store("sdb-unlock")
        e = get_or_create_entry(db.session, sid, DAY)
        set_lock(db.session, e, locked=True, user_id=None)
        set_lock(db.session, e, locked=False, user_id=None)
        update_entry(db.session, e, {"gross_sales": 500})
        assert e.gross_sales_cents == 500


def test_import_still_lands_on_a_locked_day():
    """The lock protects the operator's numbers from being edited,
    not the record from receiving what the register did. Dropping a
    day's POS data because the sheet was locked early would lose
    money with no trace."""
    with db_session():
        sid = _store("sdb-lockimport")
        e = get_or_create_entry(db.session, sid, DAY)
        set_lock(db.session, e, locked=True, user_id=None)
        apply_import(db.session, e, {"gross_sales": 9_999}, source="gilbarco")
        assert e.gross_sales_cents == 9_999


# ── Imported values vs operator edits ───────────────────────


def test_import_records_the_original_and_fills_the_field():
    with db_session():
        sid = _store("sdb-import")
        e = get_or_create_entry(db.session, sid, DAY)
        apply_import(
            db.session, e, {"lottery_sales": 24_900}, source="gilbarco",
        )
        assert e.lottery_sales_cents == 24_900
        assert originals_for(e) == {"lottery_sales": 24_900}


def test_operator_edit_survives_a_re_import():
    """The competitor's sheet shows Lottery Sales 417.00 over an
    'Orig. Val: $249.00' — the operator's correction must not be
    silently reverted the next time the POS pushes the same day."""
    with db_session():
        sid = _store("sdb-override")
        e = get_or_create_entry(db.session, sid, DAY)
        apply_import(
            db.session, e, {"lottery_sales": 24_900}, source="gilbarco",
        )
        update_entry(db.session, e, {"lottery_sales": 41_700})

        apply_import(
            db.session, e, {"lottery_sales": 24_900}, source="gilbarco",
        )
        # Operator's number stands...
        assert e.lottery_sales_cents == 41_700
        # ...and the register's is still on record beside it.
        assert originals_for(e)["lottery_sales"] == 24_900


def test_untouched_field_follows_a_re_import():
    """A value the operator never edited should track the register,
    otherwise a corrected POS figure would never reach the sheet."""
    with db_session():
        sid = _store("sdb-follow")
        e = get_or_create_entry(db.session, sid, DAY)
        apply_import(db.session, e, {"gross_sales": 1_000}, source="gilbarco")
        apply_import(db.session, e, {"gross_sales": 2_000}, source="gilbarco")
        assert e.gross_sales_cents == 2_000


def test_restore_original_takes_the_register_number_back():
    with db_session():
        sid = _store("sdb-restore")
        e = get_or_create_entry(db.session, sid, DAY)
        apply_import(
            db.session, e, {"lottery_sales": 24_900}, source="gilbarco",
        )
        update_entry(db.session, e, {"lottery_sales": 41_700})
        restore_original(db.session, e, "lottery_sales")
        assert e.lottery_sales_cents == 24_900


def test_restore_needs_an_imported_value():
    with db_session():
        sid = _store("sdb-norestore")
        e = get_or_create_entry(db.session, sid, DAY)
        with pytest.raises(StoreBookError):
            restore_original(db.session, e, "gross_sales")


# ── Unknown fields ──────────────────────────────────────────


def test_unknown_field_is_rejected_not_ignored():
    """A typo'd key must not look like a successful save that
    quietly dropped the number."""
    with db_session():
        sid = _store("sdb-unknown")
        e = get_or_create_entry(db.session, sid, DAY)
        with pytest.raises(StoreBookError):
            update_entry(db.session, e, {"grosss_sales": 100})
        with pytest.raises(StoreBookError):
            apply_import(db.session, e, {"nope": 1}, source="gilbarco")


# ── Day + month plumbing ────────────────────────────────────


def test_entry_is_created_on_first_touch_and_reused_after():
    with db_session():
        sid = _store("sdb-getorcreate")
        a = get_or_create_entry(db.session, sid, DAY)
        db.session.commit()
        b = get_or_create_entry(db.session, sid, DAY)
        assert a.id == b.id


def test_month_summary_lists_days_with_totals_and_lock_state():
    with db_session():
        sid = _store("sdb-month")
        e1 = get_or_create_entry(db.session, sid, date(2026, 8, 2))
        update_entry(db.session, e1, {"gross_sales": 196_300})
        set_lock(db.session, e1, locked=True, user_id=None)
        e2 = get_or_create_entry(db.session, sid, date(2026, 8, 5))
        update_entry(db.session, e2, {"gross_sales": 50_000})
        # A day in another month must not appear.
        get_or_create_entry(db.session, sid, date(2026, 9, 1))
        db.session.commit()

        rows = month_summary(db.session, sid, 2026, 8)
        assert [r["entry_date"] for r in rows] == ["2026-08-02", "2026-08-05"]
        assert rows[0]["sales_cents"] == 196_300
        assert rows[0]["is_locked"] is True
        assert rows[1]["is_locked"] is False


def test_month_summary_isolates_stores():
    with db_session():
        mine = _store("sdb-mine")
        theirs = _store("sdb-theirs")
        update_entry(
            db.session, get_or_create_entry(db.session, theirs, DAY),
            {"gross_sales": 999_999},
        )
        db.session.commit()
        assert month_summary(db.session, mine, 2026, 8) == []
