"""Regression test: search.js must load synchronously (no `defer`).

Pages like /return-checks and /owner/locations have inline `<script>`
blocks in `{% block scripts %}` that call `attachSearchDebounce(...)`
directly during parse. If search.js is loaded with `defer` it won't
have executed yet — the global is undefined and the inline IIFE
throws, leaving the rest of the page JS (modal bindings, row-action
click handlers) un-wired.

Symptom from the field: clicking the "+ Payment" button on
/return-checks did nothing because `bindRowActions()` never ran.

This test pins the load contract so a future "let's defer everything
for perf" sweep can't regress it without flipping a guarded test.
"""


def test_admin_shell_loads_search_js_without_defer(logged_in_client):
    resp = logged_in_client.get("/dashboard")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # The script tag must exist and must NOT carry the `defer` attribute.
    assert "search.js" in body
    # Construct the exact patterns to guard against. We accept either
    # quoting style on the src attribute since templates don't pin it.
    assert 'search.js' in body
    # Find the script tag for search.js and verify no defer is set.
    import re
    matches = re.findall(r'<script[^>]*search\.js[^>]*>', body)
    assert matches, "expected at least one script tag loading search.js"
    for tag in matches:
        assert "defer" not in tag, (
            f"search.js must load synchronously (no `defer`) so inline "
            f"scripts after it can call attachSearchDebounce — got: {tag}"
        )


def test_owner_shell_loads_search_js_without_defer():
    """Same contract on the owner shell — owner_locations.html depends
    on the same global."""
    from app import app as flask_app, db, User, StoreOwnerLink, Store
    with flask_app.app_context():
        s = Store(name="Search JS Test", slug="search-js-test", plan="trial")
        db.session.add(s); db.session.commit()
        o = User(username="owner-search-js@x.com", role="owner",
                 store_id=None, full_name="Search JS Owner")
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
    import re
    matches = re.findall(r'<script[^>]*search\.js[^>]*>', body)
    assert matches, "expected search.js tag in owner shell"
    for tag in matches:
        assert "defer" not in tag, (
            f"search.js must load synchronously in owner shell too — got: {tag}"
        )


def test_return_checks_page_carries_intact_inline_iife(logged_in_client):
    """The page-specific IIFE must not crash before binding row
    handlers. We can't run JS in the test, but we can pin a marker
    that the bindRowActions call is reached at the bottom of the
    IIFE (it won't be reached if the script has already errored)."""
    resp = logged_in_client.get("/return-checks")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # The bottom-of-IIFE bindRowActions() call must be present.
    assert "bindRowActions();" in body, (
        "page must call bindRowActions() at the bottom of its IIFE — "
        "if removed, the +Payment button stops opening the modal"
    )
    assert "rc-act-payment" in body  # the class the JS binds against
