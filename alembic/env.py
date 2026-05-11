"""Alembic environment configuration.

Reads ``DATABASE_URL`` from the environment (Postgres in prod, SQLite
elsewhere) and points autogenerate at the SQLAlchemy metadata
registered by ``app.py``. Importing ``app`` is heavy — it runs the
full Flask module-level init — but Alembic only loads this file at
migration time (never inside the request path), so the boot cost is
fine.

The legacy ``_ADDED_COLUMNS`` / ``_ensure_added_columns`` boot
mechanism in ``app.py`` is still the production migration path for
now. Alembic is being introduced in stages (per
docs/architecture/ADR-004-alembic-adoption.md):

  1. Baseline migration added (this PR) but NOT auto-run on boot.
  2. Production gets ``alembic stamp head`` once, marking the
     baseline as applied without running any DDL.
  3. ``preDeploy: alembic upgrade head`` is wired into render.yaml.
  4. ``_ADDED_COLUMNS`` is retired in a follow-up PR.

Until step 4 lands, both mechanisms coexist. They don't conflict —
Alembic only runs when invoked explicitly; ``db.create_all()`` +
``_ensure_added_columns`` continue to run on every app boot.
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context


# Alembic Config object — provides access to alembic.ini values.
config = context.config

# Override the alembic.ini sqlalchemy.url with the env var so dev,
# CI, and prod all pick up the same URL the Flask app uses. The
# alembic.ini default is a dummy placeholder.
_db_url = os.environ.get("DATABASE_URL")
if _db_url:
    config.set_main_option("sqlalchemy.url", _db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# Import the Flask app to register every SQLAlchemy model on
# db.metadata. We pull the metadata from the SQLAlchemy instance
# (``app.db.metadata``) which is what autogenerate diffs against.
#
# Setting ``DINEROBOOK_SKIP_INIT_DB`` BEFORE the import skips the
# boot-time ``db.create_all()`` + ``_ensure_added_columns`` work —
# otherwise that runs against the same DB Alembic is about to diff,
# producing an empty migration. Models still register on
# ``db.metadata`` via class-definition side effects regardless.
os.environ.setdefault("DINEROBOOK_SKIP_INIT_DB", "1")
from app import db  # noqa: E402  (intentional late import)

target_metadata = db.metadata


def run_migrations_offline() -> None:
    """Generate SQL without a DB connection.

    Used for ``alembic upgrade --sql``. We rarely need this, but the
    Alembic CLI expects both modes to be defined.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection.

    This is the normal path — ``alembic upgrade head`` from the
    deploy hook (once wired) or a CLI invocation lands here.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Render batch mode for SQLite. Postgres ignores this; on
            # SQLite, ALTER TABLE is limited so Alembic falls back to
            # create-new-table-and-copy when needed.
            render_as_batch=connection.dialect.name == "sqlite",
            # Catch identifier-only changes (e.g. server_default
            # tweaks) so autogenerate produces accurate diffs.
            compare_server_default=True,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
