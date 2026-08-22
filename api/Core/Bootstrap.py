"""Bootstrap helpers — schema, indexes, legacy backfills, seed data.

Lifted out of ``app.py``'s ``init_db()`` orchestrator so the new
ASGI entry point (and the standalone scripts) can call them
directly with a SQLAlchemy session / engine, no Flask app_context
required.

Public surface (all idempotent — safe on every boot):

  - :func:`apply_schema(engine, logger=None)` — Alembic
    ``upgrade head``, with the case-2 stamp for pre-managed DBs.
  - :func:`ensure_added_indexes(engine, logger=None)` — the
    ``CREATE INDEX IF NOT EXISTS`` safety-net list for indexes
    Alembic autogenerate doesn't reliably pick up.
  - :func:`drop_legacy_tables(engine, logger=None)` — DROP TABLE
    IF EXISTS for tables retired from the model registry but
    still present in older deploys.
  - :func:`migrate_legacy_line_item_tables(session)` — one-shot
    copy of ``DailyDrop`` + ``CheckDeposit`` rows into
    ``DailyLineItem(kind=…)``.
  - :func:`rename_maxi_transfer_to_maxi(session)` — one-shot
    company-name backfill.
  - :func:`seed_feature_flags(session)` — insert the
    ``FeatureFlag`` rows for any keys not already present.

The data tables (``ADDED_INDEXES``, ``DROPPED_TABLES``,
``DEFAULT_FEATURE_FLAGS``) live alongside the functions so tests
can introspect them directly.
"""
from __future__ import annotations

import logging
import os
from typing import Sequence

from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from api.Core.Clock import utc_now


_log = logging.getLogger(__name__)


# Each entry is (index_name, table, column_csv). When adding a new
# index, ALSO declare it on the SQLAlchemy model so a fresh Alembic
# baseline picks it up; this list is the bridge for already-deployed
# DBs.
ADDED_INDEXES: list[tuple[str, str, str]] = [
    # Transfer hot path.
    ("ix_transfer_store_send_date", "transfer", "store_id, send_date"),
    ("ix_transfer_customer_id",     "transfer", "customer_id"),
    ("ix_transfer_created_by",      "transfer", "created_by"),
    ("ix_transfer_status",          "transfer", "status"),
    ("ix_transfer_confirm_number",  "transfer", "confirm_number"),
    # Customer umbrella-upsert lookup. Non-unique on
    # (phone_country, phone_number); the existing unique constraint
    # on (store_id, phone_country, phone_number) stays put.
    ("ix_customer_phone",           "customer", "phone_country, phone_number"),
    # User cross-store username lookup. ``user`` is a Postgres
    # reserved word, but the DDL below double-quotes the table name.
    ("ix_user_username",            "user",     "username"),
    # LoginEvent DAU/MAU covering composite.
    ("ix_login_event_at_user",      "login_event", "at, user_id"),
    # Missing FK indexes on ``store_id`` for cascade-delete + JOIN
    # performance. Postgres does not auto-index FKs; without these,
    # each cascade in the data-retention purge is a full table scan.
    ("ix_store_employee_store_id",      "store_employee",      "store_id"),
    ("ix_operator_audit_log_store_id",  "operator_audit_log",  "store_id"),
    ("ix_transfer_audit_store_id",      "transfer_audit",      "store_id"),
    ("ix_daily_drop_store_id",          "daily_drop",          "store_id"),
    ("ix_check_deposit_store_id",       "check_deposit",       "store_id"),
    ("ix_return_check_store_id",        "return_check",        "store_id"),
    ("ix_daily_line_item_store_id",     "daily_line_item",     "store_id"),
    ("ix_stripe_bank_account_store_id", "stripe_bank_account", "store_id"),
    ("ix_store_owner_link_store_id",    "store_owner_link",    "store_id"),
]


# Legacy tables removed from the model registry but possibly
# present in older deployed DBs. DROP TABLE IF EXISTS is
# idempotent — safe to leave forever.
DROPPED_TABLES: list[str] = ["simplefin_config", "owner_invite_code"]


# Feature flags seeded on first boot.
# Each entry is (key, label, description, enabled_by_default).
DEFAULT_FEATURE_FLAGS: list[tuple[str, str, str, bool]] = [
    ("addon_tv_display", "Add-on: TV Display & Rates",
     "Show the TV Display add-on in the subscription page.", True),
    ("bank_sync", "Bank sync (Stripe)",
     "Enable the Pro-tier Stripe Financial Connections bank sync for stores.",
     True),
    ("multi_store_owner", "Multi-store owner portal",
     "Allow store admins to generate owner invite codes.", True),
]


def _resolve_logger(logger: logging.Logger | None) -> logging.Logger:
    return logger or _log


