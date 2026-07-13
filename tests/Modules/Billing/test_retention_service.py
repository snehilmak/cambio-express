"""Unit tests for Billing.Services.retention (PR 64).

The full purge cascade is covered by the legacy `tests/
test_purge_retention.py` suite (12 tests, still passing). This
file adds Service-level smoke tests + the small structural
checks that prove the registry hasn't drifted.
"""
from datetime import datetime, timedelta

from api.Modules.Customers.Models import Customer
from api.Modules.Tenancy.Models import Store, User
from api.Modules.Transfers.Models import Transfer
from tests._app import db, db_session


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
        # TimeClockShift FKs to StoreEmployee — if it's missing here
        # the StoreEmployee delete raises a FK violation on Postgres.
        "TimeClockEntry", "TimeClockShift",
    }
    assert expected_min.issubset(set(STORE_OWNED_MODELS))


def test_time_clock_shift_purges_before_store_employee():
    """TimeClockShift must appear before StoreEmployee in the purge
    order — it carries a NOT-NULL FK to store_employee.id, so on
    Postgres deleting the roster row first would violate it."""
    from api.Modules.Billing.Services import STORE_OWNED_MODELS
    order = STORE_OWNED_MODELS
    assert order.index("TimeClockShift") < order.index("StoreEmployee")


def test_fk_overrides_match_referral_models():
    """Referral models don't use the default `store_id` column."""
    from api.Modules.Billing.Services import STORE_FK_OVERRIDES
    assert STORE_FK_OVERRIDES["ReferralCode"] == "owner_store_id"
    assert STORE_FK_OVERRIDES["ReferralRedemption"] == "referee_store_id"


# ── purge_expired_stores ───────────────────────────────────


def test_purge_returns_zero_when_no_expired_stores():
    """Empty/no-expired DB: nothing to do, return 0."""
    from tests._app import db
    from api.Modules.Billing.Services import purge_expired_stores
    with db_session():
        # Make sure no inactive-with-elapsed-retention stores exist.
        db.session.query(Store).filter_by(plan="inactive").update(
            {"data_retention_until": None},
            synchronize_session=False,
        )
        db.session.commit()
        assert purge_expired_stores(db.session) == 0


def test_purge_skips_inactive_store_with_future_retention():
    """A canceled store still inside its retention window must
    NOT be purged — the operator still has time to come back."""
    from tests._app import db
    from api.Modules.Billing.Services import purge_expired_stores
    with db_session():
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
        assert db.session.query(Store).filter_by(id=sid).first() is not None


def test_purge_deletes_expired_store_and_cascades_owned_rows():
    """Inactive store past its retention window → store row gone,
    every per-store row gone too."""
    from tests._app import db
    from api.Modules.Billing.Services import purge_expired_stores
    with db_session():
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
        assert db.session.query(Store).filter_by(id=sid).first() is None
        # Owned rows gone.
        assert db.session.query(User).filter_by(store_id=sid).count() == 0
        assert db.session.query(Customer).filter_by(store_id=sid).count() == 0
        assert db.session.query(Transfer).filter_by(store_id=sid).count() == 0


def test_purge_skips_active_paid_stores():
    """Even past `data_retention_until` (which shouldn't be set
    on a paid plan), an active paid store is never purged. The
    plan filter is `inactive`."""
    from tests._app import db
    from api.Modules.Billing.Services import purge_expired_stores
    with db_session():
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
        assert db.session.query(Store).filter_by(id=sid).first() is not None


def test_purge_sweeps_user_scoped_child_tables():
    """Regression for the Postgres FK-violation cluster: every table
    that carries a NOT-NULL FK to ``user.id`` must be wiped before
    the User row is deleted, or the purge transaction aborts on
    Postgres and the store is never purged.

    SQLite (the test DB) is FK-permissive so it wouldn't raise — so
    we assert the stronger property the fix guarantees: after the
    purge, none of those child rows survive as orphans."""
    from datetime import date, time
    from tests._app import db
    from api.Modules.Billing.Services import purge_expired_stores
    from api.Modules.Announcements.Models import PushSubscription
    from api.Modules.Auth.Models import (
        LoginEvent, Passkey, PasswordResetToken, RecoveryCode, RefreshToken,
    )
    from api.Modules.Tenancy.Models import StoreEmployee
    from api.Modules.TimeClock.Models import TimeClockShift

    with db_session():
        s = Store(
            name="FK-Cluster", slug="fk-cluster",
            plan="inactive", email="fk-cluster@test.com",
            data_retention_until=datetime.utcnow() - timedelta(days=1),
        )
        db.session.add(s); db.session.flush()
        u = User(
            username="fk-admin@test.com", password_hash="x", role="admin",
            full_name="x", email="fk-admin@test.com", store_id=s.id,
        )
        db.session.add(u); db.session.flush()
        emp = StoreEmployee(store_id=s.id, name="Cashier")
        db.session.add(emp); db.session.flush()

        # One row in every NOT-NULL user-scoped child table.
        db.session.add(RecoveryCode(user_id=u.id, code_hash="h"))
        db.session.add(PasswordResetToken(
            user_id=u.id, token_hash="t",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        ))
        db.session.add(RefreshToken(
            jti="j", user_id=u.id,
            expires_at=datetime.utcnow() + timedelta(days=14),
        ))
        db.session.add(Passkey(
            user_id=u.id, credential_id=b"cred", public_key=b"key",
        ))
        db.session.add(LoginEvent(user_id=u.id))
        db.session.add(PushSubscription(
            user_id=u.id, endpoint="https://push/x", p256dh="p", auth="a",
        ))
        # TimeClockShift FKs to StoreEmployee, not User — same class of
        # FK-block on the StoreEmployee delete.
        db.session.add(TimeClockShift(
            store_id=s.id, store_employee_id=emp.id,
            shift_date=date.today(), start_time=time(9, 0),
            end_time=time(17, 0),
        ))
        db.session.commit()
        uid, sid = u.id, s.id

        assert purge_expired_stores(db.session) == 1
        assert db.session.query(Store).filter_by(id=sid).first() is None
        # None of the child rows may survive as orphans.
        for model in (
            RecoveryCode, PasswordResetToken, RefreshToken, Passkey,
            LoginEvent, PushSubscription,
        ):
            assert (
                db.session.query(model).filter_by(user_id=uid).count() == 0
            ), f"{model.__name__} not swept on purge"
        assert (
            db.session.query(TimeClockShift).filter_by(store_id=sid).count()
            == 0
        )


# ── legacy Flask wrapper + CLI ─────────────────────────────


def test_legacy_purge_expired_stores_delegates():
    """app.purge_expired_stores hands db.session to the Service."""
    from tests._app import purge_expired_stores as legacy
    with db_session():
        # No expired stores → 0.
        assert legacy() == 0


