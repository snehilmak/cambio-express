"""Regression test for the owner-shell avatar dropdown wiring.

The dropdown CSS animates via an `.is-open` class toggle. An earlier
revision of base_owner.html wired the avatar to toggle only the
`hidden` attribute — removing `hidden` left `opacity: 0` and
`pointer-events: none` active from the dropdown's base styles, so
the menu looked invisible and was unclickable (no logout, no nav).

The fix landed in PR #197; the JS was later extracted into
`static/shell.js` (shared-chrome PR). This test now pins both
that the owner shell loads shell.js AND that shell.js still
contains the class-toggle pattern.
"""


def test_owner_shell_loads_shell_js():
    """Render the owner base template and confirm static/shell.js
    is loaded — that's where the avatar dropdown JS lives now."""
    from app import app as flask_app, db, User, StoreOwnerLink, Store

    with flask_app.app_context():
        s = Store(name="Owner Avatar Test", slug="owner-avatar-test",
                  plan="trial")
        db.session.add(s); db.session.commit()
        o = User(username="owner-avatar@x.com", role="owner",
                 store_id=None, full_name="Avatar Owner")
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

    assert 'id="userAvatar"' in body
    assert 'id="userDropdown"' in body
    assert "shell.js" in body, (
        "owner shell must load static/shell.js — that's where the "
        "avatar-dropdown JS lives. See PR #197 for the bug history."
    )


def test_shell_js_keeps_is_open_class_toggle():
    """Pin the class-toggle pattern in shell.js. Removing it would
    re-introduce the original bug: dropdown becomes invisible +
    unclickable because removing only `hidden` leaves opacity:0 +
    pointer-events:none active on the base styles."""
    with open("static/shell.js", encoding="utf-8") as f:
        src = f.read()
    assert "classList.add('is-open')"   in src, \
        "shell.js must add .is-open on open — see static/shell.css .user-dropdown"
    assert "classList.remove('is-open')" in src, \
        "shell.js must remove .is-open on close"
    assert "setAttribute('hidden'" in src, \
        "shell.js must re-set `hidden` after the close transition settles"
