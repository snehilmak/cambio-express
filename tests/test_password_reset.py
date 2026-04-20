"""Tests for the self-service password-reset flow.

Invariant (CLAUDE.md #10): tokens are stored as sha256(raw) in
PasswordResetToken.token_hash, single-use, 1-hour expiry. /forgot-password
always responds with "Check your email" regardless of whether the account
exists. The raw token must never hit the DB.
"""
from datetime import datetime, timedelta
from unittest.mock import patch


def _seed_user(username="owner@example.com", password="oldpass123!", role="admin"):
    from app import db, User, Store
    store = Store.query.filter_by(slug="test-store").first()
    u = User(store_id=store.id, username=username, full_name="Owner", role=role)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    return u.id


# ── /forgot-password ────────────────────────────────────────────────────────

def test_forgot_password_get_renders_form(client):
    resp = client.get("/forgot-password")
    assert resp.status_code == 200
    # Form should have an input for the email/username.
    assert b"username" in resp.data.lower() or b"email" in resp.data.lower()


def test_forgot_password_same_response_for_unknown_email(client):
    """Must not leak whether an account exists — attackers could enumerate."""
    resp = client.post("/forgot-password",
                       data={"username": "nobody@nowhere.example"})
    assert resp.status_code == 200
    # Page signals "sent" without revealing anything.
    assert b"check your email" in resp.data.lower() or b"sent" in resp.data.lower()
    # And no token got minted for a non-existent user.
    from app import PasswordResetToken
    assert PasswordResetToken.query.count() == 0


def test_forgot_password_mints_token_for_known_user(client):
    from app import db, PasswordResetToken
    with client.application.app_context():
        uid = _seed_user()
    client.post("/forgot-password", data={"username": "owner@example.com"})
    with client.application.app_context():
        tokens = PasswordResetToken.query.filter_by(user_id=uid).all()
        assert len(tokens) == 1
        t = tokens[0]
        assert t.used_at is None
        # 1-hour TTL (allow a few seconds of slack for test runtime).
        delta = t.expires_at - datetime.utcnow()
        assert timedelta(minutes=55) < delta <= timedelta(hours=1, seconds=5)


def test_forgot_password_stores_only_sha256_hash(client):
    """Raw token must never reach the DB — only the sha256 hex."""
    import hashlib
    from app import db, PasswordResetToken
    with client.application.app_context():
        _seed_user()
    # Generate a deterministic raw token by patching secrets.token_urlsafe.
    raw = "fixed-raw-token-for-hash-check"
    with patch("app.secrets.token_urlsafe", return_value=raw):
        client.post("/forgot-password", data={"username": "owner@example.com"})
    expected_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    with client.application.app_context():
        t = PasswordResetToken.query.one()
        assert t.token_hash == expected_hash
        # And critically: the raw token never appears in the hash column.
        assert raw not in t.token_hash


def test_forgot_password_invalidates_old_tokens(client):
    """Minting a fresh token marks any live ones for the same user as used."""
    from app import db, PasswordResetToken
    with client.application.app_context():
        _seed_user()
    client.post("/forgot-password", data={"username": "owner@example.com"})
    client.post("/forgot-password", data={"username": "owner@example.com"})
    with client.application.app_context():
        tokens = PasswordResetToken.query.order_by(PasswordResetToken.id).all()
        assert len(tokens) == 2
        # First one got invalidated; second is still usable.
        assert tokens[0].used_at is not None
        assert tokens[1].used_at is None


def test_forgot_password_ignores_employee_accounts(client):
    """Only admins/owners/superadmins can reset via this flow."""
    from app import db, PasswordResetToken
    with client.application.app_context():
        _seed_user(username="cashier@example.com", role="employee")
    resp = client.post("/forgot-password",
                       data={"username": "cashier@example.com"})
    assert resp.status_code == 200  # Still same friendly response.
    with client.application.app_context():
        assert PasswordResetToken.query.count() == 0


def test_forgot_password_ignores_inactive_accounts(client):
    """Deactivated admins can't trigger resets."""
    from app import db, User, PasswordResetToken
    with client.application.app_context():
        uid = _seed_user()
        u = db.session.get(User, uid)
        u.is_active = False
        db.session.commit()
    client.post("/forgot-password", data={"username": "owner@example.com"})
    with client.application.app_context():
        assert PasswordResetToken.query.count() == 0


# ── /reset-password/<token> ─────────────────────────────────────────────────

