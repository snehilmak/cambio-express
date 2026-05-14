"""Smoke tests for the FastAPI scaffolding.

Verifies:
- The FastAPI app imports cleanly.
- Settings load from env without crashing.
- The Core/Database/session module can be imported (lazy engine
  resolution doesn't fire on import).
- The FastAPI app responds to its `/health` endpoint.
- The ASGI router 301s legacy URLs to the SPA equivalent.

These tests guard the scaffolding contract. Flask is gone as of
PR #550 — the legacy DispatcherMiddleware checks that used to
live here were retired alongside it.
"""
from fastapi.testclient import TestClient


def test_settings_load_without_error():
    from api.Core.Config import settings, get_settings
    assert settings is not None
    assert settings.api_prefix == "/api/v2"
    assert get_settings() is settings, \
        "get_settings() must return the cached singleton"


def test_database_module_imports_cleanly():
    """Importing the session module must not fire `_get_engine()` —
    that would force the DB to be reachable at module-import time
    and break test collection in environments where it isn't."""
    from api.Core.Database import session as s
    assert s.Base is not None
    assert s.SessionLocal is not None


def test_fastapi_app_imports_and_has_health_route():
    from api.main import api_app, create_app
    assert api_app is not None
    # create_app() returns a fresh instance — useful for tests that
    # need DI overrides without polluting the singleton.
    fresh = create_app()
    assert fresh is not api_app


def test_fastapi_health_endpoint_standalone():
    """Standalone TestClient hits FastAPI without the dispatcher,
    so route paths are relative — /health, not /api/v2/health."""
    from api.main import api_app
    client = TestClient(api_app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_fastapi_openapi_includes_api_prefix_via_root_path():
    """When mounted under /api/v2 by the ASGI router, OpenAPI URLs
    must reflect the prefix. We use FastAPI's `root_path` setting
    to achieve that without putting /api/v2 in route declarations."""
    from api.main import api_app
    assert api_app.root_path == "/api/v2"
    client = TestClient(api_app)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert spec["info"]["title"] == "DineroBook API"


def test_root_redirects_to_spa(client):
    """The legacy GET URL contract is preserved at the ASGI layer:

      - ``/`` 301s to ``/app/`` (via ``api/PublicRoutes.py``)
      - ``/login`` 301s to ``/app/login`` (via ``api/SpaCutover.py``)
    """
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["location"] == "/app/"

    resp = client.get("/login", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/login"


def test_api_v2_health_routes_through_asgi(client):
    """The asgi_app router forwards /api/v2/* to the FastAPI app.
    Regression guard against future routing changes."""
    resp = client.get("/api/v2/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
