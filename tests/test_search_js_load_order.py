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
    resp = logged_in_client.get("/admin/settings")
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




# /return-checks page rendering moved to React. The legacy Jinja
# IIFE that bound the +Payment row action is gone; the SPA
# (frontend/src/routes/ReturnChecks.tsx) owns row interactions
# now. Test deleted — was pinning Jinja-specific markers.
