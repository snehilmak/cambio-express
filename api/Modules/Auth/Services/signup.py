"""Self-service signup Service.

Creates a `(Store, admin User)` pair from a signup form submission.
The Flask `/signup` route handles the form-level validation +
ref-code resolution + flash messages; this Service does the
unique-slug allocation, the row inserts, and the trial-window
defaults.

Owner signup (`/signup/owner`) doesn't run through here — it has
its own flow (no store creation; just an Owner User).
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from slugify import slugify
from sqlalchemy.orm import Session

from api.Modules.Auth.Models import Store, User


# Trial window. Fresh signups get 7 days of free trial + 4 grace
# days where the store remains accessible but with reduced features.
DEFAULT_TRIAL_DAYS = 7
DEFAULT_GRACE_DAYS = 4


class SignupConflictError(ValueError):
    """An admin User with this email already exists. The Flask route
    surfaces this as the inline `errors["email"]` field; the Service
    raises so the caller can choose its UI."""


@dataclass
class SignupResult:
    store: Store
    admin: User


def _allocate_unique_slug(db: Session, store_name: str) -> str:
    """Pick a slug derived from `store_name` that no existing Store
    owns. If the base slug collides, append `-1`, `-2`, ... until
    unique."""
    base = slugify(store_name)
    slug = base
    counter = 1
    while db.query(Store).filter_by(slug=slug).first():
        slug = f"{base}-{counter}"
        counter += 1
    return slug


@dataclass
class OwnerSignupResult:
    owner: User


def create_owner(
    db: Session, *, full_name: str, email: str, password: str,
) -> OwnerSignupResult:
    """Create a multi-store owner user. Mirrors the legacy
    /signup/owner Flask route — no Store row, just a User with
    `role="owner"` and `store_id=None`. Owners then connect to
    individual stores via invite codes from /owner/locations.

    `email` and `full_name` should already be stripped + email
    lowered before calling. Raises `SignupConflictError` when a
    pre-existing User would clash:
      - any User with `store_id IS NULL` (other owners + superadmin)
      - any per-store admin with the same email (they'd be confused
        about which login goes where).
    """
    taken_null = (
        db.query(User)
          .filter(User.username == email)
          .filter(User.store_id.is_(None))
          .first()
    )
    taken_admin = (
        db.query(User)
          .filter(User.username == email)
          .filter(User.role == "admin")
          .first()
    )
    if taken_null is not None or taken_admin is not None:
        raise SignupConflictError(
            "An account with this email already exists.",
        )
    owner = User(
        store_id=None, username=email,
        full_name=full_name, role="owner",
    )
    owner.set_password(password)
    db.add(owner)
    db.flush()
    return OwnerSignupResult(owner=owner)


def create_store_and_admin(
    db: Session,
    *,
    store_name: str,
    email: str,
    password: str,
    phone: str = "",
    referred_by_code_id: int | None = None,
    trial_days: int = DEFAULT_TRIAL_DAYS,
    grace_days: int = DEFAULT_GRACE_DAYS,
) -> SignupResult:
    """Create a fresh Store + admin User pair.

    Caller is responsible for committing the surrounding
    transaction. We `flush()` so the Store gets an id before the
    User insert references it.

    `email` and `store_name` should already be normalised (stripped,
    `email.lower()`). The Service doesn't re-trim — that's a Flask
    presentation concern that the route handles before the call.

    Raises `SignupConflictError` if a per-store admin with the same
    email already exists. The legacy route's existence check used
    `User.store_id.isnot(None)` so we mirror that here (the
    `superadmin` user has `store_id IS NULL` and isn't considered a
    collision).
    """
    existing = (
        db.query(User)
          .filter(User.username == email)
          .filter(User.store_id.isnot(None))
          .first()
    )
    if existing is not None:
        raise SignupConflictError(
            "An account with this email already exists.",
        )

    slug = _allocate_unique_slug(db, store_name)
    now = datetime.utcnow()
    trial_end = now + timedelta(days=trial_days)
    grace_end = trial_end + timedelta(days=grace_days)
    store = Store(
        name=store_name, slug=slug, email=email,
        phone=phone, plan="trial",
        trial_ends_at=trial_end, grace_ends_at=grace_end,
    )
    if referred_by_code_id is not None:
        setattr(store, "referred_by_code_id", referred_by_code_id)
    db.add(store)
    db.flush()  # so store.id exists for the User FK

    admin = User(
        store_id=store.id, username=email,
        full_name=store_name, role="admin",
    )
    admin.set_password(password)
    db.add(admin)
    db.flush()
    return SignupResult(store=store, admin=admin)
