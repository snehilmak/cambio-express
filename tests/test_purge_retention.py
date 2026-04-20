"""Tests for purge_expired_stores() and the _STORE_OWNED_MODELS cascade
(CLAUDE.md #4).

Purge rules:
- Only hard-deletes stores where plan='inactive' AND data_retention_until
  has elapsed.
- Stores with unexpired retention timers stay put.
- Every per-store model listed in _STORE_OWNED_MODELS is wiped before the
  Store row is deleted.
- Unrelated stores (different owners / different retention state) are never
  touched.
- Superadmin platform-level data (audit log, discount codes, feature flags,
  announcements) is not scoped to a store and must never be purged here.
"""
from datetime import datetime, timedelta, date


def _make_inactive_store_due(slug="expiring-store", days_past=1):
    from app import db, Store
    s = Store(name=slug, slug=slug, email=f"{slug}@test.com",
              plan="inactive",
              canceled_at=datetime.utcnow() - timedelta(days=181),
              data_retention_until=datetime.utcnow() - timedelta(days=days_past))
    db.session.add(s); db.session.flush()
    return s


def _make_inactive_store_future(slug="still-within-window", days_future=90):
    from app import db, Store
    s = Store(name=slug, slug=slug, email=f"{slug}@test.com",
              plan="inactive",
              canceled_at=datetime.utcnow(),
              data_retention_until=datetime.utcnow() + timedelta(days=days_future))
    db.session.add(s); db.session.flush()
    return s


# ── Retention eligibility ──────────────────────────────────────────────────

def test_purge_deletes_inactive_store_past_retention(client):
    from app import db, Store, purge_expired_stores
    with client.application.app_context():
        s = _make_inactive_store_due()
        db.session.commit()
        sid = s.id
        purged = purge_expired_stores()
        assert purged == 1
        assert db.session.get(Store, sid) is None


def test_purge_skips_inactive_store_within_retention_window(client):
    from app import db, Store, purge_expired_stores
    with client.application.app_context():
        s = _make_inactive_store_future(days_future=60)
        db.session.commit()
        sid = s.id
        purged = purge_expired_stores()
        assert purged == 0
        assert db.session.get(Store, sid) is not None


def test_purge_skips_active_store_even_with_past_retention(client):
    """plan != 'inactive' => never purge, even if data_retention_until is set."""
    from app import db, Store, purge_expired_stores
    with client.application.app_context():
        s = Store(name="Paying Store", slug="paying-store",
                  email="p@test.com", plan="pro",
                  data_retention_until=datetime.utcnow() - timedelta(days=10))
        db.session.add(s); db.session.commit()
        sid = s.id
        purged = purge_expired_stores()
        assert purged == 0
        assert db.session.get(Store, sid) is not None


def test_purge_skips_inactive_store_with_null_retention(client):
    """No retention timer => cancellation never committed; don't delete."""
    from app import db, Store, purge_expired_stores
    with client.application.app_context():
        s = Store(name="No Timer", slug="no-timer", email="n@test.com",
                  plan="inactive", data_retention_until=None)
        db.session.add(s); db.session.commit()
        sid = s.id
        assert purge_expired_stores() == 0
        assert db.session.get(Store, sid) is not None


def test_purge_returns_zero_when_nothing_to_purge(client):
    from app import purge_expired_stores
    with client.application.app_context():
        assert purge_expired_stores() == 0


# ── Cascading deletion ──────────────────────────────────────────────────────

