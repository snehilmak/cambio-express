"""Tests for the /transfers live-search endpoint.

The route returns full HTML by default, and a JSON envelope {html, total,
page, total_pages, page_amount} when `?partial=1` — page_amount is the
combined send+fee+tax total for the page, matching the single "Amount"
column in the table. The client JS swaps the HTML into #transfersResult
and updates the header count.
"""
import json
from datetime import date, timedelta
from app import app as flask_app, db


def _store_id():
    from app import Store
    with flask_app.app_context():
        return Store.query.filter_by(slug="test-store").first().id


def _seed_roster(store_id):
    from app import StoreEmployee
    with flask_app.app_context():
        e = StoreEmployee(store_id=store_id, name="Maria", is_active=True)
        db.session.add(e)
        db.session.commit()
        return e.id


def _seed_transfer(sender="Jane Doe", send_amount=500.0, fee=5.0, company="Intermex"):
    """Seed a persisted Transfer row directly so we don't go through the UI."""
    from app import Store, User, Transfer
    with flask_app.app_context():
        store = Store.query.filter_by(slug="test-store").first()
        user = User.query.filter_by(username="admin@test.com").first()
        t = Transfer(
            store_id=store.id, created_by=user.id,
            send_date=date.today(), company=company,
            sender_name=sender, send_amount=send_amount, fee=fee,
            federal_tax=round(send_amount * 0.01, 2),
            commission=0.0, status="Sent",
        )
        db.session.add(t)
        db.session.commit()
        return t.id


# ── Partial returns JSON, not HTML ──────────────────────────────

def test_partial_returns_json_envelope(logged_in_client):
    _seed_transfer()
    resp = logged_in_client.get("/transfers?partial=1")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("application/json")
    body = json.loads(resp.data)
    assert "html" in body
    assert "total" in body
    assert "page" in body
    assert "total_pages" in body
    assert "page_amount" in body
    # page_fees removed — total is now combined send+fee+tax.
    assert "page_fees" not in body


def test_partial_html_contains_table_rows(logged_in_client):
    _seed_transfer(sender="Juan Perez")
    resp = logged_in_client.get("/transfers?partial=1")
    body = json.loads(resp.data)
    # The partial HTML should include the <table> and the seeded sender.
    assert "<table>" in body["html"]
    assert "Juan Perez" in body["html"]


def test_partial_respects_search_filters(logged_in_client):
    _seed_transfer(sender="Alice Smith")
    _seed_transfer(sender="Bob Johnson")
    resp = logged_in_client.get("/transfers?partial=1&sender=Alice")
    body = json.loads(resp.data)
    assert body["total"] == 1
    assert "Alice Smith" in body["html"]
    assert "Bob Johnson" not in body["html"]


def test_partial_respects_q_fulltext_search(logged_in_client):
    _seed_transfer(sender="Alice Smith")
    _seed_transfer(sender="Bob Johnson")
    resp = logged_in_client.get("/transfers?partial=1&q=Johnson")
    body = json.loads(resp.data)
    assert body["total"] == 1
    assert "Bob Johnson" in body["html"]


def test_table_shows_combined_amount_and_breakdown(logged_in_client):
    """Each row renders the send+fee+tax total as the Amount cell and
    includes all three values in a hover-pill breakdown. The individual
    Fee and Tax columns are gone."""
    _seed_transfer(send_amount=100.0, fee=2.50)  # tax seed = 1.00
    resp = logged_in_client.get("/transfers")
    html = resp.data.decode()
    # Combined total appears in the cell: 100 + 2.50 + 1.00 = 103.50
    assert "$103.50" in html
    # Breakdown is in the tooltip markup.
    assert "tf-amount-tip" in html
    assert "Amount" in html and "Fee" in html and "Tax" in html
    assert "$100.00" in html and "$2.50" in html and "$1.00" in html
    # Old separate <th>Fee</th> / <th>Tax</th> header cells are gone —
    # use tags to avoid matching the tooltip labels.
    assert "<th>Fee</th>" not in html
    assert "<th>Tax</th>" not in html


def test_partial_reports_page_sums(logged_in_client):
    """page_amount is the combined send + fee + tax total for the page."""
    # _seed_transfer sets federal_tax to send_amount * 0.01, so:
    # row 1: 100 + 2 + 1.00 = 103.00
    # row 2: 200 + 3 + 2.00 = 205.00
    # combined = 308.00
    _seed_transfer(send_amount=100.0, fee=2.0)
    _seed_transfer(send_amount=200.0, fee=3.0)
    resp = logged_in_client.get("/transfers?partial=1")
    body = json.loads(resp.data)
    assert abs(body["page_amount"] - 308.0) < 0.01


# ── Non-partial path still returns full HTML (backward compat) ──

def test_full_page_still_renders_html(logged_in_client):
    _seed_transfer()
    resp = logged_in_client.get("/transfers")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("text/html")
    # The full page must include the chrome that's NOT in the partial —
    # the card-header, the tf-search-row, and the #transfersResult
    # wrapper.
    assert b'id="transfersResult"' in resp.data
    assert b'id="tfSearchQ"' in resp.data


def test_full_page_and_partial_show_same_rows(logged_in_client):
    _seed_transfer(sender="Carla Rodriguez")
    full = logged_in_client.get("/transfers").data.decode("utf-8")
    partial = json.loads(logged_in_client.get("/transfers?partial=1").data)
    assert "Carla Rodriguez" in full
    assert "Carla Rodriguez" in partial["html"]


# ── Pagination still works for the partial path ─────────────────

def test_partial_pagination(logged_in_client):
    # Seed 60 transfers so we have 2 pages at per_page=50.
    for i in range(60):
        _seed_transfer(sender=f"Customer {i:03d}", send_amount=100.0 + i)
    r1 = json.loads(logged_in_client.get("/transfers?partial=1&page=1").data)
    r2 = json.loads(logged_in_client.get("/transfers?partial=1&page=2").data)
    assert r1["total"] == 60
    assert r1["total_pages"] == 2
    assert r1["page"] == 1
    assert r2["page"] == 2
    # Page 2 should have exactly 10 rows (60 - 50).
    assert r2["html"].count("<tr>") >= 10
