"""Unit tests for Notifications.Services.broadcasts (PR 66)."""
from datetime import datetime

from api.Modules.Tenancy.Models import User
from tests._app import db, db_session


def _add_user(db, *, store_id=1, role="admin",
               username, email, notify_announcement=True,
               is_active=True, email_bounced_at=None):
    u = User(
        username=username, password_hash="x", role=role,
        full_name=username, email=email, store_id=store_id,
        notify_announcement_email=notify_announcement,
        is_active=is_active,
        email_bounced_at=email_bounced_at,
    )
    db.add(u); db.flush()
    return u


# ── derive_broadcast_subject ───────────────────────────────


def test_subject_uses_first_line():
    from api.Modules.Notifications.Services import derive_broadcast_subject
    assert derive_broadcast_subject(
        "Holiday hours start Monday\nPlease plan accordingly.",
    ) == "Holiday hours start Monday"


def test_subject_strips_outer_whitespace_only():
    """Legacy strips outer whitespace from the whole message
    before splitting on newline. Trailing whitespace on the
    first line is preserved (matches the legacy behavior — fixing
    that is out of scope for a behavior-preserving extraction)."""
    from api.Modules.Notifications.Services import derive_broadcast_subject
    # Leading whitespace gets stripped by the outer .strip()
    assert derive_broadcast_subject(
        "   Welcome back!\nDetails below.",
    ) == "Welcome back!"
    # Trailing whitespace on the first line stays on the subject
    assert derive_broadcast_subject(
        "   Welcome back!   \nDetails below.",
    ) == "Welcome back!   "


def test_subject_caps_at_100_chars():
    from api.Modules.Notifications.Services import derive_broadcast_subject
    long_line = "A" * 250
    result = derive_broadcast_subject(long_line)
    assert len(result) == 100
    assert result == "A" * 100


def test_subject_falls_back_when_blank():
    """Empty / whitespace-only message → generic subject so the
    inbox preview stays clean."""
    from api.Modules.Notifications.Services import derive_broadcast_subject
    assert derive_broadcast_subject("") == "A message from DineroBook"
    assert derive_broadcast_subject("   ") == "A message from DineroBook"
    assert derive_broadcast_subject("\n\n") == "A message from DineroBook"
    assert derive_broadcast_subject(None) == "A message from DineroBook"


def test_subject_handles_single_line_no_newline():
    from api.Modules.Notifications.Services import derive_broadcast_subject
    assert derive_broadcast_subject(
        "Quick heads-up about pricing.",
    ) == "Quick heads-up about pricing."


# ── BROADCAST_PLAIN_BODY ───────────────────────────────────


def test_plain_body_has_required_placeholders():
    """Body must accept the kwargs the orchestrator passes."""
    from api.Modules.Notifications.Services import BROADCAST_PLAIN_BODY
    rendered = BROADCAST_PLAIN_BODY.format(
        message="The system will be down Monday at 3am for maintenance.",
        base_url="https://dinerobook.com",
        notifications_url="https://dinerobook.com/account/notifications",
    )
    assert "down Monday" in rendered
    assert "https://dinerobook.com" in rendered
    assert "https://dinerobook.com/account/notifications" in rendered
    assert "DineroBook" in rendered


# ── broadcast_eligible_recipients ──────────────────────────


def test_recipients_includes_active_opted_in_user():
    from tests._app import db
    from api.Modules.Notifications.Services import (
        broadcast_eligible_recipients,
    )
    with db_session():
        db.session.query(User).delete()
        db.session.commit()
        u = _add_user(
            db.session,
            username="active@test.com",
            email="active@test.com",
        )
        result = broadcast_eligible_recipients(db.session)
        assert u in result


def test_recipients_excludes_inactive():
    from tests._app import db
    from api.Modules.Notifications.Services import (
        broadcast_eligible_recipients,
    )
    with db_session():
        db.session.query(User).delete()
        db.session.commit()
        _add_user(
            db.session,
            username="inactive@test.com",
            email="inactive@test.com",
            is_active=False,
        )
        assert broadcast_eligible_recipients(db.session) == []


def test_recipients_excludes_no_email():
    from tests._app import db
    from api.Modules.Notifications.Services import (
        broadcast_eligible_recipients,
    )
    with db_session():
        db.session.query(User).delete()
        db.session.commit()
        _add_user(
            db.session,
            username="no-email-user",
            email="",
        )
        assert broadcast_eligible_recipients(db.session) == []


def test_recipients_excludes_opted_out():
    """notify_announcement_email=False → skip."""
    from tests._app import db
    from api.Modules.Notifications.Services import (
        broadcast_eligible_recipients,
    )
    with db_session():
        db.session.query(User).delete()
        db.session.commit()
        _add_user(
            db.session,
            username="optout@test.com",
            email="optout@test.com",
            notify_announcement=False,
        )
        assert broadcast_eligible_recipients(db.session) == []


def test_recipients_excludes_bounced_addresses():
    """email_bounced_at set → drop. Resend's reputation depends on
    not retrying hard-bounced addresses."""
    from tests._app import db
    from api.Modules.Notifications.Services import (
        broadcast_eligible_recipients,
    )
    with db_session():
        db.session.query(User).delete()
        db.session.commit()
        _add_user(
            db.session,
            username="bounced@test.com",
            email="bounced@test.com",
            email_bounced_at=datetime.utcnow(),
        )
        assert broadcast_eligible_recipients(db.session) == []


def test_recipients_includes_all_roles():
    """admins, owners, employees — all get announcements (the
    eligibility filter doesn't role-gate the way trial reminders
    do)."""
    from tests._app import db
    from api.Modules.Notifications.Services import (
        broadcast_eligible_recipients,
    )
    with db_session():
        db.session.query(User).delete()
        db.session.commit()
        admin = _add_user(
            db.session, role="admin",
            username="adm@test.com", email="adm@test.com",
        )
        owner = _add_user(
            db.session, role="owner",
            username="own@test.com", email="own@test.com",
        )
        employee = _add_user(
            db.session, role="employee",
            username="emp@test.com", email="emp@test.com",
        )
        result = broadcast_eligible_recipients(db.session)
        assert admin in result
        assert owner in result
        assert employee in result


# ── targeting (PR B) ───────────────────────────────────────


def test_recipients_restricted_to_target_stores():
    """A targeted announcement only emails users in the target
    stores; users in other stores are excluded even when opted in."""
    from tests._app import db
    from api.Modules.Notifications.Services import (
        broadcast_eligible_recipients,
    )
    with db_session():
        db.session.query(User).delete()
        db.session.commit()
        in_store = _add_user(
            db.session, store_id=1,
            username="in@test.com", email="in@test.com",
        )
        out_store = _add_user(
            db.session, store_id=2,
            username="out@test.com", email="out@test.com",
        )
        result = broadcast_eligible_recipients(db.session, store_ids=[1])
        assert in_store in result
        assert out_store not in result


def test_recipients_none_store_ids_reaches_everyone():
    """store_ids=None (a global announcement) keeps the old
    behaviour — every opted-in user regardless of store."""
    from tests._app import db
    from api.Modules.Notifications.Services import (
        broadcast_eligible_recipients,
    )
    with db_session():
        db.session.query(User).delete()
        db.session.commit()
        u1 = _add_user(
            db.session, store_id=1,
            username="g1@test.com", email="g1@test.com",
        )
        u2 = _add_user(
            db.session, store_id=2,
            username="g2@test.com", email="g2@test.com",
        )
        result = broadcast_eligible_recipients(db.session, store_ids=None)
        assert u1 in result
        assert u2 in result
