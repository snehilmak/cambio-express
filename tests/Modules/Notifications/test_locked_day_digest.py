"""Unit tests for Notifications.Services.locked_day_digest —
recipient resolution for the daily-book lock fan-out."""

from api.Modules.Tenancy.Models import Store, StoreOwnerLink, User
from tests._app import db, db_session


def _add_store(db, *, slug):
    s = Store(name=slug, slug=slug, plan="basic",
              email=f"{slug}@example.com")
    db.add(s); db.flush()
    return s


def _add_user(db, *, store_id, role, username, email,
              notify_digest=True, is_active=True):
    u = User(
        username=username, password_hash="x", role=role,
        full_name=username, email=email, store_id=store_id,
        notify_locked_day_digest=notify_digest, is_active=is_active,
    )
    db.add(u); db.flush()
    return u


# ── eligible_recipients ────────────────────────────────────


def test_recipients_include_store_admin():
    from tests._app import db
    from api.Modules.Notifications.Services import (
        locked_day_digest_recipients,
    )
    with db_session():
        # Isolate to a fresh store so seed data doesn't pollute counts.
        s = _add_store(db.session, slug="locked-test-admin")
        _add_user(db.session, store_id=s.id, role="admin",
                  username="closer", email="closer@x.com")
        db.session.commit()
        recipients = locked_day_digest_recipients(db.session, s)
    assert {u.username for u in recipients} == {"closer"}


def test_recipients_skip_employees():
    from tests._app import db
    from api.Modules.Notifications.Services import (
        locked_day_digest_recipients,
    )
    with db_session():
        s = _add_store(db.session, slug="locked-test-emp")
        _add_user(db.session, store_id=s.id, role="employee",
                  username="cashier", email="cashier@x.com")
        db.session.commit()
        recipients = locked_day_digest_recipients(db.session, s)
    assert recipients == []


def test_recipients_skip_users_with_toggle_off():
    """The opt-out toggle silences the digest for that user."""
    from tests._app import db
    from api.Modules.Notifications.Services import (
        locked_day_digest_recipients,
    )
    with db_session():
        s = _add_store(db.session, slug="locked-test-off")
        _add_user(db.session, store_id=s.id, role="admin",
                  username="silenced", email="silenced@x.com",
                  notify_digest=False)
        _add_user(db.session, store_id=s.id, role="admin",
                  username="loud", email="loud@x.com",
                  notify_digest=True)
        db.session.commit()
        recipients = locked_day_digest_recipients(db.session, s)
    assert {u.username for u in recipients} == {"loud"}


def test_recipients_skip_users_without_email():
    from tests._app import db
    from api.Modules.Notifications.Services import (
        locked_day_digest_recipients,
    )
    with db_session():
        s = _add_store(db.session, slug="locked-test-noemail")
        _add_user(db.session, store_id=s.id, role="admin",
                  username="noemail", email="")
        db.session.commit()
        recipients = locked_day_digest_recipients(db.session, s)
    assert recipients == []


def test_recipients_skip_inactive_users():
    from tests._app import db
    from api.Modules.Notifications.Services import (
        locked_day_digest_recipients,
    )
    with db_session():
        s = _add_store(db.session, slug="locked-test-inactive")
        _add_user(db.session, store_id=s.id, role="admin",
                  username="exadmin", email="ex@x.com",
                  is_active=False)
        db.session.commit()
        recipients = locked_day_digest_recipients(db.session, s)
    assert recipients == []


def test_recipients_pick_up_linked_owners():
    """Multi-store owner pattern — owner's User row lives in another
    store but StoreOwnerLink connects them in."""
    from tests._app import db
    from api.Modules.Notifications.Services import (
        locked_day_digest_recipients,
    )
    with db_session():
        # Store A — has the daily book being locked.
        store_a = _add_store(db.session, slug="locked-store-a")
        # Store B — where the owner's user row actually lives.
        store_b = _add_store(db.session, slug="locked-store-b")
        owner = _add_user(db.session, store_id=store_b.id, role="owner",
                          username="multi-owner",
                          email="multi-owner@x.com")
        link = StoreOwnerLink(owner_id=owner.id, store_id=store_a.id)
        db.session.add(link); db.session.commit()

        recipients = locked_day_digest_recipients(db.session, store_a)
    assert {u.username for u in recipients} == {"multi-owner"}


