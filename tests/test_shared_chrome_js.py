"""Tests for the shared chrome JS extraction.

`static/shell.js` consolidates the topbar clock, sidebar drawer, and
user-avatar dropdown wiring that previously lived (duplicated) inside
inline `<script>` blocks in both base.html and base_owner.html. The
duplication had drifted: the admin shell's avatar dropdown used the
correct `.is-open` class toggle, but the owner shell's copy only
toggled `hidden`, leaving the dropdown invisible / unclickable.
See PR #197.

These tests pin the contract:
- Both shells load static/shell.js.
- The shared init code (initClock / initSidebarDrawer / initAvatarDropdown)
  ALL live in shell.js, not duplicated in either base.
- The bug that made owner login users unable to open their avatar
  menu cannot regress: the `.is-open` class toggle pattern lives in
  exactly one place.
"""
import re


def _shell_js_contents():
    with open("static/shell.js", encoding="utf-8") as f:
        return f.read()


def test_admin_shell_loads_shell_js(logged_in_client):
    resp = logged_in_client.get("/admin/settings")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "shell.js" in body
    matches = re.findall(r'<script[^>]*shell\.js[^>]*>', body)
    assert matches, "expected shell.js script tag in admin shell"


def test_owner_shell_loads_shell_js():
    from app import app as flask_app, db, User, StoreOwnerLink, Store
    with flask_app.app_context():
        s = Store(name="Shell JS Test", slug="shell-js-test", plan="trial")
        db.session.add(s); db.session.commit()
        o = User(username="owner-shell-js@x.com", role="owner",
                 store_id=None, full_name="Shell Owner")
        o.set_password("p"); db.session.add(o); db.session.commit()
        db.session.add(StoreOwnerLink(owner_id=o.id, store_id=s.id))
        db.session.commit()
        oid = o.id
    c = flask_app.test_client()
    with c.session_transaction() as sess:
        sess["user_id"] = oid
        sess["role"] = "owner"
        sess["store_id"] = None
    resp = c.get("/owner/dashboard")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    matches = re.findall(r'<script[^>]*shell\.js[^>]*>', body)
    assert matches, "expected shell.js script tag in owner shell"


def test_shell_js_implements_all_three_init_functions():
    """The file must define the three baseline initializers — adding
    a new shell that loads shell.js then immediately works for free."""
    src = _shell_js_contents()
    assert "function initClock(" in src
    assert "function initSidebarDrawer(" in src
    assert "function initAvatarDropdown(" in src


def test_shell_js_avatar_dropdown_uses_is_open_class():
    """Pin the .is-open class-toggle pattern in exactly one place.
    Removing only the `hidden` attribute leaves opacity:0 +
    pointer-events:none active on the base styles, so the dropdown
    becomes invisible AND unclickable — that's the regression we
    just fixed in PR #197 and don't ever want to re-introduce."""
    src = _shell_js_contents()
    assert "classList.add('is-open')"   in src
    assert "classList.remove('is-open')" in src


def test_avatar_dropdown_logic_not_duplicated_in_bases():
    """Neither base.html nor base_owner.html should still carry
    inline avatar-dropdown wiring — that's what shell.js is for."""
    for path in ("templates/base.html", "templates/base_owner.html"):
        with open(path, encoding="utf-8") as f:
            body = f.read()
        # The unique signature of an avatar-dropdown init is the
        # combination of #userAvatar + #userDropdown lookups in the
        # same script block. If either base re-introduces that
        # combination, we want to know.
        avatar_lookups   = body.count("getElementById('userAvatar')")
        dropdown_lookups = body.count("getElementById('userDropdown')")
        assert avatar_lookups == 0, (
            f"{path} still contains an inline #userAvatar lookup — "
            f"the dropdown wiring belongs in static/shell.js"
        )
        assert dropdown_lookups == 0, (
            f"{path} still contains an inline #userDropdown lookup — "
            f"the dropdown wiring belongs in static/shell.js"
        )


def test_sidebar_drawer_logic_not_duplicated_in_bases():
    """Same guard for the sidebar drawer."""
    for path in ("templates/base.html", "templates/base_owner.html"):
        with open(path, encoding="utf-8") as f:
            body = f.read()
        toggle_lookups = body.count("getElementById('menuToggle')")
        assert toggle_lookups == 0, (
            f"{path} still contains an inline #menuToggle lookup — "
            f"sidebar wiring belongs in static/shell.js"
        )


def test_clock_logic_not_duplicated_in_bases():
    for path in ("templates/base.html", "templates/base_owner.html"):
        with open(path, encoding="utf-8") as f:
            body = f.read()
        # The clock is identifiable by the setInterval(updateClock, ...)
        # bootstrap line that both shells used to ship.
        assert "setInterval(updateClock" not in body, (
            f"{path} still bootstraps the clock inline — "
            f"that lives in static/shell.js now"
        )
