"""Boot-time initialisation: DB schema + FastAPI mount.

Both helpers are called from app.py, but the implementation lives
here so the Flask file isn't dominated by orchestration code.
"""
from __future__ import annotations

import os


def init_db(app, db) -> None:
    """Run the boot-time DB initialisation. Idempotent on every boot.
    Alembic upgrade + index safety-net + legacy drops + line-item
    migration + feature-flag seed + TV catalog seed + superadmin seed."""
    from api.Core.Bootstrap import (
        apply_schema as _bs_apply_schema,
        drop_legacy_tables as _bs_drop_legacy,
        ensure_added_indexes as _bs_ensure_indexes,
        migrate_legacy_line_item_tables as _bs_migrate_line_items,
        rename_maxi_transfer_to_maxi as _bs_rename_maxi,
        seed_feature_flags as _bs_seed_flags,
    )
    from api.Modules.Tenancy.Models import User

    with app.app_context():
        _bs_apply_schema(db.engine, app.logger)
        _bs_ensure_indexes(db.engine, app.logger)
        _bs_drop_legacy(db.engine, app.logger)
        _bs_rename_maxi(db.session, app.logger)
        try:
            _bs_migrate_line_items(db.session)
        except Exception as e:
            app.logger.warning(f"Legacy line-item migration skipped: {e}")
        _bs_seed_flags(db.session)
        try:
            from api.Modules.TVDisplay.Services.seed import run as _seed_tv
            n_imported = _seed_tv(db.session, app.root_path)
            if n_imported:
                app.logger.info(f"Imported {n_imported} TV logos from static/seed-logos/.")
        except Exception as e:
            app.logger.warning(f"TV catalog seed skipped: {e}")
        if not db.session.query(User).filter_by(username="superadmin", store_id=None).first():
            sa = User(username="superadmin", full_name="Platform Owner",
                      role="superadmin", store_id=None)
            sa.set_password(os.environ.get("SUPERADMIN_PASSWORD", "super2025!"))
            db.session.add(sa)
            db.session.commit()
            print("✅ Superadmin: superadmin / super2025!")


def mount_fastapi(app) -> None:
    """Mount /api/v2 and /app onto Flask's wsgi_app so Flask's
    test_client can reach them. Production routes via asgi.py and
    bypasses this entirely; conftest.py swaps the ASGIMiddleware
    wrappers for TestClient-backed bridges to avoid the a2wsgi
    leaked-task pathology under coverage."""
    try:
        from a2wsgi import ASGIMiddleware
        from werkzeug.middleware.dispatcher import DispatcherMiddleware

        from api.main import api_app as _fastapi_app
        from api.spa import spa_app as _spa_app

        app.wsgi_app = DispatcherMiddleware(
            app.wsgi_app,
            {
                "/api/v2": ASGIMiddleware(_fastapi_app),
                "/app":    ASGIMiddleware(_spa_app),
            },
        )
        app.logger.info(
            "FastAPI mounted at /api/v2 + SPA at /app (strangler-fig)"
        )
    except Exception as _err:
        app.logger.warning(f"FastAPI mount skipped: {_err}")
