"""Unit tests for `Auth.Services.login.authenticate_password`."""
import pytest
from tests._app import db


def _seed_user(store_id, *, username, password, role="employee",
                full_name="", is_active=True):
    from api.Modules.Tenancy.Models import User
    from tests._app import db
    u = User(
        store_id=store_id, username=username, role=role,
        full_name=full_name, is_active=is_active,
    )
    u.set_password(password)
    db.session.add(u); db.session.commit()
    return u.id


# ── permissions_for ─────────────────────────────────────────


def test_permissions_for_admin_includes_employee():
    """Admin role inherits employee permissions for the JWT claim."""
    from api.Modules.Auth.Services import permissions_for
    assert "store.admin" in permissions_for("admin")
    assert "store.employee" in permissions_for("admin")


def test_permissions_for_superadmin_includes_everything_except_owner_admin():
    from api.Modules.Auth.Services import permissions_for
    perms = permissions_for("superadmin")
    assert "platform.admin" in perms
    assert "store.admin" in perms
    assert "store.employee" in perms
    # superadmin doesn't manage owner umbrella mutations directly
    assert "owner.admin" not in perms


def test_permissions_for_unknown_role_is_empty():
    """A role not in the matrix gets no permissions — fail closed."""
    from api.Modules.Auth.Services import permissions_for
    assert permissions_for("garbage") == []


# ── authenticate_password ───────────────────────────────────


