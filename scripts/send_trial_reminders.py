"""Mail trial-ending reminders to every eligible recipient.

Run daily from the Render cron service::

    python -m scripts.send_trial_reminders

Replaces the legacy ``flask send-trial-reminders`` CLI. The
behaviour is identical (same Service entry point — ``api.Modules.
Notifications.Services.trial_reminders.run``); the difference is
that this entrypoint never imports ``app.py`` and therefore doesn't
boot Flask + FastAPI + observability + ``init_db``. Cron startup is
correspondingly cheaper.

Idempotent — re-running on a quiet day is a no-op because the
underlying Service stamps ``Store.trial_reminder_sent_at`` and skips
stores whose flag is already set.
"""
from __future__ import annotations

import sys

from api.Core.Database import SessionLocal
from api.Core.Observability import init_logging, init_sentry
from api.Modules.Notifications.Services.trial_reminders import run as send_trial_reminders


def _ensure_schema() -> None:
    """Run ``alembic upgrade head`` against the configured DB.

    Mirrors ``scripts/purge_expired_stores.py`` — see that file for
    the rationale. In prod this is a no-op because the web service
    already upgraded the schema at boot; for local dev it lets the
    script work against an empty in-memory SQLite.
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
        has_alembic = "alembic_version" in table_names
        has_app_tables = bool(table_names - {"alembic_version"})
        if not has_alembic and has_app_tables:
            command.stamp(cfg, "head")
        else:
            command.upgrade(cfg, "head")


def main() -> int:
    """Open a session, run the trial-reminder fanout, print + exit."""
    init_logging()
    init_sentry()
    _ensure_schema()

    with SessionLocal() as session:
        n = send_trial_reminders(session)
    print(f"Sent {n} trial reminder email(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
