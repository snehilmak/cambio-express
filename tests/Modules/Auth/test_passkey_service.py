"""Unit tests for Auth.Services.passkey (PR 63)."""
from unittest.mock import MagicMock


# ── rp_id ──────────────────────────────────────────────────


def test_rp_id_uses_explicit_env_var(monkeypatch):
    """Prod-style: WEBAUTHN_RP_ID env var wins over the request host."""
    from api.Modules.Auth.Services import passkey_rp_id
    monkeypatch.setenv("WEBAUTHN_RP_ID", "dinerobook.com")
    assert passkey_rp_id("staging.example.com") == "dinerobook.com"


def test_rp_id_strips_whitespace_from_env_var(monkeypatch):
    from api.Modules.Auth.Services import passkey_rp_id
    monkeypatch.setenv("WEBAUTHN_RP_ID", "  dinerobook.com  ")
    assert passkey_rp_id("ignored") == "dinerobook.com"


def test_rp_id_falls_back_to_host_without_port(monkeypatch):
    """Dev-style: localhost:5000 → localhost."""
    from api.Modules.Auth.Services import passkey_rp_id
    monkeypatch.delenv("WEBAUTHN_RP_ID", raising=False)
    assert passkey_rp_id("localhost:5000") == "localhost"


def test_rp_id_passthrough_when_no_port(monkeypatch):
    from api.Modules.Auth.Services import passkey_rp_id
    monkeypatch.delenv("WEBAUTHN_RP_ID", raising=False)
    assert passkey_rp_id("dinerobook.com") == "dinerobook.com"


def test_rp_id_empty_env_var_falls_through(monkeypatch):
    """Empty string → fall back to host."""
    from api.Modules.Auth.Services import passkey_rp_id
    monkeypatch.setenv("WEBAUTHN_RP_ID", "")
    assert passkey_rp_id("localhost:5000") == "localhost"


# ── rp_name ────────────────────────────────────────────────


def test_rp_name_is_dinerobook():
    from api.Modules.Auth.Services import passkey_rp_name, PASSKEY_RP_NAME
    assert passkey_rp_name() == "DineroBook"
    assert PASSKEY_RP_NAME == "DineroBook"


# ── origin ─────────────────────────────────────────────────


def test_origin_concatenates_scheme_and_host():
    from api.Modules.Auth.Services import passkey_origin
    assert passkey_origin("https", "dinerobook.com") == \
        "https://dinerobook.com"


def test_origin_preserves_port():
    """Dev environment: localhost:5000 keeps its port."""
    from api.Modules.Auth.Services import passkey_origin
    assert passkey_origin("http", "localhost:5000") == \
        "http://localhost:5000"


# ── exclude_credentials ────────────────────────────────────


def test_exclude_credentials_returns_descriptors_for_user():
    from api.Modules.Auth.Models import Passkey
    from api.Modules.Tenancy.Models import User
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import passkey_exclude_credentials
    with flask_app.app_context():
        # Create a user + 2 passkeys
        u = User(
            username="passkey-user@test.com",
            password_hash="x", role="admin",
            full_name="Passkey User",
            email="passkey-user@test.com",
            store_id=1,
        )
        db.session.add(u); db.session.flush()
        for i in (1, 2):
            db.session.add(Passkey(
                user_id=u.id,
                credential_id=f"cred-{u.id}-{i}".encode(),
                public_key=b"pub",
                sign_count=0,
                aaguid="",
                name=f"Key {i}",
            ))
        db.session.flush()
        result = passkey_exclude_credentials(db.session, u)
        assert len(result) == 2
        # Each has an `id` attribute (PublicKeyCredentialDescriptor)
        ids = {bytes(d.id) for d in result}
        assert ids == {b"cred-%d-1" % u.id, b"cred-%d-2" % u.id}


def test_exclude_credentials_empty_for_user_without_passkeys():
    from api.Modules.Tenancy.Models import User
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import passkey_exclude_credentials
    with flask_app.app_context():
        u = User(
            username="no-passkey@test.com",
            password_hash="x", role="admin",
            full_name="No Passkey", email="no-passkey@test.com",
            store_id=1,
        )
        db.session.add(u); db.session.flush()
        assert passkey_exclude_credentials(db.session, u) == []


# ── is_eligible ────────────────────────────────────────────


def test_is_eligible_true_for_logged_in_user():
    from api.Modules.Auth.Services import passkey_is_eligible
    user = MagicMock()
    assert passkey_is_eligible(user) is True


def test_is_eligible_false_for_none():
    from api.Modules.Auth.Services import passkey_is_eligible
    assert passkey_is_eligible(None) is False


# ── legacy Flask wrappers ──────────────────────────────────












