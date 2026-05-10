"""Tests for sortable table headers on /transfers and /batches."""
import json
from datetime import date, timedelta


def _admin_login(client, store_id):
    from app import User, Store, db
    with client.application.app_context():
        u = User.query.filter_by(store_id=store_id, role="admin").first()
        uid = u.id
        s = db.session.get(Store, store_id)
        s.plan = "pro"
        db.session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "admin"
        sess["store_id"] = store_id


def _make_transfer(store_id, *, send_date, sender, amount=100.0):
    from app import Transfer, db
    t = Transfer(
        store_id=store_id, send_date=send_date,
        sender_name=sender, recipient_name="R",
        country="MX", confirm_number=sender[:5],
        company="Intermex", send_amount=amount,
        fee=2.0, federal_tax=1.0, status="Sent",
    )
    db.session.add(t); db.session.commit()
    return t.id


def _make_batch(store_id, *, ach_date, ref, amount=500.0, company="Intermex"):
    from app import ACHBatch, db
    b = ACHBatch(store_id=store_id, ach_date=ach_date,
                 company=company, batch_ref=ref,
                 ach_amount=amount, status="Pending")
    db.session.add(b); db.session.commit()
    return b.id


# ── Transfers ────────────────────────────────────────────────


def test_transfers_default_sort_unchanged(client, test_store_id):
    """No ?sort= param should preserve the historical default
    (newest send_date first)."""
    _admin_login(client, test_store_id)
    from app import app as flask_app
    with flask_app.app_context():
        _make_transfer(test_store_id,
                        send_date=date.today() - timedelta(days=1),
                        sender="Yesterday")
        _make_transfer(test_store_id,
                        send_date=date.today(),
                        sender="Today")
    resp = client.get("/transfers?partial=1")
    assert resp.status_code == 200
    payload = json.loads(resp.data)
    html = payload["html"]
    pos_today = html.find("Today")
    pos_yesterday = html.find("Yesterday")
    assert pos_today < pos_yesterday, "Today should render before Yesterday"


def test_transfers_sort_by_amount_asc(client, test_store_id):
    _admin_login(client, test_store_id)
    from app import app as flask_app
    with flask_app.app_context():
        _make_transfer(test_store_id, send_date=date.today(),
                        sender="Big",   amount=5000.0)
        _make_transfer(test_store_id, send_date=date.today(),
                        sender="Small", amount=10.0)
    resp = client.get("/transfers?partial=1&sort=amount&dir=asc")
    payload = json.loads(resp.data)
    html = payload["html"]
    assert html.find("Small") < html.find("Big")


def test_transfers_sort_by_amount_desc(client, test_store_id):
    _admin_login(client, test_store_id)
    from app import app as flask_app
    with flask_app.app_context():
        _make_transfer(test_store_id, send_date=date.today(),
                        sender="Big",   amount=5000.0)
        _make_transfer(test_store_id, send_date=date.today(),
                        sender="Small", amount=10.0)
    resp = client.get("/transfers?partial=1&sort=amount&dir=desc")
    payload = json.loads(resp.data)
    html = payload["html"]
    assert html.find("Big") < html.find("Small")


def test_transfers_unknown_sort_falls_back_to_default(client, test_store_id):
    _admin_login(client, test_store_id)
    resp = client.get("/transfers?partial=1&sort=hahanopwn&dir=desc")
    assert resp.status_code == 200
    # Doesn't 500 — falls back silently.


def test_transfers_invalid_dir_falls_back_to_desc(client, test_store_id):
    _admin_login(client, test_store_id)
    resp = client.get("/transfers?partial=1&sort=amount&dir=evil")
    assert resp.status_code == 200


def test_transfers_page_renders_sortable_th_headers(client, test_store_id):
    _admin_login(client, test_store_id)
    resp = client.get("/transfers?sort=amount&dir=desc")
    body = resp.get_data(as_text=True)
    assert "th-sortable" in body
    # Active class on the active column.
    assert "th-sortable--active" in body
    # Arrow indicator for desc.
    assert "▼" in body or "th-sort-arrow" in body


# ── Batches ──────────────────────────────────────────────────


def test_batches_legacy_url_redirects_to_spa(client, test_store_id):
    """The legacy /batches list moved to React. The Flask page used
    to do server-side sorting via ?sort= + ?dir=; the SPA does the
    same client-side against /api/v2/batches. The 301 preserves
    those query params so a deep-link to a sorted view lands the
    SPA in the same state. Sort-correctness contract is exercised
    against the API in tests/Modules/Batches/test_batches_controllers.py."""
    _admin_login(client, test_store_id)
    resp = client.get(
        "/batches?sort=company&dir=asc", follow_redirects=False,
    )
    assert resp.status_code == 301
    loc = resp.headers["Location"]
    assert loc.startswith("/app/batches")
    assert "sort=company" in loc
    assert "dir=asc" in loc


def test_batches_default_sort_legacy_url_redirects(client, test_store_id):
    """Bare /batches with no sort params still 301s cleanly."""
    _admin_login(client, test_store_id)
    resp = client.get("/batches", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/batches"
