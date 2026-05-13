"""Hard-delete inactive stores past their data_retention_until.

Render's cron service runs this daily at 03:15 UTC (see
``render.yaml``). Idempotent — re-running on a quiet day is a no-op.

Invocation::

    python -m scripts.purge_expired_stores

Replaces the legacy ``flask purge-expired-stores`` CLI. The behaviour
is identical (calls the same ``api.Modules.Billing.Services.
purge_expired_stores(session)`` Service); the difference is that
this entrypoint never imports ``app.py`` and therefore doesn't boot
Flask + FastAPI + observability + init_db. Cron startup is
correspondingly cheaper.
"""
from __future__ import annotations

import sys

from api.Core.Database import SessionLocal
from api.Core.Observability import init_logging, init_sentry
# Import the leaf module directly rather than going through
# ``api.Modules.Billing.Services.__init__`` — that package's eager
# imports pull in the Stripe-checkout chain (and transitively
# ``app.py``), defeating the standalone-script goal.
from api.Modules.Billing.Services.retention import purge_expired_stores


def _ensure_schema() -> None:
    """Run ``alembic upgrade head`` against the configured DB.

    In production this is a no-op because the web service already
    upgraded the schema at boot. We still call it so:

      - the cron service can start up against a freshly-provisioned
        DB without depending on web-service order
      - local dev runs against an in-memory SQLite work for ad-hoc
        testing

    Mirrors ``_apply_schema()`` in ``app.py``; uses ``begin()`` so
    Alembic's transaction commits when the block exits.
    """
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    from api.Core.Database.session import _get_engine

    engine = _get_engine()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", str(engine.url))
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        table_names = set(inspect(connection).get_table_names())
        has_alembic_table = "alembic_version" in table_names
        has_app_tables = bool(table_names - {"alembic_version"})
        if not has_alembic_table and has_app_tables:
            # Pre-Alembic DB (legacy db.create_all era) — stamp head
            # without running migrations.
            command.stamp(cfg, "head")
        else:
            command.upgrade(cfg, "head")


def main() -> int:
    """Open a session, run the purge, print + exit."""
    # Structured logging on stdout + Sentry tagging (matches the
    # web service). Both no-op without their env vars set, so
    # local dev runs are quiet.
    init_logging()
    init_sentry()
    _ensure_schema()

    with SessionLocal() as session:
        n = purge_expired_stores(session)
    print(f"Purged {n} expired store(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
