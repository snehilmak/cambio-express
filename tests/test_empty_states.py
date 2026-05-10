"""Tests for the shared `_empty_table_row.html` partial (still in
use by the Jinja /dashboard for the recent-transfers + recent-
batches columns).

The /transfers + /batches lists themselves moved to React in PRs
#401 + #404; their empty-state UI lives in the SPA components now.
"""


def test_transfers_legacy_url_redirects_to_spa(logged_in_client):
    """The /transfers list moved to React in PR #404. The empty
    state ("No transfers yet") moved with it into Transfers.tsx;
    pinning the redirect contract here is enough."""
    resp = logged_in_client.get("/transfers", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/transfers"


def test_batches_legacy_url_redirects_to_spa(logged_in_client):
    """The /batches list moved to React in PR #401. The Flask URL
    301s; the empty-state copy ("No ACH batches yet") moved with
    it into Batches.tsx. Pinning the redirect contract here is
    enough; the empty-state UI is a frontend concern."""
    resp = logged_in_client.get("/batches", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/batches"


def test_admin_dashboard_legacy_url_redirects_to_spa(logged_in_client):
    """Admin dashboard moved to React in the dashboard SPA migration.
    Empty-state copy ("No transfers yet" / "No batches yet") moved
    into Dashboard.tsx; the Flask URL 301s and the empty-state UI
    is now a frontend concern."""
    resp = logged_in_client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/dashboard"
