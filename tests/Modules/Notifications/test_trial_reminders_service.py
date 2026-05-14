"""Unit tests for Notifications.Services.trial_reminders (PR 65)."""
from datetime import datetime, timedelta

from api.Modules.Tenancy.Models import Store, StoreOwnerLink, User
from tests._app import db, db_session


def _add_store(db, *, slug, plan="trial", trial_ends_at=None,
                trial_reminder_sent_at=None):
    s = Store(
        name=slug, slug=slug, plan=plan,
        email=f"{slug}@example.com",
        trial_ends_at=trial_ends_at,
        trial_reminder_sent_at=trial_reminder_sent_at,
    )
    db.add(s); db.flush()
    return s


def _add_user(db, *, store_id, role="admin", username, email,
               notify=True, is_active=True):
    u = User(
        username=username, password_hash="x", role=role,
        full_name=username, email=email, store_id=store_id,
        notify_trial_reminders=notify, is_active=is_active,
    )
    db.add(u); db.flush()
    return u


# ── stores_due_for_reminder ────────────────────────────────


def test_due_excludes_paid_plans():
    """Only trial-plan stores qualify."""
    from tests._app import db
    from api.Modules.Notifications.Services import (
        stores_due_for_reminder,
    )
    with db_session():
        db.session.query(Store).delete()
        db.session.commit()
        now = datetime.utcnow()
        # Paid plan: never reminded.
        _add_store(db.session, slug="paid-co", plan="basic",
                   trial_ends_at=now + timedelta(days=2))
        result = stores_due_for_reminder(db.session, now)
        assert result == []


def test_due_excludes_already_reminded_stores():
    """trial_reminder_sent_at set → idempotent skip."""
    from tests._app import db
    from api.Modules.Notifications.Services import (
        stores_due_for_reminder,
    )
    with db_session():
        db.session.query(Store).delete()
        db.session.commit()
        now = datetime.utcnow()
        _add_store(
            db.session, slug="already-reminded",
            trial_ends_at=now + timedelta(days=2),
            trial_reminder_sent_at=now - timedelta(days=1),
        )
        assert stores_due_for_reminder(db.session, now) == []


def test_due_excludes_stores_outside_threshold():
    """Trial > 3 days away → not yet expiring_soon."""
    from tests._app import db
    from api.Modules.Notifications.Services import (
        stores_due_for_reminder,
    )
    with db_session():
        db.session.query(Store).delete()
        db.session.commit()
        now = datetime.utcnow()
        _add_store(
            db.session, slug="not-yet-due",
            trial_ends_at=now + timedelta(days=10),
        )
        assert stores_due_for_reminder(db.session, now) == []


def test_due_includes_stores_in_threshold():
    """Trial ≤ 3 days away + not reminded → returned."""
    from tests._app import db
    from api.Modules.Notifications.Services import (
        stores_due_for_reminder,
    )
    with db_session():
        db.session.query(Store).delete()
        db.session.commit()
        now = datetime.utcnow()
        s = _add_store(
            db.session, slug="due-tomorrow",
            trial_ends_at=now + timedelta(days=2),
        )
        result = stores_due_for_reminder(db.session, now)
        assert s in result


def test_due_excludes_no_trial_end_set():
    """A trial row without trial_ends_at can't be classified —
    skip rather than guess."""
    from tests._app import db
    from api.Modules.Notifications.Services import (
        stores_due_for_reminder,
    )
    with db_session():
        db.session.query(Store).delete()
        db.session.commit()
        now = datetime.utcnow()
        _add_store(db.session, slug="no-end-set",
                   trial_ends_at=None)
        assert stores_due_for_reminder(db.session, now) == []


# ── eligible_recipients ────────────────────────────────────


def test_recipients_includes_admin_with_email_and_opt_in():
    from tests._app import db
    from api.Modules.Notifications.Services import eligible_recipients
    with db_session():
        db.session.query(Store).delete()
        db.session.query(User).delete()
        db.session.query(StoreOwnerLink).delete()
        db.session.commit()
        s = _add_store(db.session, slug="adm-1")
        u = _add_user(
            db.session, store_id=s.id, role="admin",
            username="admin1@test.com", email="admin1@test.com",
        )
        result = eligible_recipients(db.session, s)
        assert u in result


def test_recipients_excludes_inactive_users():
    from tests._app import db
    from api.Modules.Notifications.Services import eligible_recipients
    with db_session():
        db.session.query(Store).delete()
        db.session.query(User).delete()
        db.session.query(StoreOwnerLink).delete()
        db.session.commit()
        s = _add_store(db.session, slug="inactive-store")
        _add_user(
            db.session, store_id=s.id, role="admin",
            username="dormant@test.com", email="dormant@test.com",
            is_active=False,
        )
        assert eligible_recipients(db.session, s) == []