def test_purge_cascades_all_store_owned_tables(client):
    """Every per-store table must be empty of the expired store's rows."""
    from app import (
        db, Store, User, Customer, Transfer, TransferAudit, StoreEmployee,
        ACHBatch, DailyReport, DailyDrop, purge_expired_stores,
    )
    with client.application.app_context():
        s = _make_inactive_store_due(slug="cascade-store")
        db.session.flush()
        sid = s.id

        # Seed one row per model pinned to this store.
        admin = User(store_id=sid, username="cascade-admin",
                     full_name="A", role="admin")
        admin.set_password("x!")
        db.session.add(admin); db.session.flush()
        emp = StoreEmployee(store_id=sid, name="Eddie")
        db.session.add(emp); db.session.flush()
        c = Customer(store_id=sid, full_name="Carl",
                     phone_country="+1", phone_number="5559999")
        db.session.add(c); db.session.flush()
        t = Transfer(store_id=sid, created_by=admin.id, customer_id=c.id,
                     send_date=date(2026, 1, 1), company="Intermex",
                     sender_name="Carl", send_amount=100.0, fee=5.0,
                     federal_tax=1.0, batch_id="B-1")
        db.session.add(t); db.session.flush()
        db.session.add(TransferAudit(store_id=sid, transfer_id=t.id,
                                     user_id=admin.id, action="created",
                                     summary="seed"))
        db.session.add(ACHBatch(store_id=sid, ach_date=date(2026, 1, 2),
                                company="Intermex", batch_ref="B-1",
                                ach_amount=101.0))
        db.session.add(DailyReport(store_id=sid, report_date=date(2026, 1, 1),
                                   money_transfer=100.0))
        from datetime import time as dtime
        db.session.add(DailyDrop(store_id=sid, report_date=date(2026, 1, 1),
                                 drop_time=dtime(10, 0), amount=50.0))
        db.session.commit()

        # Sanity: rows exist before purge.
        assert User.query.filter_by(store_id=sid).count() == 1
        assert Transfer.query.filter_by(store_id=sid).count() == 1
        assert TransferAudit.query.filter_by(store_id=sid).count() == 1
        assert ACHBatch.query.filter_by(store_id=sid).count() == 1
        assert DailyReport.query.filter_by(store_id=sid).count() == 1
        assert DailyDrop.query.filter_by(store_id=sid).count() == 1
        assert Customer.query.filter_by(store_id=sid).count() == 1
        assert StoreEmployee.query.filter_by(store_id=sid).count() == 1

        assert purge_expired_stores() == 1

        # And they're all gone afterwards.
        assert db.session.get(Store, sid) is None
        assert User.query.filter_by(store_id=sid).count() == 0
        assert Transfer.query.filter_by(store_id=sid).count() == 0
        assert TransferAudit.query.filter_by(store_id=sid).count() == 0
        assert ACHBatch.query.filter_by(store_id=sid).count() == 0
        assert DailyReport.query.filter_by(store_id=sid).count() == 0
        assert DailyDrop.query.filter_by(store_id=sid).count() == 0
        assert Customer.query.filter_by(store_id=sid).count() == 0
        assert StoreEmployee.query.filter_by(store_id=sid).count() == 0


def test_purge_transfer_audit_before_transfer_order(client):
    """_STORE_OWNED_MODELS lists TransferAudit BEFORE Transfer — otherwise
    the FK transfer_audit.transfer_id → transfer.id would block deletion."""
    from app import _STORE_OWNED_MODELS
    assert _STORE_OWNED_MODELS.index("TransferAudit") < \
           _STORE_OWNED_MODELS.index("Transfer")


def test_purge_customer_and_user_listed(client):
    """CLAUDE.md says new per-store models must be added to _STORE_OWNED_MODELS.
    Regression guard for the critical ones."""
    from app import _STORE_OWNED_MODELS
    for required in ["User", "Customer", "Transfer", "TransferAudit",
                     "ACHBatch", "DailyReport", "StoreEmployee",
                     "StoreOwnerLink", "OwnerInviteCode"]:
        assert required in _STORE_OWNED_MODELS, \
            f"{required} missing from _STORE_OWNED_MODELS — store purge " \
            f"would leave orphaned rows"


