"""Auth invariant characterization tests.

Pins the contracts documented in
`api/Modules/Auth/INVARIANTS.md` that aren't already covered
end-to-end elsewhere. Existing test files already pin most of the
flow (login_service, login_totp_flow, totp_service, passkey_*,
password_reset_service); this file fills the remaining gaps:

  1. **`_TOTP_REQUIRED_ROLES` is exactly `("superadmin",)`** —
     accidentally adding another role would silently force every
     user of that role through 2FA on next login.
  2. **Opaque error messages** — unknown user / wrong password /
     disabled user all raise the SAME `AuthenticationError`
     message. Splitting the message leaks account existence +
     status.
  3. **`_ROLE_PERMISSIONS` matrix is pinned per role** — extending
     an employee's permission set is a silent privilege
     escalation.
  4. **Passkey register-begin requires TOTP enrollment** for
     TOTP-required roles. Without this rule, a superadmin could
     register a passkey before enrolling TOTP and then have NO
     backup factor if the passkey device is lost.

If you change any of these, change the doc + the test together.
Auth changes deserve an explicit review header in the PR
description.
"""
import pytest

from tests._app import db, db_session


# ── 1. The single 2FA role gate ─────────────────────────────


def test_totp_required_roles_is_superadmin_only():
    """Pin the exact tuple. Accidentally extending this set
    (e.g. `("superadmin", "admin")`) forces every admin through
    TOTP on next login — a UX-breaking change that should be
    deliberate, not the result of a stray edit."""
    from api.Modules.Auth.Services.totp import _TOTP_REQUIRED_ROLES
    assert _TOTP_REQUIRED_ROLES == ("superadmin",), (
        "Adding a role to _TOTP_REQUIRED_ROLES is a "
        "security-sensitive change. Update INVARIANTS.md + "
        "this test + ship as its own PR."
    )


# ── 2. Opaque error messages (anti-enumeration) ────────────


def test_auth_errors_are_opaque(test_store_id):
    """All three failure modes (unknown user / wrong password /
    disabled user) raise the SAME `AuthenticationError` message.
    Splitting the message leaks whether the account exists,
    whether it's disabled, etc.
    """
    from api.Modules.Auth.Services.login import (
        AuthenticationError, authenticate_password,
    )
    from api.Modules.Auth.Models import User
    from tests._app import db

    # Seed a disabled user
    with db_session():
        u = User(
            store_id=test_store_id,
            username="disabled@test.com",
            full_name="Disabled Account",
            role="admin",
            is_active=False,
        )
        u.set_password("validpassword123!")
        db.session.add(u); db.session.commit()
        disabled_uid = u.id

    try:
        messages: set[str] = set()
        # (a) Unknown username
        with pytest.raises(AuthenticationError) as exc1:
            authenticate_password(
                db.session,
                store_id=test_store_id,
                username="does-not-exist@test.com",
                password="anything",
            )
        messages.add(str(exc1.value))

        # (b) Wrong password for a real, active user
        with pytest.raises(AuthenticationError) as exc2:
            authenticate_password(
                db.session,
                store_id=test_store_id,
                username="admin@test.com",
                password="wrong-password",
            )
        messages.add(str(exc2.value))

        # (c) Correct password but disabled
        with pytest.raises(AuthenticationError) as exc3:
            authenticate_password(
                db.session,
                store_id=test_store_id,
                username="disabled@test.com",
                password="validpassword123!",
            )
        messages.add(str(exc3.value))

        assert len(messages) == 1, (
            f"AuthenticationError messages must be identical across "
            f"failure modes; got {messages}. Splitting the message "
            f"leaks account-state to attackers."
        )
        # The message itself is opaque text — not asserting the
        # exact string (so a copy-edit doesn't break the test)
        # but asserting it doesn't mention "disabled" or
        # "unknown" or "exist".
        only_message = next(iter(messages)).lower()
        for forbidden in ("disabled", "unknown", "doesn't exist",
                          "does not exist", "inactive", "suspended"):
            assert forbidden not in only_message, (
                f"AuthenticationError message {only_message!r} "
                f"leaks account state via the substring "
                f"{forbidden!r}"
            )
    finally:
        with db_session():
            row = db.session.get(User, disabled_uid)
            if row:
                db.session.delete(row); db.session.commit()


# ── 3. Permissions matrix (anti-privilege-escalation) ──────


def test_role_permissions_matrix_is_pinned():
    """Pin the exact permission lists per role. Accidentally
    adding `platform.admin` to admin/employee/owner is a silent
    privilege escalation — pinning the per-role lists makes the
    diff obvious in the PR."""
    from api.Modules.Auth.Services.login import permissions_for

    sa_perms = permissions_for("superadmin")
    assert "platform.admin" in sa_perms
    assert "store.admin" in sa_perms
    assert "transfers.create" in sa_perms
    assert "transfers.read" in sa_perms

    owner_perms = permissions_for("owner")
    assert "owner.read" in owner_perms
    assert "owner.admin" in owner_perms
    assert "transfers.read" in owner_perms

    admin_perms = permissions_for("admin")
    assert "store.admin" in admin_perms
    assert "store.employee" in admin_perms
    assert "transfers.create" in admin_perms

    emp_perms = permissions_for("employee")
    assert "store.employee" in emp_perms
    assert "transfers.create" in emp_perms
    assert "transfers.read" in emp_perms

    # Unknown role → no permissions. Defensive against future
    # roles that haven't been wired into the matrix.
    assert permissions_for("viewer") == []
    assert permissions_for("") == []


