"""Tests for the bank-transaction sync helpers + routes (Phase 2).

Stripe is never actually called in unit tests — the rate-limit and
upsert paths exercise app code only. Stripe API integration is covered
by manual smoke testing on /bank in test mode.
"""
from datetime import datetime, timedelta, date


def _admin_login(client, store_id, *, plan="pro"):
    """Log in as the test-store admin. Bank routes are Pro-only via
    pro_required, so the default plan upgrade is what most tests need;
    pass plan="basic" or "trial" to test the gate itself."""
    from app import User, Store, db
    with client.application.app_context():
        u = User.query.filter_by(store_id=store_id, role="admin").first()
        uid = u.id
        s = db.session.get(Store, store_id)
        s.plan = plan
        s.billing_cycle = "monthly"
        db.session.commit()
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["role"] = "admin"
        s["store_id"] = store_id
    return client


# ── _can_sync_bank_transactions ──────────────────────────────


def test_first_sync_allowed(client, test_store_id):
    from app import Store, _can_sync_bank_transactions, db
    with client.application.app_context():
        store = db.session.get(Store, test_store_id)
        ok, reason, retry = _can_sync_bank_transactions(store)
        assert ok and reason == "" and retry == 0


def test_cooldown_blocks_rapid_sync(client, test_store_id):
    from app import Store, _can_sync_bank_transactions, _record_bank_sync, db
    with client.application.app_context():
        store = db.session.get(Store, test_store_id)
        _record_bank_sync(store)
        db.session.commit()
        ok, reason, retry = _can_sync_bank_transactions(store)
        assert not ok
        assert "minute" in reason
        assert retry > 0


def test_cooldown_clears_after_window(client, test_store_id):
    from app import Store, _can_sync_bank_transactions, db, BANK_SYNC_COOLDOWN_MINUTES
    with client.application.app_context():
        store = db.session.get(Store, test_store_id)
        store.bank_sync_last_at = datetime.utcnow() - timedelta(minutes=BANK_SYNC_COOLDOWN_MINUTES + 1)
        store.bank_sync_count_today = 1
        store.bank_sync_count_date = datetime.utcnow().date()
        db.session.commit()
        ok, reason, retry = _can_sync_bank_transactions(store)
        assert ok


def test_daily_cap_blocks_after_max(client, test_store_id):
    from app import Store, _can_sync_bank_transactions, db, MAX_BANK_SYNCS_PER_DAY
    with client.application.app_context():
        store = db.session.get(Store, test_store_id)
        store.bank_sync_last_at = datetime.utcnow() - timedelta(hours=2)
        store.bank_sync_count_today = MAX_BANK_SYNCS_PER_DAY
        store.bank_sync_count_date = datetime.utcnow().date()
        db.session.commit()
        ok, reason, _ = _can_sync_bank_transactions(store)
        assert not ok
        assert "Daily limit" in reason


def test_daily_cap_resets_on_new_day(client, test_store_id):
    from app import Store, _can_sync_bank_transactions, db, MAX_BANK_SYNCS_PER_DAY
    with client.application.app_context():
        store = db.session.get(Store, test_store_id)
        store.bank_sync_count_today = MAX_BANK_SYNCS_PER_DAY
        store.bank_sync_count_date = date.today() - timedelta(days=1)
        store.bank_sync_last_at = datetime.utcnow() - timedelta(hours=2)
        db.session.commit()
        ok, reason, _ = _can_sync_bank_transactions(store)
        assert ok, f"new day should reset the daily counter; got: {reason}"


def test_record_bank_sync_bumps_counters(client, test_store_id):
    from app import Store, _record_bank_sync, db
    with client.application.app_context():
        store = db.session.get(Store, test_store_id)
        store.bank_sync_count_today = 0
        store.bank_sync_count_date = None
        db.session.commit()
        _record_bank_sync(store)
        db.session.commit()
        store = db.session.get(Store, test_store_id)
        assert store.bank_sync_count_today == 1
        assert store.bank_sync_last_at is not None
        assert store.bank_sync_count_date == datetime.utcnow().date()


# ── /bank/transactions route (legacy 301 contract) ──────────


def test_bank_transactions_legacy_url_redirects_to_spa(
        client, test_store_id):
    """The /bank/transactions ledger moved to React in PR #405.
    The Flask page used to do server-side filtering + AJAX
    `?partial=1` live-search; the SPA does both client-side
    against /api/v2/bank-sync/transactions. Pinning the redirect
    contract is enough — the data shape is exercised in
    tests/Modules/BankSync/test_banksync_controllers.py."""
    _admin_login(client, test_store_id)
    resp = client.get("/bank/transactions", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/bank-transactions"


def test_bank_transactions_preserves_query_string_and_strips_partial(
        client, test_store_id):
    """Filters (q + account + date range) survive the 301; the
    legacy `?partial=1` AJAX-only marker is stripped because the
    SPA never sends it."""
    _admin_login(client, test_store_id)
    resp = client.get(
        "/bank/transactions?partial=1&q=maxi&date_from=2026-01-01",
        follow_redirects=False,
    )
    assert resp.status_code == 301
    loc = resp.headers["Location"]
    assert loc.startswith("/app/bank-transactions")
    assert "partial=1" not in loc
    assert "q=maxi" in loc
    assert "date_from=2026-01-01" in loc


# ── /bank/stripe/sync-transactions route ─────────────────────


def test_sync_route_blocked_by_rate_limit(client, test_store_id):
    """When in cooldown, the sync POST flashes an error and does NOT
    bump the counter (no Stripe call attempted)."""
    from app import db, Store
    _admin_login(client, test_store_id)
    with client.application.app_context():
        s = db.session.get(Store, test_store_id)
        s.bank_sync_last_at = datetime.utcnow()
        s.bank_sync_count_today = 1
        s.bank_sync_count_date = datetime.utcnow().date()
        db.session.commit()

    # The flash-text confirmation moved to the SPA (/app/bank); the
    # invariant is "blocked sync doesn't bump the counter."
    resp = client.post("/bank/stripe/sync-transactions", follow_redirects=False)
    assert resp.status_code in (302, 303)

    with client.application.app_context():
        s = db.session.get(Store, test_store_id)
        assert s.bank_sync_count_today == 1, "blocked sync must not bump the counter"


def test_sync_route_requires_admin(client, test_store_id):
    """Unauthenticated POST is bounced to login."""
    resp = client.post("/bank/stripe/sync-transactions", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
