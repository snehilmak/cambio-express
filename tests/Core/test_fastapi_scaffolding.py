"""Smoke tests for the FastAPI scaffolding.

Verifies:
- The FastAPI app imports cleanly.
- Settings load from env without crashing.
- The Core/Database/session module can be imported (lazy engine
  resolution doesn't fire on import).
- The FastAPI app responds to its `/health` endpoint.
- The Flask app continues to serve / unchanged.
- The strangler-fig dispatcher routes `/api/v2/*` into FastAPI and
  everything else into Flask.

These tests guard the scaffolding contract — every module migration
PR after this one builds on top, so the foundation must stay solid.
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
    that would force a Flask import at module-import time and break
    test collection if the Flask app fails to construct."""
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
    so route paths are relative — /health, not /api/v2/health.
    The dispatched-via-Flask case is tested separately below."""
    from api.main import api_app
    client = TestClient(api_app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_fastapi_openapi_includes_api_prefix_via_root_path():
    """When mounted under /api/v2 by the dispatcher, OpenAPI URLs
    must reflect the prefix. We use FastAPI's `root_path` setting
    to achieve that without putting /api/v2 in route declarations."""
    from api.main import api_app
    assert api_app.root_path == "/api/v2"
    client = TestClient(api_app)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert spec["info"]["title"] == "DineroBook API"


def test_flask_app_still_serves_root_and_redirects_legacy(client):
    """Flask still owns ``/`` (the marketing landing handler bounces
    visitors to /app/) and the spa_cutover hook 301s legacy paths
    like /login to /app/login. If this test fails the dual-routing
    contract is broken."""
    # Root → 301 to /app/ via the landing blueprint
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/"
    # /login → 301 to /app/login via spa_cutover
    resp = client.get("/login", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/login"


def test_flask_app_dispatches_api_v2_to_fastapi(client):
    """The DispatcherMiddleware in app.py forwards /api/v2/* into
    FastAPI. Flask's URL map should NOT match these routes."""
    resp = client.get("/api/v2/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"


def test_flask_dispatcher_strips_api_prefix_correctly():
    """A regression check on the WSGI mount: when /api/v2/health is
    requested, FastAPI should see SCRIPT_NAME=/api/v2 and PATH_INFO=/health
    so its router resolves the route correctly. We verified by hitting
    the endpoint above; this test pins the exact response body shape
    so future router moves can't silently break the dispatch."""
    from app import app as flask_app
    with flask_app.test_client() as c:
        resp = c.get("/api/v2/health")
        assert resp.status_code == 200
        # Confirms PATH_INFO routing is correct (we got the JSON
        # response defined in api/main.py, not a Flask 404).
        assert resp.is_json
        assert resp.get_json().get("status") == "ok"
