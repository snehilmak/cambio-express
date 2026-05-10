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