def test_authenticate_password_returns_login_result(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import authenticate_password
    with flask_app.app_context():
        result = authenticate_password(
            db.session, store_id=test_store_id,
            username="admin@test.com", password="testpass123!",
        )
    assert result.user_id is not None
    assert result.role == "admin"
    assert result.store_id == test_store_id
    assert result.username == "admin@test.com"
    assert result.access_token  # non-empty
    assert "store.admin" in result.permissions


def test_authenticate_password_rejects_bad_password(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import authenticate_password
    from api.Modules.Auth.Services.login import AuthenticationError
    with flask_app.app_context():
        with pytest.raises(AuthenticationError):
            authenticate_password(
                db.session, store_id=test_store_id,
                username="admin@test.com", password="wrong",
            )


def test_authenticate_password_rejects_unknown_user(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import authenticate_password
    from api.Modules.Auth.Services.login import AuthenticationError
    with flask_app.app_context():
        with pytest.raises(AuthenticationError):
            authenticate_password(
                db.session, store_id=test_store_id,
                username="nobody@x.com", password="x",
            )


def test_authenticate_password_rejects_disabled_user(test_store_id):
    """Disabled accounts must fail with the same exception as an
    unknown user — never leak "account exists but is disabled" via
    the response shape."""
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import authenticate_password
    from api.Modules.Auth.Services.login import AuthenticationError
    with flask_app.app_context():
        _seed_user(
            test_store_id, username="quit@x.com", password="p",
            is_active=False,
        )
        with pytest.raises(AuthenticationError):
            authenticate_password(
                db.session, store_id=test_store_id,
                username="quit@x.com", password="p",
            )


def test_authenticate_password_finds_superadmin_with_none_store_id():
    """`store_id=None` is the superadmin scope. The seeded fixture
    creates `superadmin / super2025!` at store_id=None and pre-
    enrols TOTP so SPA logins can exchange the pending token for a
    real access token without a manual enrolment hop. The
    authenticate_password call therefore returns a pending result
    with `enroll_required=False`."""
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import (
        LoginPendingResult, authenticate_password,
    )
    from api.Modules.Auth.Services.jwt_issuer import (
        decode_pending_2fa_token,
    )
    with flask_app.app_context():
        result = authenticate_password(
            db.session, store_id=None,
            username="superadmin", password="super2025!",
        )
    assert isinstance(result, LoginPendingResult)
    assert result.enroll_required is False
    claims = decode_pending_2fa_token(result.pending_token)
    assert int(claims["sub"]) == result.user_id


def test_authenticate_password_token_carries_role_and_perms_claims(test_store_id):
    """End-to-end: the JWT we mint round-trips with the same role +
    permissions claims that the LoginResult carries."""
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import (
        authenticate_password, decode_access_token,
    )
    with flask_app.app_context():
        result = authenticate_password(
            db.session, store_id=test_store_id,
            username="admin@test.com", password="testpass123!",
        )
    payload = decode_access_token(result.access_token)
    assert payload["role"] == "admin"
    assert set(payload["perms"]) == set(result.permissions)
    assert payload["store_id"] == test_store_id


# ── Pydantic schemas ────────────────────────────────────────


def test_login_response_schema_validates(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import authenticate_password
    from api.Modules.Auth.Requests import LoginResponse
    with flask_app.app_context():
        result = authenticate_password(
            db.session, store_id=test_store_id,
            username="admin@test.com", password="testpass123!",
        )
        resp = LoginResponse(
            access_token=result.access_token,
            user_id=result.user_id,
            username=result.username,
            full_name=result.full_name,
            role=result.role,
            store_id=result.store_id,
            permissions=result.permissions,
        )
    assert resp.token_type == "Bearer"
    assert resp.expires_in == 30 * 60


def test_login_request_schema_rejects_extra_fields():
    from api.Modules.Auth.Requests import LoginRequest
    import pydantic
    with pytest.raises(pydantic.ValidationError):
        LoginRequest(
            username="alice", password="x", store_id=1,
            backdoor=True,
        )


def test_login_request_schema_rejects_empty_username():
    from api.Modules.Auth.Requests import LoginRequest
    import pydantic
    with pytest.raises(pydantic.ValidationError):
        LoginRequest(username="", password="x")


# ── verify_password_cross_store ─────────────────────────────


def test_verify_password_cross_store_returns_user_on_success(test_store_id):
    """Used by the legacy Flask /login page (which doesn't know which
    store the user belongs to before the password check)."""
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import verify_password_cross_store
    with flask_app.app_context():
        u = verify_password_cross_store(
            db.session, "admin@test.com", "testpass123!",
        )
    assert u is not None
    assert u.username == "admin@test.com"
    assert u.role == "admin"


def test_verify_password_cross_store_returns_none_on_bad_password(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import verify_password_cross_store
    with flask_app.app_context():
        u = verify_password_cross_store(
            db.session, "admin@test.com", "wrong",
        )
    assert u is None


def test_verify_password_cross_store_returns_none_for_unknown_user():
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import verify_password_cross_store
    with flask_app.app_context():
        u = verify_password_cross_store(
            db.session, "ghost@x.com", "anything",
        )
    assert u is None


def test_verify_password_cross_store_rejects_disabled_user(test_store_id):
    """Disabled accounts must fail the same way as wrong password —
    no enumeration of "exists but disabled" via the response."""
    from api.Modules.Tenancy.Models import User
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import verify_password_cross_store
    with flask_app.app_context():
        u_obj = User(
            store_id=test_store_id, username="quit-vp@x.com",
            role="employee", is_active=False,
        )
        u_obj.set_password("p")
        db.session.add(u_obj); db.session.commit()
        u = verify_password_cross_store(
            db.session, "quit-vp@x.com", "p",
        )
    assert u is None


def test_verify_password_cross_store_finds_superadmin():
    """Cross-store lookup must include the superadmin (which has
    store_id=None)."""
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import verify_password_cross_store
    with flask_app.app_context():
        u = verify_password_cross_store(
            db.session, "superadmin", "super2025!",
        )
    assert u is not None
    assert u.role == "superadmin"


def test_verify_password_cross_store_handles_empty_inputs():
    """Defensive: empty username or password short-circuits to None
    instead of fishing the DB."""
    from tests._app import app as flask_app, db
    from api.Modules.Auth.Services import verify_password_cross_store
    with flask_app.app_context():
        assert verify_password_cross_store(db.session, "", "x") is None
        assert verify_password_cross_store(db.session, "x", "") is None
        assert verify_password_cross_store(db.session, "", "") is None


# ── Flask /login route end-to-end ───────────────────────────


# The legacy Flask `/login` form + cookie-session POST handler was
# retired in chunk 3. The SPA owns login entirely via POST
# `/api/v2/auth/login` (JSON in / JWT out). UI tests for the JWT
# path live in tests/Modules/Auth/ alongside this module; the
# Jinja form-rendering tests were deleted with the Jinja UI.
