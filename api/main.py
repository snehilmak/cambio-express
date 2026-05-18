"""FastAPI app factory + router mounting.

This is the production entry point — ``asgi.py`` routes
``/api/v2/*`` here at the ASGI layer. Flask was retired in
PR #550; the historical strangler-fig dispatcher is gone.

Two ways this app gets exercised:

1. **Mounted by ``asgi.py``:** the top-level ASGI router strips
   the ``/api/v2`` prefix before forwarding, so route paths inside
   FastAPI are RELATIVE — ``/health``, not ``/api/v2/health``. We
   set ``root_path`` on the FastAPI app so OpenAPI URLs still
   reflect the mount point.

2. **Standalone (for direct uvicorn / tests):** routes live at the
   same paths but the prefix lives in the request URL the client
   sends.

Rule: never put ``/api/v2`` in a FastAPI route declaration. The
mount or the OpenAPI ``root_path`` carry it.
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.Core.Config import settings
from api.Core.Observability import (
    RequestIDMiddleware, init_logging, init_sentry,
)


def _register_routers(app: FastAPI) -> None:
    """Mount every module's APIRouter.

    Modules are imported lazily so a broken module doesn't block the
    whole app. Order doesn't matter — routers are pure mounts.
    """
    from api.Modules.Reports.Controllers import router as reports_router
    app.include_router(reports_router, prefix="/reports", tags=["reports"])

    from api.Modules.Customers.Controllers import router as customers_router
    app.include_router(customers_router, prefix="/customers", tags=["customers"])

    from api.Modules.Transfers.Controllers import router as transfers_router
    app.include_router(transfers_router, prefix="/transfers", tags=["transfers"])

    # BankSync mounted under /bank/* (matches the legacy URL space —
    # bank-sync, bank-rules, and per-account UI all share this prefix).
    from api.Modules.BankSync.Controllers import router as banksync_router
    app.include_router(banksync_router, prefix="/bank", tags=["bank"])

    from api.Modules.Auth.Controllers import router as auth_router
    app.include_router(auth_router, prefix="/auth", tags=["auth"])

    from api.Modules.DailyBook.Controllers import router as dailybook_router
    app.include_router(dailybook_router, prefix="/daily", tags=["daily"])

    from api.Modules.Batches.Controllers import router as batches_router
    app.include_router(batches_router, prefix="/batches", tags=["batches"])

    from api.Modules.Monthly.Controllers import router as monthly_router
    app.include_router(monthly_router, prefix="/monthly", tags=["monthly"])

    from api.Modules.Admin.Controllers import router as admin_router
    app.include_router(admin_router, prefix="/admin", tags=["admin"])

    from api.Modules.TimeClock.Controllers import (
        admin_router as timeclock_admin_router,
        router as timeclock_router,
    )
    app.include_router(
        timeclock_router, prefix="/timeclock", tags=["timeclock"],
    )
    # Admin-side payroll history mounted at /admin/timeclock so
    # the SPA + the sidebar nav both point to the same prefix
    # as the rest of the admin payroll surface.
    app.include_router(
        timeclock_admin_router, prefix="/admin", tags=["timeclock"],
    )

    from api.Modules.ReturnChecks.Controllers import (
        router as return_checks_router,
    )
    app.include_router(
        return_checks_router,
        prefix="/return-checks",
        tags=["return-checks"],
    )

    from api.Modules.Owners.Controllers import router as owners_router
    app.include_router(owners_router, prefix="/owner", tags=["owner"])

    from api.Modules.Superadmin.Controllers import (
        router as superadmin_router,
    )
    app.include_router(
        superadmin_router, prefix="/superadmin", tags=["superadmin"],
    )

    from api.Modules.Billing.Controllers import router as billing_router
    app.include_router(billing_router, prefix="/billing", tags=["billing"])

    from api.Modules.Announcements.Controllers import (
        router as announcements_router,
    )
    app.include_router(
        announcements_router, prefix="/announcements", tags=["announcements"],
    )

    from api.Modules.FeatureFlags.Controllers import (
        router as feature_flags_router,
    )
    app.include_router(
        feature_flags_router,
        prefix="/feature-flags",
        tags=["feature-flags"],
    )

    from api.Modules.TVDisplay.Controllers import (
        router as tv_display_router,
    )
    app.include_router(
        tv_display_router, prefix="/tv-display", tags=["tv-display"],
    )

    from api.Modules.Dashboard.Controllers import (
        router as dashboard_router,
    )
    app.include_router(
        dashboard_router, prefix="/dashboard", tags=["dashboard"],
    )

    # Webhooks reach FastAPI directly via asgi.py's /webhooks/*
    # forwarder (so existing provider URLs keep working without a
    # /api/v2 prefix), and are also reachable via /api/v2/webhooks/*.
    from api.Modules.Webhooks.Controllers import (
        router as webhooks_router,
    )
    app.include_router(
        webhooks_router, prefix="/webhooks", tags=["webhooks"],
    )


def create_app() -> FastAPI:
    """Build and return the FastAPI app.

    Doing this in a factory rather than a module-level singleton so
    tests can build fresh apps with overridden dependencies (e.g. an
    in-memory DB session) without polluting the production instance.
    """
    init_logging()
    init_sentry()

    @asynccontextmanager
    async def _lifespan(_app: FastAPI):
        """Boot-time DB init runs once at uvicorn startup.

        ``api.Core.Boot.init_db`` is idempotent — Alembic upgrade +
        index safety-net + legacy backfills + seed data.
        """
        if not os.environ.get("DINEROBOOK_SKIP_INIT_DB"):
            from api.Core.Boot import init_db
            init_db()
        yield

    app = FastAPI(
        title="DineroBook API",
        lifespan=_lifespan,
        version="2.0.0",
        description="DineroBook FastAPI backend.",
        # `root_path` tells FastAPI it's mounted under this prefix
        # (set by asgi.py), so generated OpenAPI URLs include
        # /api/v2 even though our route declarations don't.
        root_path=settings.api_prefix,
        # OpenAPI docs at /api/v2/docs and /api/v2/redoc — the
        # docs_url here is RELATIVE to the route base; root_path
        # makes the rendered links absolute.
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(RequestIDMiddleware)

    # Rate limiting (BACKLOG D6). slowapi reads its storage backend
    # from RATELIMIT_STORAGE_URI (Redis in prod, in-memory in dev/CI).
    # The module-level singleton lives in api/Core/RateLimit.py so
    # per-route decorators in controllers can import it without
    # depending on this factory's lifecycle.
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from starlette.responses import JSONResponse

    from api.Core.RateLimit import limiter as slow_limiter

    app.state.limiter = slow_limiter
    app.add_middleware(SlowAPIMiddleware)

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limit_handler(request, exc):
        """Per-route 429 envelope. Keeps body shape consistent
        with the FastAPI default (`detail`) so the SPA's existing
        `api()` wrapper renders it as the standard error message."""
        return JSONResponse(
            status_code=429,
            content={
                "detail": (
                    "Too many requests — try again in a moment."
                ),
                "limit": str(exc.detail) if hasattr(exc, "detail") else "",
            },
        )

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        """Tiny liveness probe — 200 + JSON envelope so the load
        balancer can confirm the app is reachable."""
        return {"status": "ok", "version": app.version}

    _register_routers(app)
    return app


# Module-level instance for `uvicorn api.main:api_app` (used by the
# `asgi.py` top-level router).
api_app = create_app()
