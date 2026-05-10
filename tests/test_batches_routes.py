"""Route-level tests for the legacy /batches Flask URL family.

The list / new / edit / per-batch transfers pages all moved to React
(/app/batches[/...]) backed by /api/v2/batches. The Flask routes
now 301-redirect to the SPA; the data-shape and tenancy contracts
the legacy tests pinned (cross-store 404, store-scoped list, audit
log appended on create / edit) are exercised against the JSON
endpoints in `tests/Modules/Batches/test_batches_controllers.py`.

These tests guard:
  - The legacy URLs return 301 to the right /app/* target.
  - The redirect happens *after* the auth gate so a non-admin still
    sees the bounce-to-login or bounce-to-dashboard, never the SPA
    create form.
  - Query strings are preserved (sort + dir on the list view).
"""
from datetime import date

from tests.conftest import make_employee_client


# ── Auth gate (runs BEFORE the 301) ─────────────────────────


def test_batches_requires_login(client):
    """Unauthed → /login. The @admin_required decorator runs before
    the redirect, so an anonymous request is bounced to login (NOT
    to the SPA — we don't want unauthed users landing on /app
    routes that immediately bounce them again)."""
    resp = client.get("/batches", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_batches_employee_blocked(client, test_store_id):
    """Employees aren't admins — admin_required bounces them off.
    The bounce target is /dashboard (the legacy admin_required
    contract), not the SPA list page."""
    c = make_employee_client(test_store_id)
    resp = c.get("/batches", follow_redirects=False)
    assert resp.status_code == 302
    # Bounced by admin_required, not by the SPA redirect.
    assert "/login" not in resp.headers["Location"]
    assert "/app/batches" not in resp.headers["Location"]


# ── 301 contract (list) ─────────────────────────────────────


def test_batches_list_redirects_to_spa(logged_in_client):
    resp = logged_in_client.get("/batches", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/batches"


def test_batches_list_preserves_sort_query_string(logged_in_client):
    """A deep-link to `/batches?sort=ach_date&dir=asc` should land
    the SPA in the same sort state — preserve the query string on
    the redirect."""
    resp = logged_in_client.get(
        "/batches?sort=ach_date&dir=asc", follow_redirects=False,
    )
    assert resp.status_code == 301
    loc = resp.headers["Location"]
    assert loc.startswith("/app/batches")
    assert "sort=ach_date" in loc
    assert "dir=asc" in loc


# ── 301 contract (create) ───────────────────────────────────


def test_new_batch_get_redirects_to_spa(logged_in_client):
    resp = logged_in_client.get("/batches/new", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/batches/new"


def test_new_batch_post_redirects_to_spa(logged_in_client):
    """Legacy form POST also 301s. The SPA POSTs to /api/v2/batches
    directly — the legacy form path is dead. Any in-flight Jinja
    submission lands the user on the SPA create page."""
    resp = logged_in_client.post(
        "/batches/new", data={"ach_date": date.today().isoformat()},
        follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/batches/new"


# ── 301 contract (edit) ─────────────────────────────────────


def test_edit_batch_get_redirects_to_spa(logged_in_client):
    """`/batches/<id>/edit` 301s to `/app/batches/<id>/edit`. The
    redirect runs unconditionally (no DB lookup) — cross-store
    isolation is enforced at the API layer (see
    tests/Modules/Batches/test_batches_controllers.py); the SPA's
    BatchForm.tsx surfaces the 404 from there."""
    resp = logged_in_client.get(
        "/batches/9999/edit", follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/batches/9999/edit"


def test_edit_batch_post_redirects_to_spa(logged_in_client):
    resp = logged_in_client.post(
        "/batches/42/edit", data={"ach_date": "2026-01-01"},
        follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/batches/42/edit"


# ── 301 contract (linked transfers list) ────────────────────


def test_batch_transfers_redirects_to_edit_page(logged_in_client):
    """The legacy "batch detail" template was a separate page; the
    SPA's BatchForm.tsx renders linked transfers inline alongside
    the form. Bounce to the editor."""
    resp = logged_in_client.get(
        "/batches/7/transfers", follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/batches/7/edit"
