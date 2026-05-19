"""Mail per-store missed-shift digests to opted-in admins / owners.

Run nightly from the Render cron service::

    python -m scripts.send_missed_shift_digest
    python -m scripts.send_missed_shift_digest --date 2026-05-18

Defaults to yesterday (UTC) when ``--date`` is omitted — the typical
cron use case is 02:30 UTC, after the daily-summary cron has run.
Pass ``--date YYYY-MM-DD`` to backfill a specific day.

Idempotent — re-running on a quiet day or on a day already mailed
is a no-op because ``Notifications.Services.missed_shifts.run`` reads
``Store.missed_shifts_sent_for`` and skips stores already stamped
for the target date.

Pairs with ``scripts/send_daily_summaries`` — both feed the same
audience (admins + linked owners) but the digest only fires on
stores that actually had a planned shift go un-punched.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

from api.Core.Database import SessionLocal
from api.Core.Observability import init_logging, init_sentry
from api.Modules.Notifications.Services.missed_shifts import (
    run as send_missed_shift_digests,
)


def _ensure_schema() -> None:
    """Mirror of ``scripts/send_daily_summaries._ensure_schema``."""
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
        description=(
            "Send the missed-shift digest to opted-in admins / owners "
            "for every store with at least one planned shift that had "
            "no clock-in on the target date."
        ),
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help=(
            "Target date in YYYY-MM-DD form. Defaults to yesterday (UTC)."
        ),
    )
    args = parser.parse_args(argv)

    init_logging()
    init_sentry()
    _ensure_schema()

    on_date: date | None = None
    if args.date:
        try:
            on_date = date.fromisoformat(args.date)
        except ValueError:
            print(
                f"Bad --date={args.date!r}: expected YYYY-MM-DD.",
                file=sys.stderr,
            )
            return 2

    with SessionLocal() as session:
        n = send_missed_shift_digests(session, on_date=on_date)
    label = on_date.isoformat() if on_date else "yesterday"
    print(f"Sent {n} missed-shift digest email(s) for {label}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
