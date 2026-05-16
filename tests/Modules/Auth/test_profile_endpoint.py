"""HTTP integration tests for the account-profile endpoints.

Powers /app/account/profile. GET returns the user's personal info
+ read-only metadata + the timezone dropdown options. PUT applies
validated changes; field-level errors come back as 422 with
`field_errors` keyed by field name (matches the legacy Jinja
form's inline-error shape so the SPA renders identically).
"""
from tests._app import db, db_session


def _login(client_, store_id):
    resp = client_.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


# ── GET /auth/profile ───────────────────────────────────────


def test_profile_requires_jwt(client):
    resp = client.get("/api/v2/auth/profile")
    assert resp.status_code == 401


def test_profile_returns_user_payload(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/auth/profile",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["username"] == "admin@test.com"
    assert body["role"] == "admin"
    # Editable fields default to "" when unset.
    assert body["full_name"] == "Test Admin"
    assert "timezone_choices" in body
    assert "UTC" in body["timezone_choices"]
    assert "America/New_York" in body["timezone_choices"]


def test_profile_includes_metadata_fields(client, test_store_id):
    """Read-only metadata: created_at + last_login_at as ISO
    strings. Empty string is valid (e.g. fresh user that hasn't
    logged in yet) but the seeded admin should have them."""
    token = _login(client, test_store_id)
    body = client.get(
        "/api/v2/auth/profile",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    # The login above bumped last_login_at; created_at was set on
    # the seed insert.
    assert body["created_at"]
    assert body["last_login_at"]


# ── PUT /auth/profile — happy path ──────────────────────────


def test_profile_update_persists_full_name(client, test_store_id):
    from api.Modules.Tenancy.Models import User
    from tests._app import db
    token = _login(client, test_store_id)
    resp = client.put(
        "/api/v2/auth/profile",
        json={"full_name": "Updated Admin Name"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["full_name"] == "Updated Admin Name"
    with db_session():
        u = db.session.query(User).filter_by(username="admin@test.com").first()
        assert u.full_name == "Updated Admin Name"


def test_profile_update_normalizes_email(client, test_store_id):
    """Email gets stripped + lowercased before persist."""
    token = _login(client, test_store_id)
    body = client.put(
        "/api/v2/auth/profile",
        json={"email": "  Owner@Test.COM  "},
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["email"] == "owner@test.com"


def test_profile_update_strips_phone_punctuation(
    client, test_store_id,
):
    """Phone gets whitespace + parens + dashes stripped before
    persist (legacy behavior)."""
    token = _login(client, test_store_id)
    body = client.put(
        "/api/v2/auth/profile",
        json={"phone": "+1 (555) 123-4567"},
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["phone"] == "+15551234567"


def test_profile_update_accepts_valid_timezone(
    client, test_store_id,
):
    token = _login(client, test_store_id)
    body = client.put(
        "/api/v2/auth/profile",
        json={"timezone": "America/Los_Angeles"},
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["timezone"] == "America/Los_Angeles"


def test_profile_update_clears_blanked_fields(client, test_store_id):
    """Empty string explicitly clears email / phone / timezone."""
    from api.Modules.Tenancy.Models import User
    from tests._app import db
    token = _login(client, test_store_id)
    # Set first.
    client.put(
        "/api/v2/auth/profile",
        json={
            "email": "x@y.com", "phone": "+15551234567",
            "timezone": "UTC",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    # Clear.
    body = client.put(
        "/api/v2/auth/profile",
        json={"email": "", "phone": "", "timezone": ""},
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["email"] == ""
    assert body["phone"] == ""
    assert body["timezone"] == ""


# ── PUT /auth/profile — validation ──────────────────────────


def test_profile_update_rejects_empty_full_name(
    client, test_store_id,
):
    token = _login(client, test_store_id)
    resp = client.put(
        "/api/v2/auth/profile",
        json={"full_name": "   "},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    body = resp.get_json()
    assert "full_name" in body["detail"]["field_errors"]


def test_profile_update_rejects_invalid_email(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.put(
        "/api/v2/auth/profile",
        json={"email": "no-at-sign"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    body = resp.get_json()
    assert "email" in body["detail"]["field_errors"]


def test_profile_update_rejects_unsupported_timezone(
    client, test_store_id,
):
    token = _login(client, test_store_id)
    resp = client.put(
        "/api/v2/auth/profile",
        json={"timezone": "Mars/Olympus_Mons"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    body = resp.get_json()
    assert "timezone" in body["detail"]["field_errors"]


def test_profile_update_rejects_invalid_phone(client, test_store_id):
    """Phone validation accepts 7–20 digits with optional leading
    `+`. 'abc' has zero digits after stripping punctuation, so the
    validator rejects."""
    token = _login(client, test_store_id)
    resp = client.put(
        "/api/v2/auth/profile",
        json={"phone": "abc"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    body = resp.get_json()
    assert "phone" in body["detail"]["field_errors"]


def test_profile_update_collects_multiple_field_errors(
    client, test_store_id,
):
    """One PUT with three bad fields returns all three errors at
    once — matches legacy form behavior so the user sees every
    issue without iterating."""
    token = _login(client, test_store_id)
    resp = client.put(
        "/api/v2/auth/profile",
        json={
            "full_name": "",
            "email":     "no-at",
            "timezone":  "Mars/Olympus",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    errors = resp.get_json()["detail"]["field_errors"]
    assert {"full_name", "email", "timezone"} <= set(errors.keys())


# ── Flask redirect ──────────────────────────────────────────


def test_legacy_account_profile_redirects_to_app(logged_in_client):
    resp = logged_in_client.get(
        "/account/profile", follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/account/profile"


# ── theme_preference ────────────────────────────────────────


def test_profile_get_includes_theme_preference(client, test_store_id):
    """The GET payload exposes ``theme_preference`` so the SPA can
    render the saved dark / light choice immediately."""
    token = _login(client, test_store_id)
    body = client.get(
        "/api/v2/auth/profile",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["theme_preference"] in ("dark", "light")


def test_profile_get_falls_back_to_dark_on_missing_value(
    client, test_store_id,
):
    """Defensive: a NULL / empty / unknown theme_preference value
    (left over from a partial migration or a manual DB edit) must
    render as ``"dark"`` so the user never sees an unstyled page."""
    from api.Modules.Tenancy.Models import User
    with db_session():
        u = db.session.query(User).filter_by(
            username="admin@test.com",
        ).first()
        u.theme_preference = ""
        db.session.commit()
    token = _login(client, test_store_id)
    body = client.get(
        "/api/v2/auth/profile",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["theme_preference"] == "dark"


def test_profile_put_persists_theme_preference(client, test_store_id):
    """PUT writes the new value to the User row + returns the
    canonical state."""
    from api.Modules.Tenancy.Models import User
    token = _login(client, test_store_id)
    resp = client.put(
        "/api/v2/auth/profile",
        json={"theme_preference": "light"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["theme_preference"] == "light"
    with db_session():
        u = db.session.query(User).filter_by(
            username="admin@test.com",
        ).first()
        assert u.theme_preference == "light"


def test_profile_put_rejects_invalid_theme_value(client, test_store_id):
    """Anything outside dark / light → 422 from Pydantic. Keeps
    the column from accumulating typo values that would render
    blank."""
    token = _login(client, test_store_id)
    resp = client.put(
        "/api/v2/auth/profile",
        json={"theme_preference": "neon"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
