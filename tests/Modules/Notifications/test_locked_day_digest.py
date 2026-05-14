"""Unit tests for Notifications.Services.locked_day_digest —
recipient resolution for the daily-book lock fan-out."""

from api.Modules.Tenancy.Models import Store, StoreOwnerLink, User
from tests._app import db


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
    from tests._app import app as flask_app, db
    from api.Modules.Notifications.Services import (
        locked_day_digest_recipients,
    )
    with flask_app.app_context():
        # Isolate to a fresh store so seed data doesn't pollute counts.
        s = _add_store(db.session, slug="locked-test-admin")
        _add_user(db.session, store_id=s.id, role="admin",
                  username="closer", email="closer@x.com")
        db.session.commit()
        recipients = locked_day_digest_recipients(db.session, s)
    assert {u.username for u in recipients} == {"closer"}


def test_recipients_skip_employees():
    from tests._app import app as flask_app, db
    from api.Modules.Notifications.Services import (
        locked_day_digest_recipients,
    )
    with flask_app.app_context():
        s = _add_store(db.session, slug="locked-test-emp")
        _add_user(db.session, store_id=s.id, role="employee",
                  username="cashier", email="cashier@x.com")
        db.session.commit()
        recipients = locked_day_digest_recipients(db.session, s)
    assert recipients == []


def test_recipients_skip_users_with_toggle_off():
    """The opt-out toggle silences the digest for that user."""
    from tests._app import app as flask_app, db
    from api.Modules.Notifications.Services import (
        locked_day_digest_recipients,
    )
    with flask_app.app_context():
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
    from tests._app import app as flask_app, db
    from api.Modules.Notifications.Services import (
        locked_day_digest_recipients,
    )
    with flask_app.app_context():
        s = _add_store(db.session, slug="locked-test-noemail")
        _add_user(db.session, store_id=s.id, role="admin",
                  username="noemail", email="")
        db.session.commit()
        recipients = locked_day_digest_recipients(db.session, s)
    assert recipients == []


def test_recipients_skip_inactive_users():
    from tests._app import app as flask_app, db
    from api.Modules.Notifications.Services import (
        locked_day_digest_recipients,
    )
    with flask_app.app_context():
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
    from tests._app import app as flask_app, db
    from api.Modules.Notifications.Services import (
        locked_day_digest_recipients,
    )
    with flask_app.app_context():
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
    from tests._app import app as flask_app, db
    from api.Modules.Notifications.Services import (
        locked_day_digest_recipients,
    )
    with flask_app.app_context():
        s = _add_store(db.session, slug="locked-test-dup")
        u = _add_user(db.session, store_id=s.id, role="admin",
                      username="boss", email="boss@x.com")
        # Self-link as owner of the same store — defensive against
        # data shapes the seed scripts occasionally produce.
        link = StoreOwnerLink(owner_id=u.id, store_id=s.id)
        db.session.add(link); db.session.commit()

        recipients = locked_day_digest_recipients(db.session, s)
    assert len(recipients) == 1
