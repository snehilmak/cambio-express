"""Unit tests for Auth.Services.totp (PR 41)."""
from datetime import datetime

import pyotp


def _seed_user(role="employee", *, totp_secret=None, totp_enrolled_at=None):
    from api.Modules.Tenancy.Models import Store, User
    from tests._app import db
    s = Store.query.filter_by(slug="test-store").first()
    u = User(
        store_id=s.id, username=f"u-{role}-{datetime.utcnow().timestamp()}@x.com",
        role=role,
        totp_secret=totp_secret,
        totp_enrolled_at=totp_enrolled_at,
    )
    u.set_password("p")
    db.session.add(u); db.session.commit()
    return u


# ── needs_totp ──────────────────────────────────────────────


def test_needs_totp_true_for_superadmin():
    from tests._app import app as flask_app
    from api.Modules.Auth.Services import needs_totp
    with flask_app.app_context():
        u = _seed_user(role="superadmin")
        assert needs_totp(u) is True


def test_needs_totp_false_for_other_roles():
    from tests._app import app as flask_app
    from api.Modules.Auth.Services import needs_totp
    with flask_app.app_context():
        for role in ("admin", "owner", "employee"):
            u = _seed_user(role=role)
            assert needs_totp(u) is False, f"{role} should not need TOTP"


def test_needs_totp_false_for_none():
    from api.Modules.Auth.Services import needs_totp
    assert needs_totp(None) is False


# ── is_enrolled ─────────────────────────────────────────────


def test_is_enrolled_requires_secret_and_timestamp():
    from tests._app import app as flask_app
    from api.Modules.Auth.Services import is_enrolled
    with flask_app.app_context():
        secret = pyotp.random_base32()
        u_done = _seed_user(
            role="superadmin", totp_secret=secret,
            totp_enrolled_at=datetime.utcnow(),
        )
        u_started = _seed_user(role="superadmin", totp_secret=secret)
        u_blank = _seed_user(role="superadmin")
        assert is_enrolled(u_done) is True
        assert is_enrolled(u_started) is False
        assert is_enrolled(u_blank) is False


def test_is_enrolled_handles_none():
    from api.Modules.Auth.Services import is_enrolled
    assert is_enrolled(None) is False


# ── verify_totp_token ───────────────────────────────────────


def test_verify_totp_token_accepts_current_code():
    from tests._app import app as flask_app
    from api.Modules.Auth.Services import verify_totp_token
    with flask_app.app_context():
        secret = pyotp.random_base32()
        u = _seed_user(role="superadmin", totp_secret=secret)
        current = pyotp.TOTP(secret).now()
        assert verify_totp_token(u, current) is True


def test_verify_totp_token_rejects_wrong_code():
    from tests._app import app as flask_app
    from api.Modules.Auth.Services import verify_totp_token
    with flask_app.app_context():
        u = _seed_user(role="superadmin", totp_secret=pyotp.random_base32())
        assert verify_totp_token(u, "000000") is False


def test_verify_totp_token_handles_no_secret():
    from tests._app import app as flask_app
    from api.Modules.Auth.Services import verify_totp_token
    with flask_app.app_context():
        u = _seed_user(role="superadmin")
        assert verify_totp_token(u, "123456") is False


def test_verify_totp_token_handles_none_user():
    from api.Modules.Auth.Services import verify_totp_token
    assert verify_totp_token(None, "123456") is False


def test_verify_totp_token_handles_empty_token():
    from tests._app import app as flask_app
    from api.Modules.Auth.Services import verify_totp_token
    with flask_app.app_context():
        u = _seed_user(role="superadmin", totp_secret=pyotp.random_base32())
        assert verify_totp_token(u, "") is False


def test_verify_totp_token_strips_whitespace():
    from tests._app import app as flask_app
    from api.Modules.Auth.Services import verify_totp_token
    with flask_app.app_context():
        secret = pyotp.random_base32()
        u = _seed_user(role="superadmin", totp_secret=secret)
        current = pyotp.TOTP(secret).now()
        # Whitespace-padded should still verify.
        assert verify_totp_token(u, f"  {current}  ") is True


# ── hash_recovery_code / format_recovery_code ───────────────


