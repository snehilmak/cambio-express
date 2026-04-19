def test_app_loads(client):
    """Smoke test: pytest can import app and make a request."""
    resp = client.get("/")
    assert resp.status_code in (200, 302)


def test_login_at_new_route(client):
    resp = client.get("/login")
    assert resp.status_code == 200


def test_root_is_no_longer_login(client):
    resp = client.get("/")
    assert resp.status_code in (200, 302)
    # If 200, it must NOT be the login page — it must be the landing page stub
    if resp.status_code == 200:
        # The login form has a username field; the stub does not
        assert b'name="username"' not in resp.data


def test_landing_page_loads(client):
    resp = client.get("/")
    assert resp.status_code == 200

def test_landing_has_headline(client):
    resp = client.get("/")
    assert b"Crystal Clear" in resp.data

def test_landing_has_pricing(client):
    resp = client.get("/")
    assert b"$20" in resp.data
    assert b"$30" in resp.data

def test_landing_has_signup_link(client):
    resp = client.get("/")
    assert b"/signup" in resp.data

def test_landing_redirects_logged_in_user(logged_in_client):
    resp = logged_in_client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert "dashboard" in resp.headers["Location"]


def test_store_has_trial_columns(client):
    """Store model must have trial_ends_at and grace_ends_at columns."""
    with client.application.app_context():
        from app import Store
        s = Store.query.filter_by(slug="test-store").first()
        assert hasattr(s, "trial_ends_at")
        assert hasattr(s, "grace_ends_at")
        assert s.trial_ends_at is not None
        assert s.grace_ends_at is not None
