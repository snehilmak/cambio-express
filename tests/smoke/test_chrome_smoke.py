"""Browser smoke tests for the SPA chrome layer (sidebar, sign-out,
critical buttons). Runs each visited page through real Chromium and
asserts no JS pageerror occurred — that's the gap that let both
PR #197 (owner avatar dropdown) and PR #198 (return-check +Payment
button) ship to production: the unit suite never executes JS.

These tests target the React SPA chrome at ``/app/*``. The topbar
exposes a circular avatar button (PR #577) — click to open a
dropdown with Profile / Notifications / Sign out. The dropdown
itself is rendered conditionally via React state, so the smoke
tests open it explicitly before asserting on the menu items.
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
    # PR #577 added these to the user-menu dropdown — verify the
    # routes themselves still render. (The dropdown link reachability
    # is covered by `test_admin_user_menu_dropdown_opens` below.)
    "/app/account/profile",
    "/app/account/notifications",
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


# ── User-menu dropdown (avatar button → Profile / Sign out) ─────


def _open_user_menu(page):
    """Click the avatar button in the topbar to open the dropdown.

    The button carries an ``aria-label`` of ``User menu for <user>``
    set by ``UserMenu.tsx`` — that's the stable selector across
    role flavors."""
    avatar = page.locator("button[aria-label^='User menu for']").first
    avatar.wait_for(state="visible", timeout=2000)
    avatar.click()


def test_admin_user_menu_dropdown_opens(admin_page, smoke_server):
    """Click the topbar avatar → Profile / Notifications / Sign out
    items appear. PR #577 restored this dropdown after the SPA
    migration dropped it. Without it, users had no entry into the
    per-user account screens."""
    admin_page.goto(smoke_server + "/app/dashboard")
    admin_page.wait_for_load_state("networkidle")
    _open_user_menu(admin_page)
    # menuitem role covers both the <Link>s (Profile / Notifications)
    # and the <button> (Sign out) — they all share that semantic role.
    assert admin_page.get_by_role("menuitem", name="Profile").first.is_visible()
    assert admin_page.get_by_role("menuitem", name="Notifications").first.is_visible()
    assert admin_page.get_by_role("menuitem", name="Sign out").first.is_visible()
    assert not admin_page.js_errors


def test_owner_user_menu_dropdown_opens(owner_page, smoke_server):
    """Owner-shell equivalent of the admin user-menu smoke."""
    owner_page.goto(smoke_server + "/app/owner/dashboard")
    owner_page.wait_for_load_state("networkidle")
    _open_user_menu(owner_page)
    assert owner_page.get_by_role("menuitem", name="Profile").first.is_visible()
    assert owner_page.get_by_role("menuitem", name="Notifications").first.is_visible()
    assert owner_page.get_by_role("menuitem", name="Sign out").first.is_visible()
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


# ── Return checks: list-page Edit button reachable ──────────────


def test_return_checks_list_has_edit_affordance(admin_page, smoke_server):
    """PR #578 added an explicit "Edit / Record payment" button on
    every return-check row after a user reported the list page felt
    inert (rows weren't clearly clickable). This smoke locks in
    that affordance — if it disappears or the link target breaks,
    cashiers lose access to the edit page.

    Seeds one return check first so the table renders at least one
    row."""
    from datetime import date as _date

    from api.Modules.ReturnChecks.Models import ReturnCheck
    from tests._app import db, db_session
    from api.Modules.Tenancy.Models import Store

    with db_session():
        store = db.session.query(Store).filter_by(slug="test-store").first()
        rc = ReturnCheck(
            store_id=store.id,
            bounced_on=_date.today(),
            customer_name="Smoke Test Co",
            check_number="SMK-1",
            payer_bank="Smoke Bank",
            amount=150.0,
            status="pending",
        )
        db.session.add(rc)
        db.session.commit()
        rc_id = rc.id

    admin_page.goto(smoke_server + "/app/return-checks")
    admin_page.wait_for_load_state("networkidle")
    # Look for any link pointing at the edit page for this row.
    edit_link = admin_page.locator(
        f"a[href='/app/return-checks/{rc_id}/edit']",
    ).first
    edit_link.wait_for(state="visible", timeout=2000)
    edit_link.click()
    admin_page.wait_for_url(f"**/return-checks/{rc_id}/edit")
    # The edit form's customer_name input is the canonical entry field.
    assert admin_page.locator("input[type='text']").first.is_visible()
    # Record-payment form is the partial-pay UI added in PR #576.
    # The "Record payment" button is the discoverable affordance.
    assert admin_page.get_by_role("button", name="Record payment").first.is_visible()
    assert not admin_page.js_errors
