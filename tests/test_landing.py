def test_app_loads(client):
    """Smoke test: pytest can import app and make a request."""
    resp = client.get("/")
    assert resp.status_code in (200, 302)


def test_store_has_trial_columns(client):
    """Store model must have trial_ends_at and grace_ends_at columns."""
    with client.application.app_context():
        from app import Store
        s = Store.query.filter_by(slug="test-store").first()
        assert hasattr(s, "trial_ends_at")
        assert hasattr(s, "grace_ends_at")
        assert s.trial_ends_at is not None
        assert s.grace_ends_at is not None