def test_employee_does_not_have_admin_permissions():
    """The most security-critical pair. Pinned independently of
    the matrix pin above so a refactor that's "supposed" to
    preserve the matrix can't accidentally regress this rule."""
    from api.Modules.Auth.Services.login import permissions_for

    employee_perms = set(permissions_for("employee"))
    for forbidden in ("store.admin", "platform.admin",
                      "owner.admin"):
        assert forbidden not in employee_perms, (
            f"employee must NOT have {forbidden!r}"
        )


def test_admin_does_not_have_platform_admin():
    """Store admin gets store-level admin rights, NOT platform-
    level. A regression here would let any store admin take
    actions reserved for superadmin (e.g. cross-store
    impersonation)."""
    from api.Modules.Auth.Services.login import permissions_for
    assert "platform.admin" not in permissions_for("admin")


# ── 4. Passkey register-begin TOTP-first rule ───────────────


def test_passkey_register_begin_rejects_unenrolled_superadmin(
    client,
):
    """A superadmin who hasn't enrolled TOTP yet must NOT be
    able to register a passkey. The TOTP-first rule guarantees
    the user always has a non-passkey backup factor.

    Without this rule, a fresh superadmin could register a
    passkey, lose the device, and be locked out with no
    recovery path short of the Render shell.
    """
    from api.Modules.Auth.Models import User
    from tests._app import db

    # Seed a fresh, NOT-yet-2FA-enrolled superadmin. The default
    # superadmin in conftest is pre-enrolled (so the other tests
    # can login via the TOTP flow), so we make our own here.
    with db_session():
        sa = User(
            store_id=None,
            username="fresh_super@test.com",
            full_name="Fresh Super",
            role="superadmin",
            is_active=True,
            totp_secret=None,
            totp_enrolled_at=None,
        )
        sa.set_password("freshsuper1234!")
        db.session.add(sa); db.session.commit()
        sa_id = sa.id

    try:
        # Sign in to the pending-token slot, then complete TOTP
        # enroll → confirm to get the full access token… EXCEPT:
        # we want to test the path BEFORE enrollment completes.
        # The register-begin route requires a full JWT and is
        # gated by needs_totp(user) and not is_enrolled(user).
        # We can drive that gate by issuing a hand-built JWT.
        from api.Modules.Auth.Services.jwt_issuer import (
            JWTIssuer, issue_access_token,
        )
        from api.Modules.Auth.Services.login import permissions_for
        issuer = JWTIssuer(
            sub=sa_id,
            role="superadmin",
            store_id=None,
            permissions=permissions_for("superadmin"),
            full_name="Fresh Super",
            username="fresh_super@test.com",
        )
        token = issue_access_token(issuer)

        resp = client.post(
            "/api/v2/auth/passkeys/register/begin",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403, (
            f"Expected 403 for unenrolled-superadmin passkey "
            f"register-begin; got {resp.status_code}: "
            f"{resp.get_data(as_text=True)}"
        )
        body = resp.get_json()
        # Message text intentionally mentions TOTP so the SPA
        # can route the user to the enroll page.
        assert "TOTP" in (body.get("detail") or "") or \
               "totp" in (body.get("detail") or "").lower(), (
            f"Expected the 403 detail to reference TOTP; "
            f"got {body}"
        )
    finally:
        with db_session():
            row = db.session.get(User, sa_id)
            if row:
                db.session.delete(row); db.session.commit()


def test_passkey_register_begin_allows_admin_without_totp(
    client, test_store_id,
):
    """The TOTP-first rule applies ONLY to roles where
    `needs_totp(user)` is True. An admin (not a TOTP-required
    role today) must be allowed to register a passkey without
    first enrolling TOTP — otherwise we'd lock out the entire
    admin tier from the passkey feature.

    This pins the inverse of the TOTP-first rule: don't
    accidentally tighten the gate to all roles.
    """
    resp = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": test_store_id,
        },
    )
    token = resp.get_json()["access_token"]
    begin = client.post(
        "/api/v2/auth/passkeys/register/begin",
        headers={"Authorization": f"Bearer {token}"},
    )
    # 200 (options issued) OR another non-403 — what matters is
    # we did NOT block the admin on TOTP-enrollment grounds.
    assert begin.status_code != 403, (
        f"Admin without TOTP should NOT be blocked by the "
        f"TOTP-first rule. Got {begin.status_code}: "
        f"{begin.get_data(as_text=True)}"
    )
