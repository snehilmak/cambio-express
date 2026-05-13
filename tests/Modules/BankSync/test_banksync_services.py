"""Unit tests for BankSync.Services — list_transactions_page."""
from datetime import datetime, timedelta


def _seed_account(store_id, *, last4="0000"):
    from api.Modules.BankSync.Models import StripeBankAccount
    from app import db
    a = StripeBankAccount(
        store_id=store_id,
        stripe_account_id=f"fcacc_{last4}",
        institution_name="Bank",
        last4=last4,
    )
    db.session.add(a); db.session.commit()
    return a.id


def _seed_txn(store_id, account_id, *, amount_cents=-100,
                description="X", category_slug="",
                posted_at=None, stripe_transaction_id=None):
    from api.Modules.BankSync.Models import BankTransaction
    from app import db
    t = BankTransaction(
        store_id=store_id,
        stripe_bank_account_id=account_id,
        stripe_transaction_id=(
            stripe_transaction_id or f"t_{description}_{amount_cents}"
        ),
        amount_cents=amount_cents,
        description=description,
        category_slug=category_slug,
        posted_at=posted_at or datetime.utcnow(),
        status="posted",
    )
    db.session.add(t); db.session.commit()
    return t.id


# ── list_transactions_page ──────────────────────────────────


def test_page_meta_and_totals(test_store_id):
    from app import app as flask_app, db
    from api.Modules.BankSync.Repositories import BankTransactionFilters
    from api.Modules.BankSync.Services import list_transactions_page
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        _seed_txn(test_store_id, a, amount_cents=-100)
        _seed_txn(test_store_id, a, amount_cents=200)
        page = list_transactions_page(
            db.session, [test_store_id], BankTransactionFilters(),
        )
    assert page.total == 2
    assert page.page == 1
    assert page.total_pages == 1
    assert len(page.rows) == 2
    # |−100| + |200| = 300
    assert page.page_total_cents == 300


def test_page_uncategorized_count_independent_of_pagination(test_store_id):
    """Pill shows the count across the entire filtered window, not
    just the current page."""
    from app import app as flask_app, db
    from api.Modules.BankSync.Repositories import BankTransactionFilters
    from api.Modules.BankSync.Services import list_transactions_page
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        # 3 uncategorized, 2 categorized.
        for i in range(3):
            _seed_txn(
                test_store_id, a, description=f"U{i}",
                stripe_transaction_id=f"u{i}",
            )
        for i in range(2):
            _seed_txn(
                test_store_id, a,
                description=f"C{i}",
                category_slug="bank_charge_210",
                stripe_transaction_id=f"c{i}",
            )
        # Tiny per_page so pagination splits the result.
        page = list_transactions_page(
            db.session, [test_store_id], BankTransactionFilters(),
            page=1, per_page=2,
        )
    assert page.total == 5
    assert page.uncategorized_count == 3


def test_page_total_cents_only_visible_rows(test_store_id):
    """Footer total reflects ONLY rows on the visible page."""
    from app import app as flask_app, db
    from api.Modules.BankSync.Repositories import BankTransactionFilters
    from api.Modules.BankSync.Services import list_transactions_page
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        # Posted_at descending, so the latest-inserted shows first.
        # Insert in increasing order: -100, -200, -300, -400, -500.
        for i, cents in enumerate([-100, -200, -300, -400, -500]):
            _seed_txn(
                test_store_id, a, amount_cents=cents,
                description=str(cents),
                stripe_transaction_id=f"t{i}",
                posted_at=datetime.utcnow() + timedelta(seconds=i),
            )
        page = list_transactions_page(
            db.session, [test_store_id], BankTransactionFilters(),
            page=1, per_page=2,
        )
    # Page 1 has the two newest (cents -500, -400). |−500| + |−400| = 900.
    assert page.page_total_cents == 900


def test_page_filter_passthrough_uncategorized(test_store_id):
    """When the caller filters by uncategorized_only, the
    uncategorized_count equals total — we don't re-filter on top."""
    from app import app as flask_app, db
    from api.Modules.BankSync.Repositories import BankTransactionFilters
    from api.Modules.BankSync.Services import list_transactions_page
    with flask_app.app_context():
        a = _seed_account(test_store_id)
        _seed_txn(test_store_id, a, description="U", stripe_transaction_id="u")
        _seed_txn(
            test_store_id, a, description="C",
            category_slug="bank_charge_210",
            stripe_transaction_id="c",
        )
        page = list_transactions_page(
            db.session, [test_store_id],
            BankTransactionFilters(uncategorized_only=True),
        )
    # Filter says "only uncategorized" → 1 row, all uncategorized.
    assert page.total == 1
    assert page.uncategorized_count == 1


def test_page_empty_safe(test_store_id):
    from app import app as flask_app, db
    from api.Modules.BankSync.Repositories import BankTransactionFilters
    from api.Modules.BankSync.Services import list_transactions_page
    with flask_app.app_context():
        page = list_transactions_page(
            db.session, [test_store_id], BankTransactionFilters(),
        )
    assert page.total == 0
    assert page.total_pages == 1
    assert page.page_total_cents == 0
    assert page.uncategorized_count == 0


# ── Pydantic sanity ─────────────────────────────────────────


def test_response_schema_validates_service_output(test_store_id):
    from app import app as flask_app, db
    from api.Modules.BankSync.Repositories import BankTransactionFilters
    from api.Modules.BankSync.Services import list_transactions_page
    from api.Modules.BankSync.Requests import (
        BankTransactionListResponse,
        BankTransactionRow,
    )
    with flask_app.app_context():
        a = _seed_account(test_store_id, last4="9999")
        _seed_txn(test_store_id, a, amount_cents=-210, description="FEE")
        page = list_transactions_page(
            db.session, [test_store_id], BankTransactionFilters(),
        )
        from api.Modules.BankSync.Models import StripeBankAccount
        acc = db.session.get(StripeBankAccount, a)
        rows = [
            BankTransactionRow(
                id=r.id,
                posted_at=r.posted_at.isoformat() if r.posted_at else "",
                description=r.description or "",
                amount_cents=r.amount_cents,
                amount=r.amount,
                currency=r.currency or "usd",
                status=r.status or "posted",
                category_slug=r.category_slug or "",
                account_id=r.stripe_bank_account_id,
                account_label=acc.label,
            )
            for r in page.rows
        ]
        resp = BankTransactionListResponse(
            rows=rows, total=page.total, page=page.page,
            per_page=page.per_page, total_pages=page.total_pages,
            page_total_cents=page.page_total_cents,
            uncategorized_count=page.uncategorized_count,
        )
    assert resp.rows[0].account_label == "••9999"
    assert resp.rows[0].amount == -2.10
