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
    whole app. As modules migrate, add their import + include_router
    here. Order doesn't matter — routers are pure mounts.

    During the strangler-fig migration this list grows by one module
    per PR (Reports → Customers → Transfers → BankSync → Auth/Billing
    → DailyBook). Once the list is complete, Flask is removed.
    """
    # Reports — first module to migrate. Controllers are wired as of
    # PR 4 (all four layers — Models, Repositories, Services,
    # Controllers — now present).
    from api.Modules.Reports.Controllers import router as reports_router
    app.include_router(reports_router, prefix="/reports", tags=["reports"])

    # Customers — second module to migrate. Wired as of PR 8.
    from api.Modules.Customers.Controllers import router as customers_router
    app.include_router(customers_router, prefix="/customers", tags=["customers"])

    # Transfers — third module. Read-side wired as of PR 12.
    from api.Modules.Transfers.Controllers import router as transfers_router
    app.include_router(transfers_router, prefix="/transfers", tags=["transfers"])

    # BankSync — fourth module. Read-side wired as of PR 16. Listed
    # under /bank/* because the legacy routes namespace bank-sync,
    # bank-rules, and per-account UI under /bank/.
    from api.Modules.BankSync.Controllers import router as banksync_router
    app.include_router(banksync_router, prefix="/bank", tags=["bank"])

    # Auth — fifth module. Login + JWT verification wired as of PR 20.
    # The full Auth migration (TOTP, passkey, refresh tokens) ships
    # in subsequent PRs; this PR adds password-flow + Bearer dep.
    from api.Modules.Auth.Controllers import router as auth_router
    app.include_router(auth_router, prefix="/auth", tags=["auth"])

    # DailyBook — sixth and final module. Read-side wired as of PR 23;
    # write-side (create/edit/lock + line-item CRUD) ships in
    # subsequent PRs. This completes the FastAPI router lineup —
    # cleanup PR will then remove Flask.
    from api.Modules.DailyBook.Controllers import router as dailybook_router
    app.include_router(dailybook_router, prefix="/daily", tags=["daily"])

    # Batches — ACH batch read-side, added during the SPA
    # cutover migration. Write-side (create/edit/link transfers)
    # still on Flask until subsequent PRs.
    from api.Modules.Batches.Controllers import router as batches_router
    app.include_router(batches_router, prefix="/batches", tags=["batches"])

    # Monthly — per-store, per-month P&L read-side. Write-side
    # (the auto-derived bank-charges + line-item totals plus
    # operator-editable fields) stays on Flask until subsequent
    # PRs.
    from api.Modules.Monthly.Controllers import router as monthly_router
    app.include_router(monthly_router, prefix="/monthly", tags=["monthly"])

    # Admin — store-info / team / owner-access endpoints for
    # the SPA's settings page. Mirrors the legacy
    # /admin/settings tabbed page in scope.
    from api.Modules.Admin.Controllers import router as admin_router
    app.include_router(admin_router, prefix="/admin", tags=["admin"])

    # ReturnChecks — bounced-check workflow (list / detail /
    # status transitions). Per-payment write endpoints ship in
    # a follow-up PR.
    from api.Modules.ReturnChecks.Controllers import (
        router as return_checks_router,
    )
    app.include_router(
        return_checks_router,
        prefix="/return-checks",
        tags=["return-checks"],
    )

    # Owners — multi-store owner umbrella read-side. First slice
    # ships /owner/locations; dashboard, P&L rollup, store drill-
    # down, and connect/unlink invitation flow follow.
    from api.Modules.Owners.Controllers import router as owners_router
    app.include_router(owners_router, prefix="/owner", tags=["owner"])

    # Superadmin — platform-wide read-side. First slice ships the
    # stores list; controls, anomalies, audit log, announcements,
    # feature flags, and impersonation come in subsequent PRs.
    from api.Modules.Superadmin.Controllers import (
        router as superadmin_router,
    )
    app.include_router(
        superadmin_router, prefix="/superadmin", tags=["superadmin"],
    )

    # Billing — Stripe Checkout Session + Billing Portal Session
    # mints. The webhook (`/webhooks/stripe`) is what flips a store
    # onto a new plan; these endpoints only initiate the redirect.
    from api.Modules.Billing.Controllers import router as billing_router
    app.include_router(billing_router, prefix="/billing", tags=["billing"])

    # Announcements — global banner CRUD for the superadmin. The
    # read-side `active_announcements()` is consumed everywhere
    # via the Service helper; this Controller exposes the admin
    # CRUD surface to the SPA.
    from api.Modules.Announcements.Controllers import (
        router as announcements_router,
    )
    app.include_router(
        announcements_router, prefix="/announcements", tags=["announcements"],
    )

    # FeatureFlags — superadmin CRUD over the platform-wide flag
    # registry. Per-store overrides ship in a follow-up.
    from api.Modules.FeatureFlags.Controllers import (
        router as feature_flags_router,
    )
    app.include_router(
        feature_flags_router,
        prefix="/feature-flags",
        tags=["feature-flags"],
    )

    # TVDisplay — read-only first slice for the rate-board admin
    # landing (display config + countries + active pairing summary).
    # Write-side (mint countries, edit rates, pair Fire TVs) stays
    # on legacy Flask until the WSGI bridge retires.
    from api.Modules.TVDisplay.Controllers import (
        router as tv_display_router,
    )
    app.include_router(
        tv_display_router, prefix="/tv-display", tags=["tv-display"],
    )

    # Dashboard — role-shaped landing payload for /app/dashboard.
    # No new aggregation logic; reads from the same models the
    # legacy /dashboard view used and delegates the superadmin
    # branch to the existing platform-BI service.
    from api.Modules.Dashboard.Controllers import (
        router as dashboard_router,
    )
    app.include_router(
        dashboard_router, prefix="/dashboard", tags=["dashboard"],
    )

    # Webhooks — Stripe + Resend delivery-event receivers. Routes
    # mount at /webhooks/stripe and /webhooks/resend so the existing
    # provider URLs keep working through the asgi.py routing
    # (which forwards /webhooks/* directly to FastAPI). They're
    # ALSO reachable at /api/v2/webhooks/* via the dispatcher.
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
        index safety-net + legacy backfills + seed data. PR #550
        moved this off the legacy ``app.init_db()`` orchestrator
        when Flask was retired.
        """
        if not os.environ.get("DINEROBOOK_SKIP_INIT_DB"):
            from api.Core.Boot import init_db
            init_db()
        yield

    app = FastAPI(
        title="DineroBook API",
        lifespan=_lifespan,
        version="2.0.0-alpha",  # alpha until cleanup PR removes Flask
        description=(
            "Customer-deployable FastAPI backend, currently being "
            "migrated module-by-module from the legacy Flask "
            "monolith. See docs/architecture/MIGRATION_ADR.md."
        ),
        # `root_path` tells FastAPI it's mounted under this prefix
        # (set by the dispatcher), so generated OpenAPI URLs include
        # /api/v2 even though our route declarations don't.
        root_path=settings.api_prefix,
        # OpenAPI docs at /api/v2/docs and /api/v2/redoc — the
        # docs_url here is RELATIVE to the route base (i.e. inside
        # FastAPI's view: /docs); the dispatcher prepends /api/v2
        # at request time and root_path makes the rendered links
        # absolute.
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(RequestIDMiddleware)

    # Rate limiting (BACKLOG D6). slowapi shares Flask-Limiter's
    # `limits` library — same Redis backend when one is configured.
    # In dev / CI we fall back to in-memory like the Flask side.
    # See app.py "_apply_rate_limits" for the Flask twin; tunings
    # match. The module-level singleton lives in
    # api/Core/RateLimit.py so per-route decorators in controllers
    # can import it without depending on this factory's lifecycle.
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
        """Tiny liveness probe. Returns 200 + a JSON envelope so a
        load balancer can confirm the FastAPI app is reachable
        independent of the Flask app's health."""
        return {"status": "ok", "version": app.version}

    _register_routers(app)
    return app


# Module-level instance for `uvicorn api.main:api_app` and for the
# Flask DispatcherMiddleware mount in app.py.
api_app = create_app()