def test_hash_recovery_code_is_normalised():
    """Differences in casing, hyphens, and whitespace must produce
    the same hash so a copy-paste with formatting doesn't lock the
    user out."""
    from api.Modules.Auth.Services import hash_recovery_code
    h1 = hash_recovery_code("abcd-efgh")
    h2 = hash_recovery_code("ABCD-EFGH")
    h3 = hash_recovery_code("abcdefgh")
    h4 = hash_recovery_code("  ABCD-EFGH  ")
    assert h1 == h2 == h3 == h4


def test_format_recovery_code():
    from api.Modules.Auth.Services import format_recovery_code
    assert format_recovery_code("abcdefgh") == "ABCD-EFGH"
    assert format_recovery_code("ABCD-EFGH") == "ABCD-EFGH"
    # Other lengths pass through.
    assert format_recovery_code("123") == "123"


# ── generate_recovery_codes ─────────────────────────────────


def test_generate_recovery_codes_creates_count_rows():
    from api.Modules.Auth.Models import RecoveryCode
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import generate_recovery_codes
    with flask_app.app_context():
        u = _seed_user(role="superadmin")
        codes = generate_recovery_codes(db.session, u)
        db.session.commit()
        assert len(codes) == 10
        rows = db.session.query(RecoveryCode).filter_by(user_id=u.id).all()
        assert len(rows) == 10


def test_generate_recovery_codes_replaces_existing():
    from api.Modules.Auth.Models import RecoveryCode
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import generate_recovery_codes
    with flask_app.app_context():
        u = _seed_user(role="superadmin")
        first = generate_recovery_codes(db.session, u)
        db.session.commit()
        second = generate_recovery_codes(db.session, u)
        db.session.commit()
        # No overlap (1-in-2^32 chance, negligible)
        assert set(first).isdisjoint(set(second))
        rows = db.session.query(RecoveryCode).filter_by(user_id=u.id).all()
        assert len(rows) == 10


def test_generate_recovery_codes_format():
    """Codes are returned in display format `ABCD-EFGH`."""
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import generate_recovery_codes
    with flask_app.app_context():
        u = _seed_user(role="superadmin")
        codes = generate_recovery_codes(db.session, u)
        db.session.commit()
        for c in codes:
            assert len(c) == 9  # 8 hex + 1 dash
            assert c[4] == "-"
            assert c.replace("-", "").isalnum()


# ── consume_recovery_code ───────────────────────────────────


def test_consume_recovery_code_marks_used_and_returns_true():
    from api.Modules.Auth.Models import RecoveryCode
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import (
        consume_recovery_code, generate_recovery_codes,
    )
    with flask_app.app_context():
        u = _seed_user(role="superadmin")
        codes = generate_recovery_codes(db.session, u)
        db.session.commit()
        code = codes[0]
        assert consume_recovery_code(db.session, u, code) is True
        db.session.commit()
        # Re-using the same code should now fail
        assert consume_recovery_code(db.session, u, code) is False


def test_consume_recovery_code_handles_hyphen_and_case():
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import (
        consume_recovery_code, generate_recovery_codes,
    )
    with flask_app.app_context():
        u = _seed_user(role="superadmin")
        codes = generate_recovery_codes(db.session, u)
        db.session.commit()
        # Lowercased + hyphenless variant should also match
        code = codes[0]
        unhyphenated_lc = code.replace("-", "").lower()
        assert consume_recovery_code(db.session, u, unhyphenated_lc) is True


def test_consume_recovery_code_rejects_unknown():
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import consume_recovery_code
    with flask_app.app_context():
        u = _seed_user(role="superadmin")
        assert consume_recovery_code(db.session, u, "AAAAAAAA") is False


def test_consume_recovery_code_handles_empty():
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import consume_recovery_code
    with flask_app.app_context():
        u = _seed_user(role="superadmin")
        assert consume_recovery_code(db.session, u, "") is False
        assert consume_recovery_code(db.session, u, None) is False


def test_consume_recovery_code_rejects_other_users_code():
    """A code minted for user A must not be consumable by user B."""
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import (
        consume_recovery_code, generate_recovery_codes,
    )
    with flask_app.app_context():
        u_a = _seed_user(role="superadmin")
        u_b = _seed_user(role="superadmin")
        codes_a = generate_recovery_codes(db.session, u_a)
        db.session.commit()
        # Try u_a's code on u_b — must fail
        assert consume_recovery_code(db.session, u_b, codes_a[0]) is False