def test_purge_cascades_referral_models_with_custom_fk(client):
    """ReferralCode/ReferralRedemption use owner_store_id / referee_store_id,
    not store_id. _STORE_FK_OVERRIDES must route the purge to the right
    column or the whole purge aborts with an InvalidRequestError."""
    from app import (
        db, ReferralCode, ReferralRedemption, purge_expired_stores,
        _STORE_FK_OVERRIDES,
    )
    # Override map must not lie.
    assert _STORE_FK_OVERRIDES.get("ReferralCode") == "owner_store_id"
    assert _STORE_FK_OVERRIDES.get("ReferralRedemption") == "referee_store_id"

    with client.application.app_context():
        doomed = _make_inactive_store_due(slug="referral-doomed")
        db.session.flush()
        sid = doomed.id
        db.session.add(ReferralCode(code="DOOMED1", owner_store_id=sid))
        db.session.flush()
        rc_id = ReferralCode.query.filter_by(owner_store_id=sid).one().id
        # Redemption needs a referee store too.
        referee = _make_inactive_store_due(slug="referral-referee", days_past=2)
        db.session.flush()
        db.session.add(ReferralRedemption(
            referral_code_id=rc_id, referee_store_id=referee.id,
        ))
        db.session.commit()

        assert ReferralCode.query.filter_by(owner_store_id=sid).count() == 1
        assert ReferralRedemption.query.filter_by(
            referee_store_id=referee.id).count() == 1

        assert purge_expired_stores() == 2

        assert ReferralCode.query.filter_by(owner_store_id=sid).count() == 0
        assert ReferralRedemption.query.filter_by(
            referee_store_id=referee.id).count() == 0


# ── Isolation ───────────────────────────────────────────────────────────────

def test_purge_does_not_touch_unrelated_stores(client):
    """Active stores + their data must survive a purge of a different store."""
    from app import db, Store, User, Transfer, purge_expired_stores
    with client.application.app_context():
        doomed = _make_inactive_store_due(slug="doomed")
        survivor = Store(name="Survivor", slug="survivor-store",
                         email="s@test.com", plan="pro")
        db.session.add(survivor); db.session.flush()

        admin = User(store_id=survivor.id, username="survivor-admin",
                     full_name="S", role="admin")
        admin.set_password("x!"); db.session.add(admin); db.session.flush()
        db.session.add(Transfer(
            store_id=survivor.id, created_by=admin.id,
            send_date=date(2026, 1, 1), company="Intermex",
            sender_name="Live Sender", send_amount=50.0, fee=1.0,
            federal_tax=0.5, batch_id="SURVIVE-1",
        ))
        db.session.commit()
        sid_survivor = survivor.id

        assert purge_expired_stores() == 1

        # Survivor intact.
        assert db.session.get(Store, sid_survivor) is not None
        assert User.query.filter_by(store_id=sid_survivor).count() == 1
        assert Transfer.query.filter_by(store_id=sid_survivor).count() == 1


def test_purge_preserves_superadmin_and_other_platform_data(client):
    """Superadmin, feature flags, audit logs, announcements, discount codes
    have no store_id — the purge must leave them untouched."""
    from app import (
        db, Store, User, purge_expired_stores, FeatureFlag,
        SuperadminAuditLog, Announcement, DiscountCode,
    )
    with client.application.app_context():
        _make_inactive_store_due(slug="doomed-platform-test")
        db.session.add(FeatureFlag(key="bank_sync", label="Bank sync",
                                   enabled_by_default=True))
        db.session.add(SuperadminAuditLog(admin_id=None, admin_name="sa",
                                          action="manual_test",
                                          target_type="store",
                                          target_id="1", details=""))
        db.session.add(Announcement(message="scheduled maintenance",
                                    level="info", is_active=True))
        db.session.add(DiscountCode(code="TEST10", label="10% off",
                                    percent_off=10, duration="once"))
        db.session.commit()

        purge_expired_stores()

        # Superadmin is a store-less user; must survive.
        assert User.query.filter_by(username="superadmin",
                                    store_id=None).count() == 1
        assert FeatureFlag.query.filter_by(key="bank_sync").count() == 1
        assert SuperadminAuditLog.query.count() >= 1
        assert Announcement.query.count() == 1
        assert DiscountCode.query.filter_by(code="TEST10").count() == 1


def test_purge_handles_multiple_expired_stores_in_one_run(client):
    from app import db, Store, purge_expired_stores
    with client.application.app_context():
        _make_inactive_store_due(slug="doomed-1")
        _make_inactive_store_due(slug="doomed-2", days_past=30)
        _make_inactive_store_future(slug="safe-1", days_future=30)
        db.session.commit()
        purged = purge_expired_stores()
        assert purged == 2
        remaining = {s.slug for s in Store.query.all()}
        assert "doomed-1" not in remaining
        assert "doomed-2" not in remaining
        assert "safe-1" in remaining
