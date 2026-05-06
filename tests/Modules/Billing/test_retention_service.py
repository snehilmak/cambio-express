"""Unit tests for Billing.Services.retention (PR 64).

The full purge cascade is covered by the legacy `tests/
test_purge_retention.py` suite (12 tests, still passing). This
file adds Service-level smoke tests + the small structural
checks that prove the registry hasn't drifted.
"""
from datetime import datetime, timedelta

from app import (
    Customer,
    Store,
    Transfer,
    User,
)


# ── registry shape ─────────────────────────────────────────


def test_store_owned_models_includes_core_per_store_tables():
    """Adding a new per-store model means appending to this
    registry. If a model isn't here, the purge job leaves
    orphans in the DB after a store is deleted."""
    from api.Modules.Billing.Services import STORE_OWNED_MODELS
    expected_min = {
        "Transfer", "ACHBatch", "DailyReport", "DailyDrop",
        "CheckDeposit", "DailyLineItem", "MonthlyFinancial",
        "BankRule", "BankTransaction", "StripeBankAccount",
        "Customer", "ReturnCheck",
        "ReferralCode", "ReferralRedemption",
        "TVDisplay", "User",
        "StoreEmployee", "StoreOwnerLink",
    }
    assert expected_min.issubset(set(STORE_OWNED_MODELS))


def test_fk_overrides_match_referral_models():
    """Referral models don't use the default `store_id` column."""
    from api.Modules.Billing.Services import STORE_FK_OVERRIDES
    assert STORE_FK_OVERRIDES["ReferralCode"] == "owner_store_id"
    assert STORE_FK_OVERRIDES["ReferralRedemption"] == "referee_store_id"


# ── purge_expired_stores ───────────────────────────────────


def test_purge_returns_zero_when_no_expired_stores():
    """Empty/no-expired DB: nothing to do, return 0."""
    from app import app as flask_app, db
    from api.Modules.Billing.Services import purge_expired_stores
    with flask_app.app_context():
        # Make sure no inactive-with-elapsed-retention stores exist.
        Store.query.filter_by(plan="inactive").update(
            {"data_retention_until": None},
            synchronize_session=False,
        )
        db.session.commit()
        assert purge_expired_stores(db.session) == 0


def test_purge_skips_inactive_store_with_future_retention():
    """A canceled store still inside its retention window must
    NOT be purged — the operator still has time to come back."""
    from app import app as flask_app, db
    from api.Modules.Billing.Services import purge_expired_stores
    with flask_app.app_context():
        s = Store(
            name="Future-Retention", slug="future-retention",
            plan="inactive",
            email="future-retention@test.com",
            data_retention_until=datetime.utcnow()
                + timedelta(days=30),
        )
        db.session.add(s); db.session.commit()
        sid = s.id
        result = purge_expired_stores(db.session)
        assert result == 0
        # Store row still there.
        assert Store.query.filter_by(id=sid).first() is not None


def test_purge_deletes_expired_store_and_cascades_owned_rows():
    """Inactive store past its retention window → store row gone,
    every per-store row gone too."""
    from app import app as flask_app, db
    from api.Modules.Billing.Services import purge_expired_stores
    with flask_app.app_context():
        s = Store(
            name="Expired-Co", slug="expired-co",
            plan="inactive",
            email="expired-co@test.com",
            data_retention_until=datetime.utcnow()
                - timedelta(days=1),
        )
        db.session.add(s); db.session.flush()
        # Add some per-store rows that should disappear.
        db.session.add(User(
            username="expired-admin@test.com",
            password_hash="x", role="admin",
            full_name="x", email="expired-admin@test.com",
            store_id=s.id,
        ))
        db.session.add(Customer(
            store_id=s.id,
            full_name="Test Customer",
            phone_country="+1",
            phone_number="5551234",
        ))
        db.session.add(Transfer(
            store_id=s.id,
            send_date=datetime.utcnow().date(),
            company="Intermex", sender_name="x",
            send_amount=100.0, fee=0.0, federal_tax=0.0,
            status="Sent",
        ))
        db.session.commit()
        sid = s.id

        result = purge_expired_stores(db.session)
        assert result == 1
        # Store row gone.
        assert Store.query.filter_by(id=sid).first() is None
        # Owned rows gone.
        assert User.query.filter_by(store_id=sid).count() == 0
        assert Customer.query.filter_by(store_id=sid).count() == 0
        assert Transfer.query.filter_by(store_id=sid).count() == 0


def test_purge_skips_active_paid_stores():
    """Even past `data_retention_until` (which shouldn't be set
    on a paid plan), an active paid store is never purged. The
    plan filter is `inactive`."""
    from app import app as flask_app, db
    from api.Modules.Billing.Services import purge_expired_stores
    with flask_app.app_context():
        s = Store(
            name="Active-Paid", slug="active-paid",
            plan="basic",  # paid, not inactive
            email="active-paid@test.com",
            data_retention_until=datetime.utcnow()
                - timedelta(days=999),  # ridiculously past
        )
        db.session.add(s); db.session.commit()
        sid = s.id

        result = purge_expired_stores(db.session)
        # Doesn't count this store — plan is "basic" not "inactive".
        assert result == 0
        assert Store.query.filter_by(id=sid).first() is not None


# ── legacy Flask wrapper + CLI ─────────────────────────────


def test_legacy_purge_expired_stores_delegates():
    """app.purge_expired_stores hands db.session to the Service."""
    from app import app as flask_app
    from app import purge_expired_stores as legacy
    with flask_app.app_context():
        # No expired stores → 0.
        assert legacy() == 0


def test_legacy_constants_re_exported():
    """app._STORE_OWNED_MODELS / _STORE_FK_OVERRIDES re-export
    the Service registry for any tooling that imported by name."""
    from app import _STORE_FK_OVERRIDES, _STORE_OWNED_MODELS
    from api.Modules.Billing.Services import (
        STORE_FK_OVERRIDES, STORE_OWNED_MODELS,
    )
    assert _STORE_OWNED_MODELS is STORE_OWNED_MODELS
    assert _STORE_FK_OVERRIDES is STORE_FK_OVERRIDES
