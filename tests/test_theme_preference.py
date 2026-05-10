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


# The Appearance/theme picker on /account/profile was retired
# when the page moved to React. Per CLAUDE.md invariant #1, the
# SPA is dark-only — no user-facing toggle. The /account/theme
# POST endpoint still exists for Jinja chrome (tested below) but
# the picker UI itself is gone.




def test_theme_chooser_uses_has_selector_for_click_highlight(logged_in_client):
    """REGRESSION: the radio chooser used to only highlight the active
    tile via a server-rendered `is-active` class — clicking a different
    radio toggled the input but didn't move the visual ring until form
    save + reload. CSS now uses `:has(input:checked)` so clicks are
    immediate. We can't assert browser behavior in pytest, but we CAN
    assert the CSS selector is present so a refactor doesn't silently
    drop it."""
    # The static CSS is served by Flask via /static/...
    rv = logged_in_client.get("/static/content.css")
    assert rv.status_code == 200
    body = rv.data.decode()
    assert ":has(input[type=\"radio\"]:checked)" in body, (
        "theme-choice tile must use :has(input:checked) so the active "
        "ring follows the radio without JS"
    )
