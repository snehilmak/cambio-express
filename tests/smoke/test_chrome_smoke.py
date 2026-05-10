"""Browser smoke tests for the chrome layer (sidebar, avatar dropdown,
critical buttons). Runs every visited page through a real Chromium and
asserts no JS pageerror occurred — that's the gap that let both
PR #197 (owner avatar dropdown) and PR #198 (return-check +Payment
button) ship to production: the unit suite never executes JS.

If a future refactor breaks any of these flows again, the test fails
loudly with the exact JS error.
"""
import pytest


# ── Pages render with no uncaught JS errors ─────────────────────


@pytest.mark.parametrize("path", [
    "/dashboard",
    "/transfers",
    "/return-checks",
    "/batches",
    "/daily",
    "/admin/audit-log",
])
def test_admin_page_loads_without_js_errors(admin_page, smoke_server, path):
    admin_page.goto(smoke_server + path)
    admin_page.wait_for_load_state("networkidle")
    assert not admin_page.js_errors, (
        f"page {path} threw JS errors: {admin_page.js_errors}"
    )


@pytest.mark.parametrize("path", [
    "/owner/dashboard",
    "/owner/locations",
    "/owner/pl-rollup",
    "/owner/reports",
])
def test_owner_page_loads_without_js_errors(owner_page, smoke_server, path):
    owner_page.goto(smoke_server + path)
    owner_page.wait_for_load_state("networkidle")
    assert not owner_page.js_errors, (
        f"page {path} threw JS errors: {owner_page.js_errors}"
    )


# ── Avatar dropdown actually opens (regression for PR #197) ─────


def test_admin_avatar_dropdown_opens_on_click(admin_page, smoke_server):
    admin_page.goto(smoke_server + "/dashboard")
    admin_page.wait_for_load_state("networkidle")
    avatar = admin_page.locator("#userAvatar")
    dropdown = admin_page.locator("#userDropdown")
    # Closed at start.
    assert dropdown.is_hidden()
    avatar.click()
    # The CSS animates in over ~150ms; expect it visible after a
    # short wait. Playwright's auto-wait will tolerate the transition.
    dropdown.wait_for(state="visible", timeout=2000)
    assert dropdown.is_visible()
    # Sign-out link must be reachable now.
    assert dropdown.locator("a[href='/logout']").is_visible()
    assert not admin_page.js_errors


def test_owner_avatar_dropdown_opens_on_click(owner_page, smoke_server):
    """The exact bug from PR #197 — owner shell's avatar dropdown
    silently failed to open because the JS toggled `hidden` instead
    of the `.is-open` class. With shell.js extracted (PR #199) the
    wiring is shared, so this test guards both shells via one path
    if they ever diverge again."""
    owner_page.goto(smoke_server + "/owner/dashboard")
    owner_page.wait_for_load_state("networkidle")
    avatar = owner_page.locator("#userAvatar")
    dropdown = owner_page.locator("#userDropdown")
    assert dropdown.is_hidden()
    avatar.click()
    dropdown.wait_for(state="visible", timeout=2000)
    assert dropdown.is_visible()
    assert dropdown.locator("a[href='/logout']").is_visible()
    assert not owner_page.js_errors


# Note: the legacy /return-checks +Payment inline modal smoke test was
# retired when /return-checks 301'd to the SPA (PR #392). The SPA's
# return-check edit page surfaces existing payments read-only today;
# the per-payment write UI ships in a follow-up. Once it lands, add
# a smoke test that drives the new SPA flow (button → form → POST →
# row appears) instead of resurrecting the old modal selectors.


# ── Critical buttons exist and are reachable ────────────────────


def test_new_transfer_button_reachable(admin_page, smoke_server):
    """The +New Transfer entry point must always be live. If the
    sidebar nav breaks (CSS regression, JS error, missing route),
    cashiers can't log work."""
    admin_page.goto(smoke_server + "/dashboard")
    admin_page.wait_for_load_state("networkidle")
    # Both the sidebar link and any +New Transfer CTA are valid.
    new_xfer = admin_page.locator("a[href='/transfers/new']").first
    new_xfer.wait_for(state="visible", timeout=2000)
    new_xfer.click()
    admin_page.wait_for_url("**/transfers/new")
    # The form must render the sender input — that's the entry field.
    assert admin_page.locator("input[name='sender_name']").is_visible()
    assert not admin_page.js_errors
