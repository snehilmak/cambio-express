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


# ── /bank/transactions route ─────────────────────────────────


def test_bank_transactions_route_renders_empty(client, test_store_id):
    _admin_login(client, test_store_id)
    resp = client.get("/bank/transactions")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "All Bank Transactions" in body
    assert "No transactions yet" in body


def test_bank_transactions_partial_returns_json(client, test_store_id):
    _admin_login(client, test_store_id)
    resp = client.get("/bank/transactions?partial=1")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload is not None
    assert "html" in payload
    assert "total" in payload
    assert payload["total"] == 0


def test_bank_transactions_filters_by_search(client, test_store_id):
    """Insert a few rows directly and confirm the q filter narrows them."""
    from app import db, BankTransaction, StripeBankAccount
    _admin_login(client, test_store_id)
    with client.application.app_context():
        acct = StripeBankAccount(
            store_id=test_store_id, stripe_account_id="fca_test_1",
            display_name="Checking", last4="1234",
        )
        db.session.add(acct); db.session.flush()
        for i, desc in enumerate(["MAXISEND CO ENTRY", "WAL-MART POS", "INTERMEX ACH"]):
            db.session.add(BankTransaction(
                store_id=test_store_id, stripe_bank_account_id=acct.id,
                stripe_transaction_id=f"fctxn_{i}",
                amount_cents=1000 * (i + 1),
                description=desc,
                posted_at=datetime.utcnow() - timedelta(hours=i),
            ))
        db.session.commit()

    resp = client.get("/bank/transactions?partial=1&q=maxi")
    payload = resp.get_json()
    assert payload["total"] == 1
    assert "MAXISEND" in payload["html"]
    assert "WAL-MART" not in payload["html"]


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

    resp = client.post("/bank/stripe/sync-transactions", follow_redirects=True)
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "wait" in body.lower() or "minute" in body.lower()

    with client.application.app_context():
        s = db.session.get(Store, test_store_id)
        assert s.bank_sync_count_today == 1, "blocked sync must not bump the counter"


def test_sync_route_requires_admin(client, test_store_id):
    """Unauthenticated POST is bounced to login."""
    resp = client.post("/bank/stripe/sync-transactions", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
