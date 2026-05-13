"""Unit tests for BankSync.Services.fc_accounts (PR 73)."""
from datetime import datetime
from unittest.mock import MagicMock, patch

from api.Modules.BankSync.Models import StripeBankAccount
from api.Modules.Tenancy.Models import Store


def _add_store(db, *, slug="fc-acct-store"):
    s = Store(name=slug, slug=slug, plan="basic",
              email=f"{slug}@example.com")
    db.add(s); db.flush()
    return s


def _stripe_account_dict(*, account_id=None, institution_name="Chase",
                          display_name="Chase Checking",
                          last4="0210",
                          category="cash",
                          subcategory="checking",
                          balance=None):
    """Stripe FC Account dict (matches the API response shape)."""
    return {
        "id": account_id or f"fcacct_test_{last4}",
        "institution_name": institution_name,
        "display_name": display_name,
        "last4": last4,
        "category": category,
        "subcategory": subcategory,
        "balance": balance,
    }


# ── upsert_fc_account ──────────────────────────────────────


def test_upsert_inserts_new_account():
    from app import app as flask_app, db
    from api.Modules.BankSync.Services import upsert_fc_account
    with flask_app.app_context():
        StripeBankAccount.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="upsert-fc-new")
        api = _stripe_account_dict(
            account_id="fcacct_new_1",
            institution_name="Nizari Progressive",
            display_name="MSB Checking",
            last4="0230",
        )
        row = upsert_fc_account(db.session, s.id, api)
        assert row.stripe_account_id == "fcacct_new_1"
        assert row.institution_name == "Nizari Progressive"
        assert row.last4 == "0230"
        assert row.enabled is True
        assert row.disconnected_at is None


def test_upsert_idempotent_on_existing_account():
    from app import app as flask_app, db
    from api.Modules.BankSync.Services import upsert_fc_account
    with flask_app.app_context():
        StripeBankAccount.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="upsert-fc-idem")
        api = _stripe_account_dict(account_id="fcacct_idem")
        row1 = upsert_fc_account(db.session, s.id, api)
        row2 = upsert_fc_account(db.session, s.id, api)
        # Same row, no duplicates.
        assert row1.id == row2.id
        assert StripeBankAccount.query.filter_by(
            stripe_account_id="fcacct_idem",
        ).count() == 1


def test_upsert_preserves_existing_fields_when_api_drops_them():
    """Field-merge contract: if Stripe drops a field on a
    subsequent fetch, keep the prior cached value."""
    from app import app as flask_app, db
    from api.Modules.BankSync.Services import upsert_fc_account
    with flask_app.app_context():
        StripeBankAccount.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="upsert-fc-merge")
        first = _stripe_account_dict(
            account_id="fcacct_merge",
            institution_name="Chase",
            display_name="Chase Checking",
            last4="0210",
        )
        upsert_fc_account(db.session, s.id, first)
        # API drops display_name + last4 on next refresh.
        second = {
            "id": "fcacct_merge",
            "institution_name": "Chase",
            "display_name": "",
            "last4": "",
        }
        row = upsert_fc_account(db.session, s.id, second)
        # Prior values preserved.
        assert row.display_name == "Chase Checking"
        assert row.last4 == "0210"


def test_upsert_extracts_balance_with_currency_match():
    """`current` is a {"usd": <cents>} dict; pick the matching
    currency for this account."""
    from app import app as flask_app, db
    from api.Modules.BankSync.Services import upsert_fc_account
    with flask_app.app_context():
        StripeBankAccount.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="upsert-fc-bal")
        api = _stripe_account_dict(
            account_id="fcacct_bal",
            balance={
                "current": {"usd": 12345},
                "as_of": int(datetime(2026, 5, 1).timestamp()),
            },
        )
        row = upsert_fc_account(db.session, s.id, api)
        assert row.last_balance_cents == 12345
        assert row.last_balance_as_of is not None


def test_upsert_extracts_first_balance_when_currency_missing():
    """When `current` doesn't have the account's currency, fall
    back to the first value."""
    from app import app as flask_app, db
    from api.Modules.BankSync.Services import upsert_fc_account
    with flask_app.app_context():
        StripeBankAccount.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="upsert-fc-fallback")
        api = _stripe_account_dict(
            account_id="fcacct_fallback",
            balance={"current": {"eur": 5000}, "as_of": None},
        )
        row = upsert_fc_account(db.session, s.id, api)
        assert row.last_balance_cents == 5000


