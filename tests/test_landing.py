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
    """Hero headline names the core value prop: the daily book for MSBs."""
    resp = client.get("/")
    assert b"The daily book" in resp.data
    assert b"money-service" in resp.data

def test_landing_has_pricing(client):
    """All three plan prices must render so the pricing section never
    silently regresses to a single tier."""
    resp = client.get("/")
    # Trial (free), Basic ($20), Pro ($30) — each plan's headline price.
    assert b"$0" in resp.data
    assert b"$20" in resp.data
    assert b"$30" in resp.data

def test_landing_has_signup_link(client):
    resp = client.get("/")
    assert b"/signup" in resp.data

def test_landing_has_all_core_sections(client):
    """Every major landing section must render — guards against a
    future edit accidentally dropping one of: features / how-it-works
    / pricing / FAQ / CTA."""
    resp = client.get("/")
    body = resp.data
    # Stat strip anchor values
    assert b"2,400+" in body
    assert b"$4.2B" in body
    # The five feature eyebrows
    for eye in (
        b"THE DAILY BOOK",
        b"MONEY TRANSFERS",
        b"ACH RECONCILIATION",
        b"MONTHLY P&amp;L",
        b"BANK SYNC",
    ):
        assert eye in body, f"missing feature eyebrow: {eye!r}"
    # How it works + FAQ + CTA band markers
    assert b"HOW IT WORKS" in body
    assert b"QUESTIONS" in body
    assert b"Start free trial" in body

def test_landing_loads_design_tokens_css(client):
    """The dark+neon token layer must be linked — if this regresses,
    every color on the page falls back to browser defaults."""
    resp = client.get("/")
    assert b"design-tokens.css" in resp.data

def test_landing_references_neon_primary_color(client):
    """Smoke-check the neon accent. It's referenced inline in the
    hero SVG (`#3fff00` stroke) and as a CSS custom-property value.
    If it disappears entirely, something unwound the redesign."""
    resp = client.get("/")
    assert b"#3fff00" in resp.data

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