def test_recipients_dedup_owner_admin_overlap():
    """Same user could be both admin of this store AND linked owner —
    they should only get one email."""
    from tests._app import db
    from api.Modules.Notifications.Services import (
        locked_day_digest_recipients,
    )
    with db_session():
        s = _add_store(db.session, slug="locked-test-dup")
        u = _add_user(db.session, store_id=s.id, role="admin",
                      username="boss", email="boss@x.com")
        # Self-link as owner of the same store — defensive against
        # data shapes the seed scripts occasionally produce.
        link = StoreOwnerLink(owner_id=u.id, store_id=s.id)
        db.session.add(link); db.session.commit()

        recipients = locked_day_digest_recipients(db.session, s)
    assert len(recipients) == 1


# ── run() — the SMTP fanout orchestrator ────────────────────


def _add_report(db, *, store_id, report_date, locked_by=None):
    from api.Modules.DailyBook.Models import DailyReport
    r = DailyReport(store_id=store_id, report_date=report_date)
    if locked_by is not None:
        r.locked_by = locked_by
    db.add(r); db.flush()
    return r


def test_run_returns_zero_for_none_report():
    from api.Modules.Notifications.Services.locked_day_digest import run
    with db_session():
        assert run(db.session, None) == 0


def test_run_returns_zero_when_store_id_missing():
    """A transient (never-flushed) report with no store_id — the
    guard clause short-circuits before any DB write is attempted."""
    from datetime import date
    from api.Modules.DailyBook.Models import DailyReport
    from api.Modules.Notifications.Services.locked_day_digest import run
    with db_session():
        r = DailyReport(store_id=None, report_date=date.today())
        assert run(db.session, r) == 0


def test_run_returns_zero_when_store_row_gone():
    """store_id points at a Store row that no longer exists (e.g.
    deleted between the lock commit and the worker running)."""
    from datetime import date
    from api.Modules.Notifications.Services.locked_day_digest import run
    with db_session():
        r = _add_report(db.session, store_id=999999, report_date=date.today())
        assert run(db.session, r) == 0


def test_run_sends_digest_to_eligible_recipient(monkeypatch):
    from datetime import date
    from api.Modules.Notifications.Services.locked_day_digest import run

    sent_calls = []
    monkeypatch.setattr(
        "api.Modules.Notifications.Services.locked_day_digest.send_email",
        lambda session, to_addr, subject, body, html: sent_calls.append(
            (to_addr, subject),
        ) or True,
    )

    with db_session():
        s = _add_store(db.session, slug="run-locked-co")
        admin = _add_user(
            db.session, store_id=s.id, role="admin",
            username="run-closer", email="run-closer@x.com",
        )
        db.session.commit()
        r = _add_report(
            db.session, store_id=s.id, report_date=date(2026, 3, 1),
            locked_by=admin.id,
        )
        db.session.commit()

        count = run(db.session, r, base_url="https://x.test")
        assert count == 1
        assert sent_calls == [
            ("run-closer@x.com",
             "Daily book locked — run-locked-co, March 01, 2026"),
        ]


def test_run_counts_only_successful_sends(monkeypatch):
    """send_email returning False (e.g. bounce suppression) does not
    increment the sent counter."""
    from datetime import date
    from api.Modules.Notifications.Services.locked_day_digest import run

    monkeypatch.setattr(
        "api.Modules.Notifications.Services.locked_day_digest.send_email",
        lambda session, to_addr, subject, body, html: False,
    )

    with db_session():
        s = _add_store(db.session, slug="run-locked-fail-co")
        _add_user(
            db.session, store_id=s.id, role="admin",
            username="fail-closer", email="fail-closer@x.com",
        )
        db.session.commit()
        r = _add_report(db.session, store_id=s.id, report_date=date(2026, 3, 1))
        db.session.commit()

        assert run(db.session, r, base_url="https://x.test") == 0


def test_run_handles_recipient_query_failure(monkeypatch):
    """eligible_recipients raising is caught and logged — the lock
    route must not fail because of a digest-side error."""
    from datetime import date
    from api.Modules.Notifications.Services import locked_day_digest as mod

    def _boom(session, store):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(mod, "eligible_recipients", _boom)

    with db_session():
        s = _add_store(db.session, slug="run-locked-boom-co")
        db.session.commit()
        r = _add_report(db.session, store_id=s.id, report_date=date(2026, 3, 1))
        db.session.commit()

        assert mod.run(db.session, r, base_url="https://x.test") == 0