def apply_schema(engine: Engine, logger: logging.Logger | None = None) -> None:
    """Bring the DB schema up to the latest Alembic revision.

    Three cases:

      1. **Empty DB** (no ``alembic_version``, no app tables) —
         fresh install. ``upgrade head`` runs every revision from
         the baseline.
      2. **Pre-Alembic DB** (no ``alembic_version`` BUT app tables
         already exist) — the production prod database before
         chunk 1 + a few dev DBs that were created via the old
         ``db.create_all()`` path. Running ``upgrade head`` here
         would crash on ``CREATE TABLE`` for tables that already
         exist. Recovery: ``alembic stamp head`` — record "we're
         at head" without running any DDL.
      3. **Managed DB** (``alembic_version`` exists) — normal
         path. ``upgrade head`` applies any new revisions since
         the last boot. No-op when already at head.

    The caller's existing engine is reused via ``cfg.attributes``
    so both Alembic and SQLAlchemy run against the SAME database
    — matters for in-memory SQLite tests where each engine
    creates its own private DB.
    """
    log = _resolve_logger(logger)
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", str(engine.url))

    prev_skip = os.environ.get("DINEROBOOK_SKIP_INIT_DB")
    try:
        # ``engine.begin()`` opens a transaction and commits on
        # exit (vs ``engine.connect()`` which silently rolls back).
        # The explicit commit is critical for SQLite in-memory
        # tests + StaticPool — without it the upgrade DDL
        # evaporates when the connection returns to the pool.
        with engine.begin() as connection:
            # Serialize migrations across gunicorn workers. With
            # --workers 2+, every worker runs init_db() on boot;
            # without a lock, two workers can race on `upgrade head`
            # and one crashes with "expected to match one row …
            # 0 found" because the alembic_version row is being
            # mutated concurrently. pg_advisory_xact_lock blocks
            # until the first worker's transaction commits, then the
            # second worker's upgrade is a no-op ("already at head").
            if engine.dialect.name == "postgresql":
                from sqlalchemy import text
                connection.execute(text(
                    "SELECT pg_advisory_xact_lock(8675309)"
                ))

            cfg.attributes["connection"] = connection
            inspector = inspect(connection)
            table_names = set(inspector.get_table_names())
            has_alembic_table = "alembic_version" in table_names
            has_app_tables = bool(table_names - {"alembic_version"})
            if not has_alembic_table and has_app_tables:
                # Case 2: schema exists from the pre-Alembic boot
                # path. Stamp head without running any DDL.
                command.stamp(cfg, "head")
                log.info(
                    "Alembic stamped 'head' on pre-managed DB "
                    "(%d existing tables)", len(table_names),
                )
            else:
                # Case 1 (fresh DB) and case 3 (already managed)
                # both take the standard upgrade path.
                command.upgrade(cfg, "head")
                log.info("Alembic upgrade head: OK")
    finally:
        if prev_skip is None:
            os.environ.pop("DINEROBOOK_SKIP_INIT_DB", None)
        else:
            os.environ["DINEROBOOK_SKIP_INIT_DB"] = prev_skip


def ensure_added_indexes(
    engine: Engine,
    logger: logging.Logger | None = None,
    indexes: Sequence[tuple[str, str, str]] = ADDED_INDEXES,
) -> None:
    """Apply the ``ADDED_INDEXES`` safety-net.

    Both sqlite and Postgres support ``CREATE INDEX IF NOT EXISTS``,
    so the same DDL works for both. Each statement runs in its own
    transaction on Postgres so one failure doesn't poison the rest.
    Failures log a warning instead of crashing boot — a missing
    index slows queries but doesn't stop the app.
    """
    log = _resolve_logger(logger)
    try:
        dialect = engine.dialect.name
    except Exception as e:
        log.warning("index migration skipped (no engine): %s", e)
        return
    for name, table, cols in indexes:
        ddl = f'CREATE INDEX IF NOT EXISTS {name} ON "{table}" ({cols})'
        try:
            if dialect == "sqlite":
                with engine.connect() as conn:
                    conn.exec_driver_sql(ddl)
                    conn.commit()
            else:
                with engine.begin() as conn:
                    conn.exec_driver_sql(ddl)
        except Exception as e:
            log.warning("%s CREATE INDEX failed for %s: %s", dialect, name, e)


def drop_legacy_tables(
    engine: Engine,
    logger: logging.Logger | None = None,
    tables: Sequence[str] = DROPPED_TABLES,
) -> None:
    """``DROP TABLE IF EXISTS`` for tables retired from the model
    registry but possibly still present in older deployed DBs."""
    log = _resolve_logger(logger)
    try:
        for table in tables:
            with engine.begin() as conn:
                conn.exec_driver_sql(f'DROP TABLE IF EXISTS "{table}"')
    except Exception as e:
        log.warning("legacy table drop skipped: %s", e)