def _mint_token(client, username="owner@example.com"):
    """Helper: trigger the mint flow with a known raw token and return it."""
    raw = "known-raw-token-for-test-reset"
    with patch("app.secrets.token_urlsafe", return_value=raw):
        client.post("/forgot-password", data={"username": username})
    return raw


def test_reset_password_get_valid_token_shows_form(client):
    with client.application.app_context():
        _seed_user()
    raw = _mint_token(client)
    resp = client.get(f"/reset-password/{raw}")
    assert resp.status_code == 200
    # Form present — "invalid" branch should NOT be rendered.
    assert b"password" in resp.data.lower()


def test_reset_password_get_unknown_token_renders_invalid(client):
    resp = client.get("/reset-password/this-token-was-never-minted")
    assert resp.status_code == 200
    assert b"invalid" in resp.data.lower() or b"expired" in resp.data.lower()


def test_reset_password_rejects_short_password(client):
    with client.application.app_context():
        _seed_user()
    raw = _mint_token(client)
    resp = client.post(f"/reset-password/{raw}",
                       data={"password": "short", "confirm_password": "short"})
    assert resp.status_code == 200
    assert b"8 characters" in resp.data or b"at least" in resp.data.lower()


def test_reset_password_rejects_mismatched_confirmation(client):
    with client.application.app_context():
        _seed_user()
    raw = _mint_token(client)
    resp = client.post(f"/reset-password/{raw}",
                       data={"password": "newpass123!",
                             "confirm_password": "different123!"})
    assert resp.status_code == 200
    assert b"do not match" in resp.data.lower() or b"match" in resp.data.lower()


def test_reset_password_success_sets_new_password(client):
    from app import db, User, PasswordResetToken
    with client.application.app_context():
        uid = _seed_user()
    raw = _mint_token(client)
    resp = client.post(f"/reset-password/{raw}",
                       data={"password": "brandnew123!",
                             "confirm_password": "brandnew123!"},
                       follow_redirects=False)
    # Redirect to login on success.
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
    with client.application.app_context():
        u = db.session.get(User, uid)
        assert u.check_password("brandnew123!")
        assert not u.check_password("oldpass123!")
        # Token was consumed.
        t = PasswordResetToken.query.filter_by(user_id=uid).one()
        assert t.used_at is not None


def test_reset_password_token_is_single_use(client):
    """Using a token once burns it — second POST must fail."""
    with client.application.app_context():
        _seed_user()
    raw = _mint_token(client)
    # First use: succeeds.
    client.post(f"/reset-password/{raw}",
                data={"password": "firstpass123!", "confirm_password": "firstpass123!"})
    # Second use: must be rejected as invalid.
    resp = client.post(f"/reset-password/{raw}",
                       data={"password": "secondpass123!",
                             "confirm_password": "secondpass123!"})
    assert resp.status_code == 200
    assert b"invalid" in resp.data.lower() or b"expired" in resp.data.lower()
    # Password should still be the one set on first use.
    from app import db, User
    with client.application.app_context():
        u = User.query.filter_by(username="owner@example.com").first()
        assert u.check_password("firstpass123!")
        assert not u.check_password("secondpass123!")


def test_reset_password_expired_token_rejected(client):
    """Tokens past expires_at are rejected, even before used_at is set."""
    from app import db, PasswordResetToken
    with client.application.app_context():
        _seed_user()
    raw = _mint_token(client)
    # Age the token by an hour + a minute.
    with client.application.app_context():
        t = PasswordResetToken.query.one()
        t.expires_at = datetime.utcnow() - timedelta(minutes=1)
        db.session.commit()
    resp = client.post(f"/reset-password/{raw}",
                       data={"password": "newpass123!",
                             "confirm_password": "newpass123!"})
    assert resp.status_code == 200
    assert b"invalid" in resp.data.lower() or b"expired" in resp.data.lower()


def test_reset_password_unknown_token_post_is_rejected(client):
    """POSTing to an unknown token must not reset anyone's password."""
    from app import db, User
    with client.application.app_context():
        uid = _seed_user()
    resp = client.post("/reset-password/bogus-token",
                       data={"password": "hacker123!",
                             "confirm_password": "hacker123!"})
    assert resp.status_code == 200  # renders invalid page, not 5xx
    with client.application.app_context():
        u = db.session.get(User, uid)
        assert u.check_password("oldpass123!")
