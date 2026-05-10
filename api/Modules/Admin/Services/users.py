"""Per-store user-management Service.

Mirrors the legacy admin_new_user / admin_edit_user Flask handlers.
Caller commits — the Service flushes so generated IDs are visible
but never commits the transaction itself. That keeps audit-log
rows + user mutation in a single rolled-back-on-error txn.

Validation rules (kept in sync with the legacy form):

  - username: 1..80 chars, unique within the store. Whitespace is
    trimmed; collisions raise UsernameTakenError.
  - password (on create): required, ≥1 char. Hashed via
    `User.set_password` — never stored raw.
  - password (on update): omit / blank to keep the current hash.
  - role: must be 'admin' or 'employee'. Other values rejected.
  - full_name: optional, ≤120 chars (trimmed).
  - is_active: PATCH-only; flipping False on yourself is blocked
    by the controller (`require_not_self`) — see the self-edit
    guard there. The Service also defends so any caller
    (programmatic, future tests) gets the same protection.
"""
from typing import Optional

from sqlalchemy.orm import Session

from api.Modules.Admin.Models import User
from api.Modules.Admin.Repositories.users import (
    find_store_user_by_username,
)


VALID_ROLES = ("admin", "employee")


class UsernameTakenError(ValueError):
    """Username already exists in this store."""


class SelfDemotionError(ValueError):
    """Admin tried to demote / deactivate their own account.

    Mirrors the legacy form's intent: a single-admin store could
    lock itself out by flipping its own role to employee or
    is_active=False. The Service refuses; the controller maps
    this to a 422 with `field_errors` so the React form renders
    the inline message.
    """


def create_store_user(
    db: Session, *, store_id: int,
    username: str, password: str,
    full_name: str = "", role: str = "employee",
) -> User:
    """Insert a new active User row for the store. Caller commits.
    Raises UsernameTakenError on collision, ValueError on bad
    role / missing required fields."""
    username = (username or "").strip()
    if not username:
        raise ValueError("Username is required.")
    if len(username) > 80:
        raise ValueError("Username is too long (max 80 characters).")

    if not (password or ""):
        raise ValueError("Password is required.")

    role = (role or "employee").strip()
    if role not in VALID_ROLES:
        raise ValueError("Role must be 'admin' or 'employee'.")

    full_name = (full_name or "").strip()[:120]

    if find_store_user_by_username(db, store_id, username):
        raise UsernameTakenError("Username already exists in this store.")

    user = User(
        store_id=store_id,
        username=username,
        full_name=full_name,
        role=role,
        is_active=True,
    )
    user.set_password(password)
    db.add(user)
    db.flush()
    return user


def update_store_user(
    db: Session, user: User, *,
    full_name: Optional[str] = None,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    password: Optional[str] = None,
    actor_id: Optional[int] = None,
) -> User:
    """Update editable fields. Each field is None → leave alone.

    `password` is only applied when caller passes a non-blank
    string. Empty / missing keeps the current hash, matching the
    legacy form's "leave blank to keep current" behavior.

    `actor_id` is the principal making the request. When the
    actor is the same User as the target, demoting role or
    flipping is_active=False raises SelfDemotionError so a
    single-admin store can't lock itself out via the Edit form."""
    if full_name is not None:
        user.full_name = (full_name or "").strip()[:120]

    if role is not None:
        role_clean = (role or "").strip()
        if role_clean not in VALID_ROLES:
            raise ValueError("Role must be 'admin' or 'employee'.")
        if (
            actor_id is not None
            and user.id == actor_id
            and role_clean != (user.role or "")
        ):
            raise SelfDemotionError(
                "You cannot change your own role. "
                "Ask another admin to do it.",
            )
        user.role = role_clean

    if is_active is not None:
        new_active = bool(is_active)
        if (
            actor_id is not None
            and user.id == actor_id
            and not new_active
        ):
            raise SelfDemotionError(
                "You cannot deactivate your own account. "
                "Ask another admin to do it.",
            )
        user.is_active = new_active

    if password is not None and password != "":
        user.set_password(password)

    db.flush()
    return user
