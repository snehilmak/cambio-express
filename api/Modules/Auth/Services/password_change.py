"""Password-change Service.

Two related flows: a self-service `/account/security` change (where
the user must prove the current password) and an admin-side reset
on the team page (`/admin/settings/team/<uid>`, no current password
required).

Both share the same new+confirm validation rules (length 8 +
matching). The `_update_user_password` legacy helper in app.py
becomes a thin wrapper over `change_password` here, and the
admin-side route grows the same kind of wrapper.
"""
from sqlalchemy.orm import Session

from api.Modules.Auth.Models import User


MIN_PASSWORD_LENGTH = 8


def _validate_new_password(
    new_pw: str, confirm_pw: str,
) -> dict[str, str]:
    """Shared validation for any password-set flow. Returns an
    `{field: message}` dict (empty on success) so callers can
    surface inline form errors without translating exceptions."""
    if len(new_pw or "") < MIN_PASSWORD_LENGTH:
        return {
            "new_password": f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
        }
    if new_pw != confirm_pw:
        return {"confirm_password": "Passwords do not match."}
    return {}


def change_password(
    db: Session, user: User,
    current_pw: str, new_pw: str, confirm_pw: str,
) -> dict[str, str]:
    """Self-service password change. Validates the current password,
    then applies the new one. Returns `{}` on success or
    `{field: message}` on failure.

    Caller commits — we just mutate the User row.
    """
    if not user.check_password(current_pw or ""):
        return {"current_password": "Current password is incorrect."}
    errors = _validate_new_password(new_pw, confirm_pw)
    if errors:
        return errors
    user.set_password(new_pw)
    db.flush()
    return {}


def admin_set_password(
    db: Session, target: User,
    new_pw: str, confirm_pw: str,
) -> dict[str, str]:
    """Admin-side password reset for an employee. No current-password
    check (the admin is the authority). Same validation rules as
    `change_password`. Returns `{}` on success or `{field: message}`.

    Caller is responsible for scoping the `target` user to their
    store before calling — the Service trusts the caller on tenancy.
    """
    errors = _validate_new_password(new_pw, confirm_pw)
    if errors:
        return errors
    target.set_password(new_pw)
    db.flush()
    return {}
