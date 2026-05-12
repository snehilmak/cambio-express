"""Browser smoke tests for the SPA chrome layer (sidebar, sign-out,
critical buttons). Runs each visited page through real Chromium and
asserts no JS pageerror occurred — that's the gap that let both
PR #197 (owner avatar dropdown) and PR #198 (return-check +Payment
button) ship to production: the unit suite never executes JS.

These tests target the React SPA chrome at ``/app/*``. The legacy
Jinja avatar-dropdown selectors (`#userAvatar`, `#userDropdown`)
that older revisions of this file used were retired when every
dashboard/list/form moved to the SPA — the SPA's `AppShell` has a
flat "Sign out" button in the topbar, no dropdown to open.
"""
import pytest


# Routes that should render under the admin AppShell without
# throwing. Every one is a public-to-the-store-admin SPA route
# served at `/app/<path>`.
_ADMIN_SPA_ROUTES = [
    "/app/dashboard",
    "/app/transfers",
    "/app/return-checks",
    "/app/batches",
    "/app/daily",
    "/app/customers",
    "/app/admin/audit-log",
]


_OWNER_SPA_ROUTES = [
    "/app/owner/dashboard",
    "/app/owner/locations",
    "/app/owner/pl-rollup",
    "/app/owner/reports",
]


# ── Pages render with no uncaught JS errors ─────────────────────


@pytest.mark.parametrize("path", _ADMIN_SPA_ROUTES)
def test_admin_page_loads_without_js_errors(admin_page, smoke_server, path):
    admin_page.goto(smoke_server + path)
    admin_page.wait_for_load_state("networkidle")
    assert not admin_page.js_errors, (
        f"page {path} threw JS errors: {admin_page.js_errors}"
    )


@pytest.mark.parametrize("path", _OWNER_SPA_ROUTES)
def test_owner_page_loads_without_js_errors(owner_page, smoke_server, path):
    owner_page.goto(smoke_server + path)
    owner_page.wait_for_load_state("networkidle")
    assert not owner_page.js_errors, (
        f"page {path} threw JS errors: {owner_page.js_errors}"
    )


# ── Sign-out button reachable from the AppShell topbar ──────────


def test_admin_sign_out_button_visible(admin_page, smoke_server):
    """The "Sign out" button is the SPA's logout affordance. The
    legacy Jinja chrome had a click-to-open dropdown that hid the
    link; the SPA renders the button inline so it's always
    reachable without an extra click."""
    admin_page.goto(smoke_server + "/app/dashboard")
    admin_page.wait_for_load_state("networkidle")
    button = admin_page.get_by_role("button", name="Sign out")
    button.wait_for(state="visible", timeout=2000)
    assert button.is_visible()
    assert not admin_page.js_errors


def test_owner_sign_out_button_visible(owner_page, smoke_server):
    """Owner-shell equivalent of the admin sign-out smoke."""
    owner_page.goto(smoke_server + "/app/owner/dashboard")
    owner_page.wait_for_load_state("networkidle")
    button = owner_page.get_by_role("button", name="Sign out")
    button.wait_for(state="visible", timeout=2000)
    assert button.is_visible()
    assert not owner_page.js_errors


# ── Critical entry-point: +New Transfer ─────────────────────────


def test_new_transfer_button_reachable(admin_page, smoke_server):
    """The +New Transfer entry point must always be live. If the
    sidebar nav breaks (CSS regression, JS error, missing route),
    cashiers can't log work."""
    admin_page.goto(smoke_server + "/app/dashboard")
    admin_page.wait_for_load_state("networkidle")
    # Sidebar link + any in-page CTA both point at the same SPA URL.
    new_xfer = admin_page.locator("a[href='/app/transfers/new']").first
    new_xfer.wait_for(state="visible", timeout=2000)
    new_xfer.click()
    admin_page.wait_for_url("**/app/transfers/new")
    # The form must render the sender input — that's the entry field.
    assert admin_page.locator("input[name='sender_name']").first.is_visible()
    assert not admin_page.js_errors
