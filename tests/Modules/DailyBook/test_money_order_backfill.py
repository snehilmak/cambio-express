"""Backfill for the money_order → line-item conversion migration
(``a9d5f1c7e3b8_backfill_money_order_line_items``).

Pins the risky bits of the data migration: the ``money_order > 0``
filter, the one-entry-per-report shape, and the NOT EXISTS
idempotency guard (a Render replay must not double-count). Mirror
of ``test_from_bank_backfill.py``.
"""
from __future__ import annotations

import importlib.util
from datetime import date

import pytest
from pathlib import Path

from tests._app import db, db_session


def _load_migration():
    path = (
        Path(__file__).resolve().parents[3]
        / "alembic" / "versions"
        / "a9d5f1c7e3b8_backfill_money_order_line_items.py"
    )
    spec = importlib.util.spec_from_file_location("_money_order_backfill_mig", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _seed_report(store_id: int, day: date, money_order: float):
    from api.Modules.DailyBook.Models import DailyReport
    db.session.add(
        DailyReport(store_id=store_id, report_date=day, money_order=money_order)
    )


def _money_order_items(store_id: int, day: date):
    from api.Modules.DailyBook.Models import DailyLineItem
    return (
        db.session.query(DailyLineItem)
        .filter_by(store_id=store_id, report_date=day, kind="money_order")
        .all()
    )


@pytest.mark.skip(
    reason="Historical one-shot backfill predates the cents schema "
           "(P0-3): its raw SQL reads the old Float columns, which "
           "exist at its point in the migration chain but not in the "
           "live schema. The chain itself is exercised by conftest's "
           "alembic upgrade head on every run."
)
def test_backfill_seeds_positive_reports_only_and_is_idempotent(test_store_id):
    from api.Modules.DailyBook.Models import DailyLineItem
    mig = _load_migration()
    d_pos = date(2026, 2, 10)
    d_zero = date(2026, 2, 11)
    d_existing = date(2026, 2, 12)

    with db_session():
        _seed_report(test_store_id, d_pos, 425.0)    # should seed one entry
        _seed_report(test_store_id, d_zero, 0.0)     # zero → skipped
        _seed_report(test_store_id, d_existing, 60.0)
        # d_existing already has a money_order line item → must not double
        db.session.add(
            DailyLineItem(
                store_id=test_store_id, report_date=d_existing,
                kind="money_order", amount=60.0,
            )
        )
        db.session.flush()

        seeded = mig.backfill_money_order_line_items(db.session.connection())
        assert seeded == 1  # only the positive, un-seeded report

        pos_items = _money_order_items(test_store_id, d_pos)
        assert len(pos_items) == 1
        assert pos_items[0].amount == 425.0
        assert pos_items[0].at_time is None

        assert _money_order_items(test_store_id, d_zero) == []
        # existing report keeps exactly its one original line item
        assert len(_money_order_items(test_store_id, d_existing)) == 1

        # Re-running seeds nothing (idempotent replay guard).
        again = mig.backfill_money_order_line_items(db.session.connection())
        assert again == 0
        assert len(_money_order_items(test_store_id, d_pos)) == 1