def test_run_continues_after_one_recipient_send_fails(monkeypatch):
    """One recipient's send raising an exception doesn't stop the
    fan-out to the rest of the list."""
    from datetime import date
    from api.Modules.Notifications.Services.locked_day_digest import run

    calls = []

    def _flaky_send(session, to_addr, subject, body, html):
        if to_addr == "flaky@x.com":
            raise RuntimeError("smtp exploded")
        calls.append(to_addr)
        return True

    monkeypatch.setattr(
        "api.Modules.Notifications.Services.locked_day_digest.send_email",
        _flaky_send,
    )

    with db_session():
        s = _add_store(db.session, slug="run-locked-partial-co")
        _add_user(
            db.session, store_id=s.id, role="admin",
            username="flaky", email="flaky@x.com",
        )
        _add_user(
            db.session, store_id=s.id, role="admin",
            username="steady", email="steady@x.com",
        )
        db.session.commit()
        r = _add_report(db.session, store_id=s.id, report_date=date(2026, 3, 1))
        db.session.commit()

        count = run(db.session, r, base_url="https://x.test")
        assert count == 1
        assert calls == ["steady@x.com"]


def test_run_falls_back_to_generic_locked_by_label(monkeypatch):
    """locked_by is None (or the user row is gone) → 'an admin'
    fallback in the email body, not a crash."""
    from datetime import date
    from api.Modules.Notifications.Services.locked_day_digest import run

    bodies = []
    monkeypatch.setattr(
        "api.Modules.Notifications.Services.locked_day_digest.send_email",
        lambda session, to_addr, subject, body, html: bodies.append(body) or True,
    )

    with db_session():
        s = _add_store(db.session, slug="run-locked-noname-co")
        _add_user(
            db.session, store_id=s.id, role="admin",
            username="reader", email="reader@x.com",
        )
        db.session.commit()
        r = _add_report(
            db.session, store_id=s.id, report_date=date(2026, 3, 1),
            locked_by=None,
        )
        db.session.commit()

        assert run(db.session, r, base_url="https://x.test") == 1
        assert "an admin" in bodies[0]


# ── send_locked_day_digest() — the RQ worker entry point ────


def test_send_locked_day_digest_worker_sends(monkeypatch):
    from datetime import date
    from api.Modules.Notifications.Services.locked_day_digest import (
        send_locked_day_digest,
    )

    monkeypatch.setattr(
        "api.Modules.Notifications.Services.locked_day_digest.send_email",
        lambda session, to_addr, subject, body, html: True,
    )

    with db_session():
        s = _add_store(db.session, slug="worker-locked-co")
        _add_user(
            db.session, store_id=s.id, role="admin",
            username="worker-closer", email="worker-closer@x.com",
        )
        db.session.commit()
        r = _add_report(db.session, store_id=s.id, report_date=date(2026, 3, 1))
        db.session.commit()
        report_id = r.id

    assert send_locked_day_digest(report_id) == 1


def test_send_locked_day_digest_worker_missing_report():
    """report_id points at a row that's gone by the time the worker
    runs (rare race) — returns 0 instead of raising."""
    from api.Modules.Notifications.Services.locked_day_digest import (
        send_locked_day_digest,
    )
    assert send_locked_day_digest(999999) == 0


def test_recipients_skip_hard_bounced_addresses():
    """A user whose address hard-bounced (email_bounced_at set by the
    Resend webhook) must not receive the digest — same suppression
    every other sender applies."""
    from datetime import datetime
    from tests._app import db
    from api.Modules.Notifications.Services import (
        locked_day_digest_recipients,
    )
    with db_session():
        s = _add_store(db.session, slug="locked-test-bounced")
        bounced = _add_user(db.session, store_id=s.id, role="admin",
                            username="bounced", email="bounced@x.com")
        bounced.email_bounced_at = datetime(2026, 1, 1)
        _add_user(db.session, store_id=s.id, role="admin",
                  username="deliverable", email="ok@x.com")
        db.session.commit()
        recipients = locked_day_digest_recipients(db.session, s)
    assert {u.username for u in recipients} == {"deliverable"}
