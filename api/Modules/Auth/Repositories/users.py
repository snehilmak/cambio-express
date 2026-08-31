"""User lookup helpers.

The User table mixes per-store users (admin / employee / owner) with
the platform-wide superadmin (`store_id IS NULL`). The unique
constraint is `(store_id, username)` — the same email can be a
user at multiple stores. Login flows must always know which store
the request is for; we never search "username across all stores".
"""
from typing import Iterable

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from api.Modules.Auth.Models import User


def find_user_by_id(db: Session, user_id: int) -> User | None:
    """Lookup by primary key. Used for session restoration and the
    JWT subject resolution path."""
    return db.get(User, user_id)


def find_user_by_username_in_store(
    db: Session, store_id: int | None, username: str,
) -> User | None:
    """Find a user by `(store_id, username)`. Pass `store_id=None`
    to look up the superadmin (which lives at `store_id IS NULL`).

    `username` is matched case-sensitively, mirroring the legacy
    behavior — clients normalize to lowercase before submitting.
    """
    if not username:
        return None
    return (
        db.query(User)
          .filter(User.store_id.is_(store_id) if store_id is None
                   else User.store_id == store_id)
          .filter(User.username == username)
          .first()
    )


def find_user_by_username(
    db: Session, username: str, *, role: str | None = None,
) -> User | None:
    """Find a user by username across stores — first match wins.
    Only safe for use in superadmin-style flows (e.g. password reset
    by username) where the caller has already established intent.
    Optional `role` filter scopes to a single role (e.g. "superadmin")
    so a normal user can't be promoted by accident."""
    if not username:
        return None
    q = db.query(User).filter(User.username == username)
    if role:
        q = q.filter(User.role == role)
    return q.first()


def find_active_users_by_identifier(
    db: Session, identifier: str, *, limit: int = 25,
) -> list[User]:
    """Every ACTIVE user a sign-in `identifier` could refer to,
    across all stores, ordered by id asc.

    An identifier is an email address, a phone number, or — for
    accounts that predate L-2 — a username. All three are matched in
    one query rather than branching on what the input "looks like",
    because the guess can be wrong: a legacy username can be an email
    address, and a numeric username can look like a phone number.
    Matching all three and letting the password decide has no such
    failure mode.

    Identifiers are unique per store, not globally
    (`UniqueConstraint("store_id", "username")`), so "amber" — or one
    shared family email — can legitimately exist at several stores.
    The sign-in page has no store context, so it has to consider all
    of them; a first-match-wins lookup would lock out everyone but
    the oldest row.

    `limit` bounds the scan: each candidate costs a bcrypt verify at
    the call site, so an unbounded result would let a common
    identifier turn one login attempt into hundreds of hashes. 25 is
    far above any realistic collision count and far below a useful
    amplification factor.
    """
    from api.Modules.Auth.Services.identity import (
        normalize_email, normalize_phone,
    )
    raw = (identifier or "").strip()
    if not raw:
        return []

    # Username stays case-sensitive (legacy behaviour); email is
    # matched case-insensitively, which is what people expect of an
    # address they typed with a capital letter.
    matches = [User.username == raw]
    email = normalize_email(raw)
    if email:
        matches.append(func.lower(User.email) == email)
    phone = normalize_phone(raw)
    if phone:
        matches.append(User.login_phone == phone)

    return (
        db.query(User)
          .filter(or_(*matches))
          .filter(User.is_active.is_(True))
          .order_by(User.id.asc())
          .limit(limit)
          .all()
    )


def list_users_in_store(
    db: Session, store_id: int, *,
    roles: Iterable[str] | None = None,
    active_only: bool = False,
) -> list[User]:
    """All users in a store, ordered by id asc (insertion order =
    historical seniority). Filter by role(s) and `active_only=True`
    to restrict the set."""
    q = db.query(User).filter(User.store_id == store_id)
    if roles is not None:
        q = q.filter(User.role.in_(list(roles)))
    if active_only:
        q = q.filter(User.is_active.is_(True))
    return q.order_by(User.id.asc()).all()
