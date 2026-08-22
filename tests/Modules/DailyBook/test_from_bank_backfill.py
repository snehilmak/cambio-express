"""Backfill for the from_bank → line-item conversion migration
(``b8e2f4a1c9d7_backfill_from_bank_line_items``).

Pins the risky bits of the data migration: the ``from_bank > 0``
filter, the one-entry-per-report shape, and the NOT EXISTS
idempotency guard (a Render replay must not double-count).
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
        / "b8e2f4a1c9d7_backfill_from_bank_line_items.py"
    )
    spec = importlib.util.spec_from_file_location("_from_bank_backfill_mig", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _seed_report(store_id: int, day: date, from_bank: float):
    from api.Modules.DailyBook.Models import DailyReport
    db.session.add(
        DailyReport(store_id=store_id, report_date=day, from_bank=from_bank)
    )


def _from_bank_items(store_id: int, day: date):
    from api.Modules.DailyBook.Models import DailyLineItem
    return (
        db.session.query(DailyLineItem)
        .filter_by(store_id=store_id, report_date=day, kind="from_bank")
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
    d_pos = date(2026, 1, 10)
    d_zero = date(2026, 1, 11)
    d_existing = date(2026, 1, 12)

    with db_session():
        _seed_report(test_store_id, d_pos, 150.0)   # should seed one entry
        _seed_report(test_store_id, d_zero, 0.0)     # zero → skipped
        _seed_report(test_store_id, d_existing, 99.0)
        # d_existing already has a from_bank line item → must not double
        db.session.add(
            DailyLineItem(
                store_id=test_store_id, report_date=d_existing,
                kind="from_bank", amount=99.0,
            )
        )
        db.session.flush()

        seeded = mig.backfill_from_bank_line_items(db.session.connection())
        assert seeded == 1  # only the positive, un-seeded report

        pos_items = _from_bank_items(test_store_id, d_pos)
        assert len(pos_items) == 1
        assert pos_items[0].amount == 150.0
        assert pos_items[0].at_time is None

        assert _from_bank_items(test_store_id, d_zero) == []
        # existing report keeps exactly its one original line item
        assert len(_from_bank_items(test_store_id, d_existing)) == 1

        # Re-running seeds nothing (idempotent replay guard).
        again = mig.backfill_from_bank_line_items(db.session.connection())
        assert again == 0
        assert len(_from_bank_items(test_store_id, d_pos)) == 1
