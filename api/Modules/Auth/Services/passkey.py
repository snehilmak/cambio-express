"""WebAuthn / passkey configuration helpers.

Per CLAUDE.md invariant #13, passkeys are phishing-resistant MFA
that satisfies the same security goal as TOTP. Five small helpers
own the configuration shared between registration + sign-in:

  - rp_id(host)              — Relying Party ID, what the
                                 authenticator binds the credential
                                 to. **Changing this invalidates
                                 every existing passkey.**
  - rp_name()                — Display name shown by the OS picker.
  - origin(scheme, host)     — Expected `Origin` header for
                                 verification.
  - exclude_credentials(db, user)
                              — Existing credential IDs to feed
                                 the browser as `excludeCredentials`
                                 so the same authenticator can't
                                 enroll twice on one account.
  - is_eligible(user)        — Predicate gating who can enroll.

The HTTP-facing wrappers in app.py (which build `host` /
`scheme` from `flask.request`) keep their existing names with
leading underscores so call sites in the passkey routes don't
move during the migration window.
"""
import os
from typing import Iterable, Sequence

from sqlalchemy.orm import Session

from webauthn.helpers.structs import PublicKeyCredentialDescriptor


# Brand label shown to the user during the OS-level passkey
# picker. Centralized here so we don't drift between
# registration + authentication response shapes.
RP_NAME = "DineroBook"


def rp_id(host: str) -> str:
    """Resolve the effective Relying Party ID.

    Prefer an explicit `WEBAUTHN_RP_ID` env var (prod sets this
    to `dinerobook.com`); otherwise strip the port off `host`
    so `localhost:5000` → `localhost`.

    **Critical:** every existing passkey is bound to whatever
    rpId was active at registration time. Changing this string
    invalidates every credential — we'd be issuing fresh
    enrollment prompts to all users.
    """
    explicit = os.environ.get("WEBAUTHN_RP_ID", "").strip()
    if explicit:
        return explicit
    return host.split(":", 1)[0]


def rp_name() -> str:
    """Display name shown by the OS picker. Stable across env."""
    return RP_NAME


def origin(scheme: str, host: str) -> str:
    """Build the expected `Origin` header for WebAuthn verification.

    The browser signs this alongside the challenge; a mismatch
    means the request came from a different tab/frame and the
    assertion is rejected.
    """
    return f"{scheme}://{host}"


def exclude_credentials(
    db: Session, user,
) -> list[PublicKeyCredentialDescriptor]:
    """Existing credential descriptors for `user`, sized for the
    browser's `excludeCredentials` parameter so the same physical
    authenticator can't enroll twice on one account.
    """
    from api.Modules.Auth.Models import Passkey
    rows = (
        db.query(Passkey)
          .filter_by(user_id=user.id)
          .all()
    )
    return [
        PublicKeyCredentialDescriptor(id=p.credential_id)
        for p in rows
    ]


def is_eligible(user) -> bool:
    """Whether `user` may enroll a passkey.

    Today: any logged-in user. Kept as a single predicate so
    future tightening (e.g. "deny pending self-deletion
    accounts") has one place to land.
    """
    return bool(user)
