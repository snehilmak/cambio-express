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


def test_transfers_legacy_url_redirects_to_spa(client, test_store_id):
    """The legacy /transfers list moved to React in PR #404. The
    Flask page used to do server-side sorting + an AJAX `?partial=1`
    live-search; the SPA does both client-side against
    /api/v2/transfers. The 301 preserves sort + dir params so a
    deep-link to a sorted view still lands the SPA in the same
    state. Sort-correctness is exercised on the API in
    tests/Modules/Transfers/test_transfers_controllers.py."""
    _admin_login(client, test_store_id)
    resp = client.get(
        "/transfers?sort=amount&dir=desc", follow_redirects=False,
    )
    assert resp.status_code == 301
    loc = resp.headers["Location"]
    assert loc.startswith("/app/transfers")
    assert "sort=amount" in loc
    assert "dir=desc" in loc


def test_transfers_partial_marker_stripped_on_redirect(client, test_store_id):
    """The legacy `?partial=1` AJAX-only flag is stripped from the
    redirect target so a stale browser cache isn't forwarded a
    no-op param the SPA would just ignore."""
    _admin_login(client, test_store_id)
    resp = client.get(
        "/transfers?partial=1&sort=amount&dir=asc",
        follow_redirects=False,
    )
    assert resp.status_code == 301
    loc = resp.headers["Location"]
    assert "partial=1" not in loc
    assert "sort=amount" in loc
    assert "dir=asc" in loc


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
