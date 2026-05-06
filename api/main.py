"""FastAPI app factory + router mounting.

This is the entry point the Dockerized FastAPI image will boot from
once Flask is gone. During the strangler-fig migration, the legacy
Flask app continues to own / and the rest of the URL space; FastAPI
only handles routes under `settings.api_prefix` (default `/api/v2`).

Two ways this app gets exercised:

1. **Mounted inside Flask (current strangler-fig phase):** the Flask
   app uses `werkzeug.middleware.dispatcher.DispatcherMiddleware`
   to forward `/api/v2/*` requests into the FastAPI ASGI app via
   `a2wsgi.ASGIMiddleware`. The dispatcher strips the mount prefix
   before forwarding, so route paths inside FastAPI are RELATIVE —
   `/health`, not `/api/v2/health`. We set `root_path` on the
   FastAPI app so OpenAPI URLs reflect the mount point.

2. **Standalone (post-cleanup, or for direct uvicorn):** routes
   live at the same paths but the prefix lives in the request URL
   the client sends (since there's no dispatcher anymore).

Mixed routing rule: never put `/api/v2` in a FastAPI route
declaration. The mount or the OpenAPI `root_path` carry it.
"""
from fastapi import FastAPI

from api.Core.Config import settings


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


def create_app() -> FastAPI:
    """Build and return the FastAPI app.

    Doing this in a factory rather than a module-level singleton so
    tests can build fresh apps with overridden dependencies (e.g. an
    in-memory DB session) without polluting the production instance.
    """
    app = FastAPI(
        title="DineroBook API",
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