def seed_feature_flags(session: Session) -> None:
    """Insert the ``FeatureFlag`` rows for any keys not already
    present. Idempotent — re-running only inserts entries with
    new keys, so superadmin edits are preserved across deploys."""
    from api.Modules.Billing.Models import FeatureFlag

    for key, label, description, enabled in DEFAULT_FEATURE_FLAGS:
        if not session.query(FeatureFlag).filter_by(key=key).first():
            session.add(FeatureFlag(
                key=key, label=label, description=description,
                enabled_by_default=enabled,
            ))
    session.commit()


def rename_maxi_transfer_to_maxi(
    session: Session,
    logger: logging.Logger | None = None,
) -> None:
    """One-time idempotent backfill: rename legacy 'Maxi Transfer'
    to 'Maxi' in every place a company name is persisted. Safe on
    every boot — after the first run, nothing matches and the
    update is a no-op."""
    log = _resolve_logger(logger)
    from api.Modules.Batches.Models import ACHBatch
    from api.Modules.DailyBook.Models import MoneyTransferSummary
    from api.Modules.Tenancy.Models import Store
    from api.Modules.Transfers.Models import Transfer

    try:
        session.query(Transfer).filter_by(company="Maxi Transfer").update(
            {"company": "Maxi"}
        )
        session.query(ACHBatch).filter_by(company="Maxi Transfer").update(
            {"company": "Maxi"}
        )
        session.query(MoneyTransferSummary).filter_by(
            company="Maxi Transfer",
        ).update({"company": "Maxi"})
        # ``Store.companies`` is a comma-separated string — split,
        # replace, rejoin.
        for s in session.query(Store).filter(
            Store.companies.like("%Maxi Transfer%"),
        ).all():
            parts = [p.strip() for p in (s.companies or "").split(",") if p.strip()]
            setattr(s, "companies", ",".join(
                ["Maxi" if p == "Maxi Transfer" else p for p in parts],
            ))
        session.commit()
    except Exception as e:
        session.rollback()
        log.warning("Maxi Transfer rename backfill skipped: %s", e)


def migrate_legacy_line_item_tables(session: Session) -> int:
    """One-time, idempotent migration: copy legacy ``DailyDrop`` and
    ``CheckDeposit`` rows into ``DailyLineItem(kind='drop' |
    'check_deposit')``.

    Idempotency: for each legacy row, we look for a matching
    ``DailyLineItem`` (same store_id + report_date + kind +
    at_time + amount). If one exists we skip — a re-run inserts
    nothing new. The legacy tables themselves are NOT dropped;
    their rows stay intact as a safety net.

    Returns the number of rows inserted.
    """
    from api.Modules.DailyBook.Models import (
        CheckDeposit, DailyDrop, DailyLineItem,
    )

    inserted = 0
    try:
        legacy_drops = session.query(DailyDrop).all()
    except Exception:
        # Defensive — legacy tables may be already dropped from a
        # freshly-baselined DB.
        legacy_drops = []
    for dd in legacy_drops:
        existing = session.query(DailyLineItem).filter_by(
            store_id=dd.store_id, report_date=dd.report_date,
            kind="drop", at_time=dd.drop_time,
        ).filter(DailyLineItem.amount_cents == dd.amount_cents).first()
        if existing is None:
            session.add(DailyLineItem(
                store_id=dd.store_id, report_date=dd.report_date,
                kind="drop", at_time=dd.drop_time,
                amount=dd.amount, note=dd.note or "",
                created_by=dd.created_by,
                created_at=dd.created_at or utc_now(),
            ))
            inserted += 1
    try:
        legacy_checks = session.query(CheckDeposit).all()
    except Exception:
        legacy_checks = []
    for cd in legacy_checks:
        existing = session.query(DailyLineItem).filter_by(
            store_id=cd.store_id, report_date=cd.report_date,
            kind="check_deposit", at_time=cd.deposit_time,
        ).filter(DailyLineItem.amount_cents == cd.amount_cents).first()
        if existing is None:
            session.add(DailyLineItem(
                store_id=cd.store_id, report_date=cd.report_date,
                kind="check_deposit", at_time=cd.deposit_time,
                amount=cd.amount, note=cd.note or "",
                created_by=cd.created_by,
                created_at=cd.created_at or utc_now(),
            ))
            inserted += 1
    if inserted:
        session.commit()
    return inserted


__all__ = [
    "ADDED_INDEXES",
    "DEFAULT_FEATURE_FLAGS",
    "DROPPED_TABLES",
    "apply_schema",
    "drop_legacy_tables",
    "ensure_added_indexes",
    "migrate_legacy_line_item_tables",
    "rename_maxi_transfer_to_maxi",
    "seed_feature_flags",
]
