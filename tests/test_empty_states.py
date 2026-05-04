"""Tests for the shared `_empty_table_row.html` partial.

The partial replaces the legacy `<tr><td colspan>No X found</td>` rows
with a richer empty state (icon + title + body + optional CTA). These
tests pin the expected markup so a future refactor can't quietly
regress the structure or the per-page copy.
"""
import json


def test_transfers_empty_state_shows_cta(logged_in_client):
    """A fresh store with zero transfers should render the empty-row
    partial with the +New Transfer CTA on the main /transfers page."""
    resp = logged_in_client.get("/transfers")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'class="empty-row"' in body
    assert "No transfers yet" in body
    # CTA points at /transfers/new — both the href and the button label.
    assert "/transfers/new" in body
    assert "+ New Transfer" in body


def test_transfers_partial_filtered_empty_state(logged_in_client):
    """When the user has filters on but no rows match, show the
    'no results match these filters' variant (search icon, no CTA)."""
    resp = logged_in_client.get("/transfers?sender=zzz_no_such_sender&partial=1")
    assert resp.status_code == 200
    payload = json.loads(resp.data)
    html = payload["html"]
    assert 'class="empty-row"' in html
    assert "No transfers match these filters" in html
    # No "+ New Transfer" CTA on the filtered variant — clearing the
    # filter is the right action, not creating a transfer.
    assert "+ New Transfer" not in html


def test_batches_empty_state_renders(logged_in_client):
    resp = logged_in_client.get("/batches")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'class="empty-row"' in body
    assert "No ACH batches yet" in body
    assert "+ New Batch" in body


def test_admin_dashboard_empty_states_render(logged_in_client):
    """Admin dashboard has two empty rows (recent transfers + recent
    batches). Verify both render via the new partial when the store
    has no data."""
    resp = logged_in_client.get("/dashboard")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # Both empty rows should be present — count occurrences of the class.
    assert body.count('class="empty-row"') >= 2
    assert "No transfers yet" in body
    assert "No batches yet" in body
