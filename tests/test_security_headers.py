"""Tests for security headers middleware (CSP, frame options, etc.)."""


def test_csp_header_present(client):
    resp = client.get("/api/v2/auth/refresh")
    csp = resp.headers.get("content-security-policy", "")
    assert "default-src 'self'" in csp


def test_csp_allows_stripe(client):
    """Stripe Checkout iframe needs js.stripe.com."""
    resp = client.get("/api/v2/auth/refresh")
    csp = resp.headers.get("content-security-policy", "")
    assert "js.stripe.com" in csp
    assert "checkout.stripe.com" in csp


def test_csp_allows_google_fonts(client):
    """Google Fonts CSS + font files need explicit allowance."""
    resp = client.get("/api/v2/auth/refresh")
    csp = resp.headers.get("content-security-policy", "")
    assert "fonts.googleapis.com" in csp
    assert "fonts.gstatic.com" in csp


def test_clickjacking_blocked(client):
    """X-Frame-Options + CSP frame-ancestors both block iframe embed."""
    resp = client.get("/api/v2/auth/refresh")
    assert resp.headers.get("x-frame-options") == "DENY"
    csp = resp.headers.get("content-security-policy", "")
    assert "frame-ancestors 'none'" in csp


def test_mime_sniffing_blocked(client):
    resp = client.get("/api/v2/auth/refresh")
    assert resp.headers.get("x-content-type-options") == "nosniff"


def test_referrer_policy_set(client):
    resp = client.get("/api/v2/auth/refresh")
    assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


def test_permissions_policy_locks_down_apis(client):
    resp = client.get("/api/v2/auth/refresh")
    pp = resp.headers.get("permissions-policy", "")
    assert "camera=()" in pp
    assert "microphone=()" in pp
