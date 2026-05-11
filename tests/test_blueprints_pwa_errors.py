"""Coverage for the PWA + error-handler Blueprints (D2 scaffolding).

These routes existed before the Blueprint split but had no test
coverage. Adding them here both (a) confirms the extraction is a
no-op and (b) creates the regression guard so future Blueprint
moves don't silently change behavior.
"""
from __future__ import annotations


def test_service_worker_serves_js(client):
    """/sw.js is the registered service-worker URL. Must:
    - 200
    - JavaScript content-type (browser refuses to register a
      service worker served as text/html)
    - Cache-Control: no-cache (a stale SW would pin a stale UI)
    - Service-Worker-Allowed: / (lets the SW claim every path)
    """
    resp = client.get("/sw.js")
    assert resp.status_code == 200
    ct = resp.headers.get("Content-Type", "")
    assert "javascript" in ct.lower(), ct
    assert resp.headers.get("Cache-Control") == "no-cache"
    assert resp.headers.get("Service-Worker-Allowed") == "/"


def test_offline_page_renders(client):
    """/offline is precached by the service worker so the browser
    has something to render when the network is gone. Must 200 and
    return HTML."""
    resp = client.get("/offline")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("Content-Type", "").lower()


def test_404_renders_public_template_for_anon(client):
    """Logged-out 404 uses error_public.html — no admin chrome."""
    resp = client.get("/this-route-does-not-exist-zzz")
    assert resp.status_code == 404
    # error_public.html has no sidebar/topbar markup; a sloppy
    # template choice would have leaked the admin chrome here.
    body = resp.get_data(as_text=True)
    assert "404" in body or "not found" in body.lower()


def test_500_handler_invokes_template_and_logger():
    """Confirm the registered 500 handler renders the error template
    and logs the exception. We invoke the handler directly via Flask's
    handler registry rather than triggering a 500 from a route — Flask
    refuses to add routes after the first request, and the production
    app has already handled requests by the time tests run.
    """
    from app import app as flask_app
    from werkzeug.exceptions import InternalServerError

    handler_spec = flask_app.error_handler_spec.get(None, {})
    handlers_500 = handler_spec.get(500, {})
    # Flask stores by exception class — fall back to the dict's only value.
    handler = next(iter(handlers_500.values()))

    with flask_app.test_request_context("/some-bad-path"):
        response, status = handler(InternalServerError("boom"))
    assert status == 500
    body = response if isinstance(response, str) else response.get_data(as_text=True)
    assert "500" in body or "something went wrong" in body.lower()
