"""Unit tests for Auth.Services.password_reset (PR 37)."""
from datetime import datetime, timedelta

import pytest


def _seed_user(store_id, *, username, role="admin", is_active=True):
    from api.Modules.Tenancy.Models import User
    from tests._app import db
    u = User(
        store_id=store_id, username=username, role=role,
        is_active=is_active,
    )
    u.set_password("oldpass")
    db.session.add(u); db.session.commit()
    return u


# ── hash_token ──────────────────────────────────────────────


def test_hash_token_deterministic_and_hex():
    from api.Modules.Auth.Services import hash_token
    h1 = hash_token("abc")
    h2 = hash_token("abc")
    assert h1 == h2
    assert len(h1) == 64
    int(h1, 16)  # should not raise


def test_hash_token_different_inputs_diverge():
    from api.Modules.Auth.Services import hash_token
    assert hash_token("abc") != hash_token("abd")


# ── issue_password_reset_token ──────────────────────────────


def test_issue_token_returns_payload_for_admin(test_store_id):
    from api.Modules.Auth.Models import PasswordResetToken
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import (
        hash_token, issue_password_reset_token,
    )
    with flask_app.app_context():
        result = issue_password_reset_token(
            db.session, "admin@test.com",
        )
        db.session.commit()
        assert result is not None
        assert result.user.role == "admin"
        assert result.raw_token  # non-empty
        # The token row in the DB is hashed, not raw
        row = (
            db.session.query(PasswordResetToken)
              .filter_by(token_hash=hash_token(result.raw_token))
              .first()
        )
        assert row is not None
        assert row.used_at is None


def test_issue_token_rejects_employee(test_store_id):
    """Employees use admin_reset_employee_password, not the email
    flow. Service must return None for non-admin/owner roles."""
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import issue_password_reset_token
    with flask_app.app_context():
        _seed_user(
            test_store_id, username="emp@x.com", role="employee",
        )
        result = issue_password_reset_token(db.session, "emp@x.com")
    assert result is None


def test_issue_token_rejects_superadmin(test_store_id):
    """Superadmin reset goes through `flask reset-superadmin`. Email
    flow MUST refuse to issue tokens for that role (2FA bypass risk)."""
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import issue_password_reset_token
    with flask_app.app_context():
        result = issue_password_reset_token(db.session, "superadmin")
    assert result is None


def test_issue_token_rejects_inactive_user(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import issue_password_reset_token
    with flask_app.app_context():
        _seed_user(
            test_store_id, username="quit@x.com", role="admin",
            is_active=False,
        )
        result = issue_password_reset_token(db.session, "quit@x.com")
    assert result is None


def test_issue_token_returns_none_for_unknown_user():
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import issue_password_reset_token
    with flask_app.app_context():
        assert issue_password_reset_token(
            db.session, "ghost@x.com",
        ) is None


def test_issue_token_returns_none_for_empty_username():
    """Defensive — empty input shouldn't fish the DB."""
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import issue_password_reset_token
    with flask_app.app_context():
        assert issue_password_reset_token(db.session, "") is None
        assert issue_password_reset_token(db.session, "   ") is None


def test_issue_token_invalidates_prior_active_tokens(test_store_id):
    """Issuing a new token marks any still-valid existing tokens for
    the user as used so their prior reset link stops working."""
    from api.Modules.Auth.Models import PasswordResetToken
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import (
        hash_token, issue_password_reset_token,
    )
    with flask_app.app_context():
        first = issue_password_reset_token(db.session, "admin@test.com")
        db.session.commit()
        second = issue_password_reset_token(db.session, "admin@test.com")
        db.session.commit()
        # First token should now be marked used
        first_row = (
            db.session.query(PasswordResetToken)
              .filter_by(token_hash=hash_token(first.raw_token))
              .first()
        )
        assert first_row.used_at is not None
        # Second is still pending
        second_row = (
            db.session.query(PasswordResetToken)
              .filter_by(token_hash=hash_token(second.raw_token))
              .first()
        )
        assert second_row.used_at is None


# ── verify_password_reset_token ─────────────────────────────


def test_verify_returns_row_for_valid_token(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import (
        issue_password_reset_token, verify_password_reset_token,
    )
    with flask_app.app_context():
        result = issue_password_reset_token(db.session, "admin@test.com")
        db.session.commit()
        row = verify_password_reset_token(db.session, result.raw_token)
    assert row is not None


def test_verify_rejects_unknown_token():
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import verify_password_reset_token
    with flask_app.app_context():
        assert verify_password_reset_token(
            db.session, "garbage-token",
        ) is None


def test_verify_rejects_used_token(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import (
        consume_password_reset_token, issue_password_reset_token,
        verify_password_reset_token,
    )
    with flask_app.app_context():
        result = issue_password_reset_token(db.session, "admin@test.com")
        db.session.commit()
        # Consume it once
        row = verify_password_reset_token(db.session, result.raw_token)
        consume_password_reset_token(db.session, row, "newpass123")
        db.session.commit()
        # Now verify again — should refuse
        assert verify_password_reset_token(
            db.session, result.raw_token,
        ) is None


def test_verify_rejects_expired_token(test_store_id):
    from api.Modules.Auth.Models import PasswordResetToken
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import (
        issue_password_reset_token, verify_password_reset_token,
    )
    with flask_app.app_context():
        result = issue_password_reset_token(db.session, "admin@test.com")
        db.session.commit()
        # Force-expire the token row
        row = (
            db.session.query(PasswordResetToken)
              .filter_by(user_id=result.user.id).first()
        )
        row.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()
        assert verify_password_reset_token(
            db.session, result.raw_token,
        ) is None


def test_verify_rejects_empty_token():
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import verify_password_reset_token
    with flask_app.app_context():
        assert verify_password_reset_token(db.session, "") is None
        assert verify_password_reset_token(db.session, None) is None


# ── consume_password_reset_token ────────────────────────────


def test_consume_updates_password_and_marks_token_used(test_store_id):
    from api.Modules.Tenancy.Models import User
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import (
        consume_password_reset_token, issue_password_reset_token,
        verify_password_reset_token,
    )
    with flask_app.app_context():
        result = issue_password_reset_token(db.session, "admin@test.com")
        db.session.commit()
        row = verify_password_reset_token(db.session, result.raw_token)
        consume_password_reset_token(db.session, row, "brand-new-pw")
        db.session.commit()
        # New password works
        u = db.session.query(User).filter_by(
            username="admin@test.com",
        ).first()
        assert u.check_password("brand-new-pw")
        # Token is used
        assert row.used_at is not None


def test_consume_raises_if_user_gone(test_store_id):
    """Race: user deleted between verify and consume → LookupError."""
    from api.Modules.Auth.Models import PasswordResetToken
    from api.Modules.Tenancy.Models import User
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import (
        consume_password_reset_token, issue_password_reset_token,
    )
    with flask_app.app_context():
        result = issue_password_reset_token(db.session, "admin@test.com")
        db.session.commit()
        row = (
            db.session.query(PasswordResetToken)
              .filter_by(user_id=result.user.id).first()
        )
        # Simulate the user being deleted between verify and consume
        db.session.query(PasswordResetToken).delete()
        db.session.query(User).filter_by(id=result.user.id).delete()
        db.session.commit()
        with pytest.raises(LookupError):
            consume_password_reset_token(db.session, row, "x"*10)
