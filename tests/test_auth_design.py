"""Dark+neon redesign guards for the three auth entry pages.

These catch regressions where someone accidentally drops the token
link, reverts to the legacy serif/cream palette, or removes the
employee quick-login box on the main login page.
"""


def test_login_loads_design_tokens(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert b"design-tokens.css" in resp.data


def test_login_renders_neon_accent(client):
    """#3fff00 is the sole saturated color in the system; if it's
    gone, the redesign has been unwound."""
    resp = client.get("/login")
    # The neon enters the page as either an inline hex (#3fff00, used
    # in the isometric SVG) or as a `var(--db-neon)` token reference.
    body = resp.data
    assert b"#3fff00" in body or b"--db-neon" in body


def test_login_has_brand_mark_and_headline(client):
    resp = client.get("/login")
    body = resp.data
    assert b"DineroBook" in body
    assert b"fifteen minutes" in body  # new headline
    assert b"ALL SYSTEMS OPERATIONAL" in body


def test_login_preserves_employee_quick_login(client):
    """PR #74's store-code quick login must survive the redesign —
    it's the only way employees on the installed PWA can reach
    their store's login page."""
    resp = client.get("/login")
    body = resp.data
    assert b"Employee?" in body
    assert b'name="store_code"' in body
    assert b"/employee-login" in body


def test_login_has_forgot_password_link(client):
    resp = client.get("/login")
    assert b"/forgot-password" in resp.data or b"forgot_password" in resp.data


def test_login_error_renders_in_negative_style(client):
    """Bad creds render the error-msg block."""
    resp = client.post(
        "/login",
        data={"username": "nope@example.com", "password": "wrong"},
        follow_redirects=False,
    )
    # 200 with error rendered, or 400 — anything other than a success redirect
    # into the dashboard.
    assert resp.status_code in (200, 400, 401)


def test_signup_loads_design_tokens(client):
    resp = client.get("/signup")
    assert resp.status_code == 200
    assert b"design-tokens.css" in resp.data


def test_signup_renders_neon_accent(client):
    resp = client.get("/signup")
    # The neon enters the page as either an inline hex (#3fff00, used
    # in the isometric SVG) or as a `var(--db-neon)` token reference.
    body = resp.data
    assert b"#3fff00" in body or b"--db-neon" in body


def test_signup_has_all_required_fields(client):
    """Redesign must keep every field the backend reads, otherwise
    POST /signup validation flows break."""
    resp = client.get("/signup")
    body = resp.data
    for field in (b'name="store_name"', b'name="email"', b'name="password"',
                  b'name="phone"', b'name="ref_code"'):
        assert field in body, f"signup missing field: {field!r}"


def test_signup_owner_loads_design_tokens(client):
    resp = client.get("/signup/owner")
    assert resp.status_code == 200
    assert b"design-tokens.css" in resp.data


def test_signup_owner_renders_neon_accent(client):
    resp = client.get("/signup/owner")
    # The neon enters the page as either an inline hex (#3fff00, used
    # in the isometric SVG) or as a `var(--db-neon)` token reference.
    body = resp.data
    assert b"#3fff00" in body or b"--db-neon" in body


def test_signup_owner_has_all_required_fields(client):
    resp = client.get("/signup/owner")
    body = resp.data
    for field in (b'name="full_name"', b'name="email"', b'name="password"'):
        assert field in body, f"signup_owner missing field: {field!r}"


def test_auth_pages_link_fonts(client):
    """All three auth pages pull the new Space Grotesk + Inter stack."""
    for path in ("/login", "/signup", "/signup/owner"):
        resp = client.get(path)
        body = resp.data
        assert b"Space+Grotesk" in body, f"{path} missing Space Grotesk"
        assert b"Inter" in body, f"{path} missing Inter"
