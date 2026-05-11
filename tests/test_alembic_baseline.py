"""Guarantee the Alembic baseline stays in sync with ``db.metadata``.

The baseline migration (``alembic/versions/*baseline*.py``) must
produce the same schema as ``db.create_all()`` does, otherwise a
fresh-install deploy via Alembic will land on a different schema
than every existing dev / test boot that uses
``db.create_all()`` + ``_ensure_added_columns``.

This test exercises the migration end-to-end against a temporary
SQLite DB and asserts table + column parity. When you add a new
``db.Model`` (or extend ``_ADDED_COLUMNS``), regenerate the baseline
or add a follow-up Alembic revision; this test will fail until you
do.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = REPO_ROOT / "alembic.ini"


def _table_columns(db_path: str) -> dict[str, set[tuple[str, str]]]:
    """Return ``{table_name: {(col_name, col_type), ...}}`` for every
    user table in the SQLite DB, excluding Alembic's own bookkeeping
    table and SQLite internal tables."""
    conn = sqlite3.connect(db_path)
    try:
        tables = [
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version' "
                "ORDER BY name",
            )
        ]
        return {
            t: {(r[1], r[2]) for r in conn.execute(f"PRAGMA table_info({t})")}
            for t in tables
        }
    finally:
        conn.close()


def _run_alembic_upgrade(db_path: str) -> None:
    """Subprocess out so we don't pollute the running test's app
    import state (Alembic's env.py does its own ``from app import db``
    that we don't want overwriting fixtures)."""
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{db_path}",
        "SECRET_KEY": "test",
        "STRIPE_SECRET_KEY": "sk_test",
        "STRIPE_BASIC_PRICE_ID": "p",
        "STRIPE_PRO_PRICE_ID": "p",
        "STRIPE_WEBHOOK_SECRET": "ws",
        "DINEROBOOK_SKIP_INIT_DB": "1",
    }
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI),
         "upgrade", "head"],
        cwd=REPO_ROOT, env=env, check=True, capture_output=True,
    )


def _run_db_create_all(db_path: str) -> None:
    """Subprocess a fresh Python that imports app (which calls
    ``init_db`` → ``db.create_all`` + ``_ensure_added_columns`` +
    ``_ensure_added_indexes``). Matches what every production boot
    does today."""
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{db_path}",
        "SECRET_KEY": "test",
        "STRIPE_SECRET_KEY": "sk_test",
        "STRIPE_BASIC_PRICE_ID": "p",
        "STRIPE_PRO_PRICE_ID": "p",
        "STRIPE_WEBHOOK_SECRET": "ws",
    }
    subprocess.run(
        [sys.executable, "-c", "import app"],
        cwd=REPO_ROOT, env=env, check=True, capture_output=True,
    )


@pytest.fixture
def fresh_dbs(tmp_path):
    """Two empty SQLite files, one for Alembic, one for
    ``db.create_all``. Both are populated, then compared."""
    alembic_db = tmp_path / "alembic.db"
    create_all_db = tmp_path / "create_all.db"
    yield str(alembic_db), str(create_all_db)


def test_alembic_baseline_produces_same_tables_as_create_all(fresh_dbs):
    """The two boot paths must converge on the same set of tables.
    A mismatch means the baseline migration is stale relative to
    new ``db.Model`` declarations.
    """
    alembic_db, create_all_db = fresh_dbs
    _run_alembic_upgrade(alembic_db)
    _run_db_create_all(create_all_db)

    alembic_tables = set(_table_columns(alembic_db))
    create_all_tables = set(_table_columns(create_all_db))

    only_alembic = alembic_tables - create_all_tables
    only_create_all = create_all_tables - alembic_tables
    assert not only_alembic, (
        f"Alembic baseline declares tables not in db.metadata: "
        f"{only_alembic}"
    )
    assert not only_create_all, (
        f"db.metadata has tables missing from the Alembic baseline: "
        f"{only_create_all}\n"
        f"Generate a follow-up revision with: "
        f"alembic revision --autogenerate -m 'add <table>'"
    )


def test_alembic_baseline_produces_same_columns_as_create_all(fresh_dbs):
    """Per-table column parity. Catches missing ``_ADDED_COLUMNS``
    entries that haven't been ported to a new Alembic revision.
    """
    alembic_db, create_all_db = fresh_dbs
    _run_alembic_upgrade(alembic_db)
    _run_db_create_all(create_all_db)

    a = _table_columns(alembic_db)
    b = _table_columns(create_all_db)
    mismatches = {}
    for t in sorted(set(a) | set(b)):
        only_a = a.get(t, set()) - b.get(t, set())
        only_b = b.get(t, set()) - a.get(t, set())
        if only_a or only_b:
            mismatches[t] = {
                "in_alembic_only": only_a,
                "in_create_all_only": only_b,
            }
    assert not mismatches, (
        "Alembic baseline column-set drift detected. Regenerate a "
        "follow-up revision with: "
        "`alembic revision --autogenerate -m 'sync schema'`. Drift:\n"
        f"{mismatches}"
    )


def test_alembic_skip_init_db_gate_works():
    """``DINEROBOOK_SKIP_INIT_DB=1`` must skip ``init_db()`` on
    import. Otherwise Alembic's env.py would trigger
    ``db.create_all`` on the file it's about to migrate, yielding an
    empty baseline.
    """
    env = {
        **os.environ,
        "DATABASE_URL": "sqlite:///:memory:",
        "SECRET_KEY": "test",
        "STRIPE_SECRET_KEY": "sk_test",
        "STRIPE_BASIC_PRICE_ID": "p",
        "STRIPE_PRO_PRICE_ID": "p",
        "STRIPE_WEBHOOK_SECRET": "ws",
        "DINEROBOOK_SKIP_INIT_DB": "1",
    }
    result = subprocess.run(
        [sys.executable, "-c",
         "import app; "
         "from app import db; "
         "print('OK' if len(db.metadata.tables) > 0 else 'EMPTY')"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    # Metadata still populated (models registered via class-definition
    # side effects) but init_db itself didn't run — confirmed by the
    # absence of the "Superadmin: superadmin / super2025!" print.
    assert "Superadmin:" not in result.stdout
    assert "OK" in result.stdout
