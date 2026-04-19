def test_app_loads(client):
    """Smoke test: pytest can import app and make a request."""
    resp = client.get("/")
    assert resp.status_code in (200, 302, 404)
