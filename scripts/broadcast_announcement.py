"""Resend an announcement email to every opted-in user.

Run from the Render shell after the superadmin creates an
announcement with the "Also email all users" checkbox set, or to
replay a broadcast that hit an SMTP outage on the first attempt::

    python -m scripts.broadcast_announcement <announcement_id>

Replaces the legacy ``flask broadcast-announcement <id>`` CLI.
Idempotent on ``Announcement.broadcast_sent_at`` — re-running on
an already-sent announcement is a no-op (returns 0).
"""
from __future__ import annotations

import argparse
import sys

from api.Core.Database import SessionLocal
from api.Core.Observability import init_logging, init_sentry
from api.Modules.Notifications.Services.broadcasts import run as broadcast


def _ensure_schema() -> None:
    """Mirror of ``scripts/purge_expired_stores._ensure_schema``."""
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Broadcast an announcement email to opted-in users.",
    )
    parser.add_argument(
        "announcement_id", type=int,
        help="DB id of the Announcement row to broadcast.",
    )
    args = parser.parse_args(argv)

    init_logging()
    init_sentry()
    _ensure_schema()

    with SessionLocal() as session:
        n = broadcast(session, args.announcement_id)
    print(f"Broadcast announcement {args.announcement_id}: {n} email(s) sent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
