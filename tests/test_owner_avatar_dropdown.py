"""Regression test for the owner-shell avatar dropdown wiring.

The dropdown CSS animates via an `.is-open` class toggle. An earlier
revision of base_owner.html wired the avatar to toggle only the
`hidden` attribute — removing `hidden` left `opacity: 0` and
`pointer-events: none` active from the dropdown's base styles, so
the menu looked invisible and was unclickable (no logout, no nav).

This test pins the JS pattern by string-matching the rendered owner
shell, so a future refactor that drops the `.is-open` class toggle
would fail loudly.
"""
import re


def test_owner_shell_avatar_uses_is_open_class():
    """Render the owner base template and confirm the avatar JS
    toggles the .is-open class — not just the `hidden` attribute."""
    from app import app as flask_app, db, User, StoreOwnerLink, Store

    with flask_app.app_context():
        # Seed an owner + a linked store so /owner/dashboard renders.
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

    # The avatar dropdown markup must be present.
    assert 'id="userAvatar"' in body
    assert 'id="userDropdown"' in body

    # Find the script block that wires the avatar — it lives in the
    # owner shell's IIFE next to the menu-toggle code.
    assert "classList.add('is-open')"   in body, \
        "owner avatar JS must add .is-open on click — see static/shell.css .user-dropdown"
    assert "classList.remove('is-open')" in body, \
        "owner avatar JS must remove .is-open on close"

    # And the close path must still re-set `hidden` after the
    # transition — keeps display:none in tact for unmounted state.
    assert "setAttribute('hidden'" in body