def test_upsert_handles_missing_balance_gracefully():
    """No `balance` key (permission not granted) — don't crash."""
    from app import app as flask_app, db
    from api.Modules.BankSync.Services import upsert_fc_account
    with flask_app.app_context():
        StripeBankAccount.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="upsert-fc-no-bal")
        api = _stripe_account_dict(account_id="fcacct_no_bal")
        # No balance set in the dict.
        api.pop("balance", None)
        row = upsert_fc_account(db.session, s.id, api)
        # Defaults to 0 / None, no exception raised.
        assert (row.last_balance_cents or 0) == 0


def test_upsert_clears_disconnected_at_on_re_enable():
    """Re-upserting an account that was previously marked
    disconnected re-enables it."""
    from app import app as flask_app, db
    from api.Modules.BankSync.Services import upsert_fc_account
    with flask_app.app_context():
        StripeBankAccount.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="upsert-fc-reconn")
        api = _stripe_account_dict(account_id="fcacct_reconn")
        row = upsert_fc_account(db.session, s.id, api)
        # Mark as disconnected.
        row.enabled = False
        row.disconnected_at = datetime.utcnow()
        db.session.commit()
        # Reconnect via second upsert.
        upsert_fc_account(db.session, s.id, api)
        db.session.refresh(row)
        assert row.enabled is True
        assert row.disconnected_at is None


# ── refresh_bank_balances ─────────────────────────────────


def test_refresh_returns_zero_when_unconfigured(monkeypatch):
    from app import app as flask_app, db
    from api.Modules.BankSync.Services import refresh_bank_balances
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    with flask_app.app_context():
        s = _add_store(db.session, slug="refresh-unconfig")
        updated, err = refresh_bank_balances(db.session, s)
        assert updated == 0
        assert "not configured" in err.lower()


def test_refresh_returns_zero_when_no_enabled_accounts(monkeypatch):
    from app import app as flask_app, db
    from api.Modules.BankSync.Services import refresh_bank_balances
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    with flask_app.app_context():
        StripeBankAccount.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="refresh-no-accts")
        updated, err = refresh_bank_balances(db.session, s)
        assert updated == 0
        assert err == ""


def test_refresh_pulls_balance_for_each_account(monkeypatch):
    from app import app as flask_app, db
    from api.Modules.BankSync.Services import refresh_bank_balances
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    with flask_app.app_context():
        StripeBankAccount.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="refresh-happy")
        # Pre-existing connected account.
        acct = StripeBankAccount(
            store_id=s.id,
            stripe_account_id="fcacct_happy",
            last4="0210",
            enabled=True,
        )
        db.session.add(acct); db.session.commit()
        api_obj = _stripe_account_dict(
            account_id="fcacct_happy",
            balance={"current": {"usd": 99999}, "as_of": None},
        )
        with patch(
            "stripe.financial_connections.Account.refresh_account",
        ), patch(
            "stripe.financial_connections.Account.retrieve",
            return_value=api_obj,
        ):
            updated, err = refresh_bank_balances(db.session, s)
        assert updated == 1
        assert err == ""
        db.session.refresh(acct)
        assert acct.last_balance_cents == 99999


def test_refresh_records_stripe_error_in_last_error(monkeypatch):
    from app import app as flask_app, db
    from api.Modules.BankSync.Services import refresh_bank_balances
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    import stripe
    with flask_app.app_context():
        StripeBankAccount.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="refresh-err")
        db.session.add(StripeBankAccount(
            store_id=s.id,
            stripe_account_id="fcacct_err",
            display_name="Errored Account",
            enabled=True,
        ))
        db.session.commit()
        with patch(
            "stripe.financial_connections.Account.refresh_account",
            side_effect=stripe.error.StripeError("rate limited"),
        ):
            updated, err = refresh_bank_balances(db.session, s)
        assert updated == 0
        assert "Errored Account" in err


# ── legacy Flask wrappers ─────────────────────────────────




