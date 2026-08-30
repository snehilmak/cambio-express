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


def test_due_defaults_now_when_omitted():
    """Calling without `now` falls back to utc_now() internally —
    exercises the module's own default branch rather than run()'s."""
    from tests._app import db
    from api.Modules.Notifications.Services import (
        stores_due_for_reminder,
    )
    with db_session():
        db.session.query(Store).delete()
        db.session.commit()
        now = datetime.utcnow()
        s = _add_store(
            db.session, slug="due-default-now-co",
            trial_ends_at=now + timedelta(days=2),
        )
        result = stores_due_for_reminder(db.session)
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


# ── run() — the cron orchestrator ───────────────────────────


def test_run_sends_email_and_stamps_dedup_flag(monkeypatch):
    """A trial store inside the reminder window with one eligible
    admin gets exactly one email, and the store's
    trial_reminder_sent_at gets stamped so a same-day rerun is a
    no-op."""
    from tests._app import db
    from api.Modules.Notifications.Services.trial_reminders import run

    sent_calls = []
    monkeypatch.setattr(
        "api.Modules.Notifications.Services.trial_reminders.send_email",
        lambda session, to_addr, subject, body, html: sent_calls.append(
            (to_addr, subject),
        ) or True,
    )

    with db_session():
        db.session.query(Store).delete()
        db.session.query(User).delete()
        db.session.commit()
        now = datetime.utcnow()
        s = _add_store(
            db.session, slug="run-due-co",
            trial_ends_at=now + timedelta(days=2),
        )
        u = _add_user(
            db.session, store_id=s.id, role="admin",
            username="run-admin@test.com", email="run-admin@test.com",
        )
        db.session.commit()

        count = run(db.session, now=now, base_url="https://x.test")
        assert count == 1
        assert sent_calls == [("run-admin@test.com",
                                "Your DineroBook trial ends in 2 days")]

        refreshed = db.session.get(Store, s.id)
        assert refreshed.trial_reminder_sent_at == now


def test_run_is_idempotent_on_second_call(monkeypatch):
    """Once trial_reminder_sent_at is stamped, a second run() for the
    same `now` sends nothing further."""
    from tests._app import db
    from api.Modules.Notifications.Services.trial_reminders import run

    sent_calls = []
    monkeypatch.setattr(
        "api.Modules.Notifications.Services.trial_reminders.send_email",
        lambda session, to_addr, subject, body, html: sent_calls.append(
            to_addr,
        ) or True,
    )

    with db_session():
        db.session.query(Store).delete()
        db.session.query(User).delete()
        db.session.commit()
        now = datetime.utcnow()
        s = _add_store(
            db.session, slug="run-idempotent-co",
            trial_ends_at=now + timedelta(days=2),
        )
        _add_user(
            db.session, store_id=s.id, role="admin",
            username="idem-admin@test.com", email="idem-admin@test.com",
        )
        db.session.commit()

        first = run(db.session, now=now, base_url="https://x.test")
        second = run(db.session, now=now, base_url="https://x.test")
        assert first == 1
        assert second == 0
        assert len(sent_calls) == 1


def test_run_skips_stores_outside_the_window(monkeypatch):
    """A trial ending 10 days out doesn't qualify — no email, no
    stamp."""
    from tests._app import db
    from api.Modules.Notifications.Services.trial_reminders import run

    sent_calls = []
    monkeypatch.setattr(
        "api.Modules.Notifications.Services.trial_reminders.send_email",
        lambda session, to_addr, subject, body, html: sent_calls.append(
            to_addr,
        ) or True,
    )

    with db_session():
        db.session.query(Store).delete()
        db.session.query(User).delete()
        db.session.commit()
        now = datetime.utcnow()
        s = _add_store(
            db.session, slug="run-not-due-co",
            trial_ends_at=now + timedelta(days=10),
        )
        _add_user(
            db.session, store_id=s.id, role="admin",
            username="not-due-admin@test.com",
            email="not-due-admin@test.com",
        )
        db.session.commit()

        count = run(db.session, now=now, base_url="https://x.test")
        assert count == 0
        assert sent_calls == []
        refreshed = db.session.get(Store, s.id)
        assert refreshed.trial_reminder_sent_at is None