def test_recipients_excludes_users_without_email():
    from tests._app import db
    from api.Modules.Notifications.Services import eligible_recipients
    with db_session():
        db.session.query(Store).delete()
        db.session.query(User).delete()
        db.session.query(StoreOwnerLink).delete()
        db.session.commit()
        s = _add_store(db.session, slug="no-email-co")
        _add_user(
            db.session, store_id=s.id, role="admin",
            username="no-email@test.com", email="",
        )
        assert eligible_recipients(db.session, s) == []


def test_recipients_excludes_opted_out_users():
    """notify_trial_reminders=False → skip."""
    from tests._app import db
    from api.Modules.Notifications.Services import eligible_recipients
    with db_session():
        db.session.query(Store).delete()
        db.session.query(User).delete()
        db.session.query(StoreOwnerLink).delete()
        db.session.commit()
        s = _add_store(db.session, slug="optout-co")
        _add_user(
            db.session, store_id=s.id, role="admin",
            username="optout@test.com", email="optout@test.com",
            notify=False,
        )
        assert eligible_recipients(db.session, s) == []


def test_recipients_excludes_employees():
    """Only admin + owner roles get the reminder; cashiers don't."""
    from tests._app import db
    from api.Modules.Notifications.Services import eligible_recipients
    with db_session():
        db.session.query(Store).delete()
        db.session.query(User).delete()
        db.session.query(StoreOwnerLink).delete()
        db.session.commit()
        s = _add_store(db.session, slug="emp-co")
        _add_user(
            db.session, store_id=s.id, role="employee",
            username="cashier@test.com", email="cashier@test.com",
        )
        assert eligible_recipients(db.session, s) == []


def test_recipients_includes_linked_owner_from_other_store():
    """Owner's User row sits in another store; the StoreOwnerLink
    pulls them into this store's reminder list."""
    from tests._app import db
    from api.Modules.Notifications.Services import eligible_recipients
    with db_session():
        db.session.query(Store).delete()
        db.session.query(User).delete()
        db.session.query(StoreOwnerLink).delete()
        db.session.commit()
        # Trial store the owner is linked to.
        target = _add_store(db.session, slug="target-trial-co")
        # Owner lives in another store entirely.
        owner_home = _add_store(
            db.session, slug="owner-home-co", plan="basic",
        )
        owner = _add_user(
            db.session, store_id=owner_home.id, role="owner",
            username="multi-owner@test.com",
            email="multi-owner@test.com",
        )
        db.session.add(StoreOwnerLink(
            owner_id=owner.id, store_id=target.id,
        ))
        db.session.flush()
        result = eligible_recipients(db.session, target)
        assert owner in result


def test_recipients_dedupes_admin_who_is_also_linked_owner():
    """Same User row reachable via store_id AND owner-link →
    appears once in the list."""
    from tests._app import db
    from api.Modules.Notifications.Services import eligible_recipients
    with db_session():
        db.session.query(Store).delete()
        db.session.query(User).delete()
        db.session.query(StoreOwnerLink).delete()
        db.session.commit()
        s = _add_store(db.session, slug="dedup-co")
        u = _add_user(
            db.session, store_id=s.id, role="admin",
            username="dual-role@test.com",
            email="dual-role@test.com",
        )
        # Also link the same user as owner of the same store.
        db.session.add(StoreOwnerLink(
            owner_id=u.id, store_id=s.id,
        ))
        db.session.flush()
        result = eligible_recipients(db.session, s)
        ids = [r.id for r in result]
        assert ids.count(u.id) == 1


# ── constants ──────────────────────────────────────────────


def test_subject_template_takes_days():
    from api.Modules.Notifications.Services import (
        TRIAL_REMINDER_SUBJECT,
    )
    assert TRIAL_REMINDER_SUBJECT.format(days=3) == \
        "Your DineroBook trial ends in 3 days"


def test_body_template_has_named_placeholders():
    """Body must accept the kwargs that send_trial_reminders passes."""
    from api.Modules.Notifications.Services import TRIAL_REMINDER_BODY
    rendered = TRIAL_REMINDER_BODY.format(
        name="Alice",
        store_name="Demo Store",
        trial_end_date="May 9, 2026",
        days=3,
        subscribe_url="https://x/subscribe",
        notifications_url="https://x/account/notifications",
    )
    assert "Alice" in rendered
    assert "Demo Store" in rendered
    assert "May 9, 2026" in rendered
    assert "https://x/subscribe" in rendered


# ── legacy Flask wrappers ──────────────────────────────────


# The legacy ``app._trial_reminder_recipients`` wrapper was deleted
# in Final step 2 — ``send_trial_reminders`` now calls
# ``eligible_recipients`` directly with a ``SessionLocal()``
# session. Its delegation test went with it.
