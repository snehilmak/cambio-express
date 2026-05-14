"""Boot-time initialisation for production + tests.

Single source of truth for "what needs to happen before the first
HTTP request is served": Alembic upgrade, index safety-net,
legacy backfills, seed data. Replaces ``api/Flask/Init.py``'s
``init_db()`` orchestrator, which was bound to the Flask app
context. This module takes the shared engine + ``SessionLocal``
from ``api.Core.Database`` directly — no Flask required.

Called from two places:

* ``api.main.create_app()``'s lifespan hook — production. Runs
  once at uvicorn startup, before the first request lands.
* ``tests/conftest.py`` — runs once at test-session start, then
  again before every test via the ``clean_db`` fixture (which
  drops + recreates the schema, then re-seeds).

Idempotent — safe on every boot.
"""
from __future__ import annotations

import logging
import os
from typing import Optional


def warn_default_seed_passwords(
    logger: Optional[logging.Logger] = None,
) -> None:
    """Loud structured-log warning when prod boots with the default
    seed passwords (super2025! / cambio2025!) still in effect."""
    if not os.environ.get("APP_BASE_URL", "").startswith("https://"):
        return
    log = logger or logging.getLogger("dinerobook")
    missing = []
    if not os.environ.get("SUPERADMIN_PASSWORD"):
        missing.append("SUPERADMIN_PASSWORD")
    if not os.environ.get("ADMIN_PASSWORD"):
        missing.append("ADMIN_PASSWORD")
    if missing:
        log.critical(
            "Seed password fallback is active in prod for: "
            "%s. The default values (super2025! / cambio2025!) "
            "are public in the repo. Either set the env vars OR "
            "change the password in the UI immediately on first login.",
            ", ".join(missing),
        )


def init_db(logger: Optional[logging.Logger] = None) -> None:
    """Run the boot-time DB initialisation.

    Schema upgrade + indexes + legacy backfills + feature-flag seed +
    TV catalog seed + superadmin seed. Idempotent — re-running on an
    already-initialised DB is a no-op.
    """
    log = logger or logging.getLogger("dinerobook")
    warn_default_seed_passwords(log)

    from api.Core.Bootstrap import (
        apply_schema, drop_legacy_tables, ensure_added_indexes,
        migrate_legacy_line_item_tables, rename_maxi_transfer_to_maxi,
        seed_feature_flags,
    )
    from api.Core.Database import SessionLocal, engine
    from api.Modules.Tenancy.Models import User

    apply_schema(engine, log)
    ensure_added_indexes(engine, log)
    drop_legacy_tables(engine, log)

    with SessionLocal() as session:
        rename_maxi_transfer_to_maxi(session, log)
        try:
            migrate_legacy_line_item_tables(session)
        except Exception as e:
            log.warning(f"Legacy line-item migration skipped: {e}")
        seed_feature_flags(session)

        try:
            from api.Modules.TVDisplay.Services.seed import run as seed_tv
            # The legacy ``app.root_path`` argument is the repo root —
            # one level up from ``api/``.
            import os.path
            repo_root = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            n_imported = seed_tv(session, repo_root)
            if n_imported:
                log.info(
                    f"Imported {n_imported} TV logos from static/seed-logos/.",
                )
        except Exception as e:
            log.warning(f"TV catalog seed skipped: {e}")

        existing = (
            session.query(User)
            .filter_by(username="superadmin", store_id=None)
            .first()
        )
        if not existing:
            sa = User(
                username="superadmin", full_name="Platform Owner",
                role="superadmin", store_id=None,
            )
            sa.set_password(
                os.environ.get("SUPERADMIN_PASSWORD", "super2025!"),
            )
            session.add(sa)
            session.commit()
            print("✅ Superadmin: superadmin / super2025!")