def test_run_skips_paid_stores(monkeypatch):
    """A basic-plan store never qualifies, regardless of any stray
    trial_ends_at value left on the row."""
    from tests._app import db
    from api.Modules.Notifications.Services.trial_reminders import run

    sent_calls = []
    monkeypatch.setattr(
        "api.Modules.Notifications.Services.trial_reminders.send_email",
        lambda session, to_addr, subject, body, html: sent_calls.append(
            to_addr,
        ) or True,
    )

    with db_session():
        db.session.query(Store).delete()
        db.session.query(User).delete()
        db.session.commit()
        now = datetime.utcnow()
        s = _add_store(
            db.session, slug="run-paid-co", plan="basic",
            trial_ends_at=now + timedelta(days=2),
        )
        _add_user(
            db.session, store_id=s.id, role="admin",
            username="paid-admin@test.com", email="paid-admin@test.com",
        )
        db.session.commit()

        count = run(db.session, now=now, base_url="https://x.test")
        assert count == 0
        assert sent_calls == []


def test_run_does_not_stamp_store_with_no_eligible_recipients(monkeypatch):
    """A due store with zero eligible recipients (e.g. opted out)
    doesn't get stamped — so it becomes reachable again if a
    recipient later opts in within the same window."""
    from tests._app import db
    from api.Modules.Notifications.Services.trial_reminders import run

    sent_calls = []
    monkeypatch.setattr(
        "api.Modules.Notifications.Services.trial_reminders.send_email",
        lambda session, to_addr, subject, body, html: sent_calls.append(
            to_addr,
        ) or True,
    )

    with db_session():
        db.session.query(Store).delete()
        db.session.query(User).delete()
        db.session.commit()
        now = datetime.utcnow()
        s = _add_store(
            db.session, slug="run-no-recipients-co",
            trial_ends_at=now + timedelta(days=2),
        )
        _add_user(
            db.session, store_id=s.id, role="admin",
            username="optout-run@test.com", email="optout-run@test.com",
            notify=False,
        )
        db.session.commit()

        count = run(db.session, now=now, base_url="https://x.test")
        assert count == 0
        assert sent_calls == []
        refreshed = db.session.get(Store, s.id)
        assert refreshed.trial_reminder_sent_at is None


def test_run_defaults_now_and_base_url_when_omitted(monkeypatch):
    """Calling run() with no kwargs falls back to utc_now() and
    get_base_url() rather than raising — exercises the two
    ``if ... is None`` branches."""
    from tests._app import db
    from api.Modules.Notifications.Services.trial_reminders import run

    monkeypatch.setattr(
        "api.Modules.Notifications.Services.trial_reminders.send_email",
        lambda session, to_addr, subject, body, html: True,
    )

    with db_session():
        db.session.query(Store).delete()
        db.session.query(User).delete()
        db.session.commit()
        # Nothing due — just confirms no exception and a clean 0.
        assert run(db.session) == 0


def test_recipients_excludes_hard_bounced_addresses():
    """email_bounced_at set (Resend hard-bounce webhook) suppresses the
    trial reminder — same filter every other sender applies."""
    from datetime import datetime
    from tests._app import db
    from api.Modules.Notifications.Services import eligible_recipients
    with db_session():
        db.session.query(Store).delete()
        db.session.query(User).delete()
        db.session.query(StoreOwnerLink).delete()
        db.session.commit()
        s = _add_store(db.session, slug="bounce-1")
        bounced = _add_user(
            db.session, store_id=s.id, role="admin",
            username="bounced@test.com", email="bounced@test.com",
        )
        bounced.email_bounced_at = datetime(2026, 1, 1)
        ok = _add_user(
            db.session, store_id=s.id, role="admin",
            username="ok@test.com", email="ok@test.com",
        )
        db.session.commit()
        result = eligible_recipients(db.session, s)
        assert ok in result
        assert bounced not in result
