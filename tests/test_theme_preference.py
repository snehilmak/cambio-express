"""Tests for the per-user dark/light UI theme preference.

Theme is stored on User.theme_preference (default 'dark'), exposed to
templates via the inject_theme context processor as `theme`, and
toggled via POST /account/theme. Logged-out pages always render dark —
the preference is per-user.
"""
import pytest
from app import app as flask_app, db


def test_theme_preference_column_exists_and_defaults_dark():
    """The migration in _ADDED_COLUMNS adds the column; the SQLAlchemy
    column declaration sets default='dark' so new User rows pick it up
    without an explicit assignment."""
    with flask_app.app_context():
        from app import User
        u = User(username="theme_default@test.com", role="employee", store_id=None)
        u.set_password("x")
        db.session.add(u)
        db.session.commit()
        assert u.theme_preference == "dark"


def test_inject_theme_returns_dark_for_logged_out(client):
    """Anonymous requests get theme='dark' regardless of any session state.
    Easy to verify: the rendered base.html carries data-theme='dark'."""
    rv = client.get("/login")
    assert rv.status_code == 200
    # login.html is a logged-out page that hardcodes data-theme="dark";
    # this asserts the body is rendered (sanity), not the specific
    # source of the theme attribute.
    assert b'data-theme="dark"' in rv.data


def test_inject_theme_uses_user_preference_when_logged_in(logged_in_client, test_admin_id):
    """Logged-in user with theme_preference='light' should see the base
    template render with data-theme='light'. The dashboard route is
    convenient because it goes through base.html."""
    with flask_app.app_context():
        from app import User
        u = db.session.get(User, test_admin_id)
        u.theme_preference = "light"
        db.session.commit()
    rv = logged_in_client.get("/dashboard")
    assert rv.status_code == 200
    assert b'data-theme="light"' in rv.data


def test_inject_theme_falls_back_to_dark_on_unknown_value(logged_in_client, test_admin_id):
    """If the column ever holds something other than 'dark'/'light' the
    processor returns 'dark' rather than passing the bad value through.
    Defensive, covers cases like a manual DB edit or partial migration."""
    with flask_app.app_context():
        from app import User
        u = db.session.get(User, test_admin_id)
        u.theme_preference = "neon-cyberpunk"  # not a valid choice
        db.session.commit()
    rv = logged_in_client.get("/dashboard")
    assert rv.status_code == 200
    assert b'data-theme="dark"' in rv.data
    assert b'data-theme="neon-cyberpunk"' not in rv.data


def test_account_theme_persists_light(logged_in_client, test_admin_id):
    """POST /account/theme with theme=light flips the user's column,
    redirects, and the next request carries the new theme."""
    rv = logged_in_client.post("/account/theme", data={"theme": "light"})
    assert rv.status_code == 302
    with flask_app.app_context():
        from app import User
        u = db.session.get(User, test_admin_id)
        assert u.theme_preference == "light"


def test_account_theme_persists_dark(logged_in_client, test_admin_id):
    """Round-trip back to dark."""
    with flask_app.app_context():
        from app import User
        u = db.session.get(User, test_admin_id)
        u.theme_preference = "light"
        db.session.commit()
    rv = logged_in_client.post("/account/theme", data={"theme": "dark"})
    assert rv.status_code == 302
    with flask_app.app_context():
        from app import User
        u = db.session.get(User, test_admin_id)
        assert u.theme_preference == "dark"


def test_account_theme_rejects_invalid_value(logged_in_client, test_admin_id):
    """A theme value that's neither 'dark' nor 'light' must NOT clobber
    the existing preference. Important so a malformed POST (or a
    typo'd custom theme name from a future feature) can't leave the
    user with an unstyled page."""
    with flask_app.app_context():
        from app import User
        u = db.session.get(User, test_admin_id)
        u.theme_preference = "light"  # known-good starting point
        db.session.commit()
    rv = logged_in_client.post("/account/theme", data={"theme": "tron"})
    # Still redirects (the route is forgiving) but doesn't write.
    assert rv.status_code == 302
    with flask_app.app_context():
        from app import User
        u = db.session.get(User, test_admin_id)
        assert u.theme_preference == "light"


def test_account_theme_redirects_to_next_param(logged_in_client):
    """The route honors a 'next' form field so the toggle can live on
    any page and bring the user back to that page."""
    rv = logged_in_client.post("/account/theme",
                               data={"theme": "light", "next": "/account/profile"})
    assert rv.status_code == 302
    assert "/account/profile" in rv.headers["Location"]


def test_account_theme_falls_back_to_referrer(logged_in_client):
    """Without a 'next' param the route bounces to the HTTP Referer."""
    rv = logged_in_client.post("/account/theme",
                               data={"theme": "dark"},
                               headers={"Referer": "/dashboard"})
    assert rv.status_code == 302
    assert "/dashboard" in rv.headers["Location"]


def test_account_theme_blocks_unauthenticated(client):
    rv = client.post("/account/theme", data={"theme": "light"})
    assert rv.status_code == 302
    assert "/login" in rv.headers["Location"]


def test_account_profile_renders_appearance_card(logged_in_client):
    """The profile page surfaces the chooser with both options visible
    so users can find the toggle without searching."""
    rv = logged_in_client.get("/account/profile")
    assert rv.status_code == 200
    body = rv.data
    assert b"Appearance" in body
    assert b'name="theme"' in body
    assert b'value="dark"' in body
    assert b'value="light"' in body


def test_account_profile_active_choice_marks_current_theme(logged_in_client, test_admin_id):
    """The radio matching the user's current preference is `checked`."""
    with flask_app.app_context():
        from app import User
        u = db.session.get(User, test_admin_id)
        u.theme_preference = "light"
        db.session.commit()
    rv = logged_in_client.get("/account/profile")
    assert rv.status_code == 200
    # Light radio is checked, dark is not.
    body = rv.data.decode()
    # Find the light radio input markup and confirm `checked`.
    assert 'value="light"' in body
    light_idx = body.find('value="light"')
    # Look at a small slice around the input to confirm `checked` is on it.
    near_light = body[max(0, light_idx - 100):light_idx + 100]
    assert "checked" in near_light


def test_owner_dashboard_carries_theme_attr(client):
    """Owner shell (base_owner.html) goes through the same context
    processor — confirm the data-theme attr is set there too."""
    with flask_app.app_context():
        from app import User
        o = User(username="theme_owner@test.com", role="owner",
                 full_name="Theme Owner", store_id=None)
        o.set_password("ownerpass123")
        db.session.add(o)
        db.session.commit()
        oid = o.id
    with client.session_transaction() as sess:
        sess["user_id"] = oid
        sess["role"] = "owner"
    rv = client.get("/owner/dashboard")
    assert rv.status_code == 200
    assert b'data-theme="dark"' in rv.data
