"""Self-service signup Service.

Owner-first signup (U-4b, owner directive): `/signup` creates a
`(Store, OWNER User)` pair — the person who signs up owns the
store, sees everything, and creates admin/employee users under
them from inside it. The owner's `store_id` is their home store
and a `StoreOwnerLink` row is written so the owner umbrella +
sibling-store logic treat the home store like any linked store.

Legacy owner signup (`/signup/owner`, no store creation) still
runs through `create_owner` for owners who only oversee existing
stores via invite codes; the SPA no longer links to it.
"""
from dataclasses import dataclass
from datetime import timedelta

from slugify import slugify
from sqlalchemy.orm import Session

from api.Modules.Auth.Models import Store, User
from api.Modules.Tenancy.Models import StoreOwnerLink
from api.Core.Clock import utc_now


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
    owner: User


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


def create_store_and_owner(
    db: Session,
    *,
    store_name: str,
    email: str,
    password: str,
    phone: str = "",
    referred_by_code_id: int | None = None,
    trial_days: int = DEFAULT_TRIAL_DAYS,
    grace_days: int = DEFAULT_GRACE_DAYS,
    business_type: str = "msb_hybrid",
) -> SignupResult:
    """Create a fresh Store + OWNER User pair (U-4b).

    The signer-up becomes a `role="owner"` user whose `store_id`
    is the new store (their home store), plus a `StoreOwnerLink`
    row so sibling-store logic (customer upsert, rollups) sees
    the home store without special-casing. They enter the store
    through `/auth/switch-store` (the SPA auto-enters after
    signup) and manage users from inside it.

    Caller is responsible for committing the surrounding
    transaction. We `flush()` so the Store gets an id before the
    User insert references it.

    `email` and `store_name` should already be normalised (stripped,
    `email.lower()`). The Service doesn't re-trim — that's a
    presentation concern the route handles before the call.

    Raises `SignupConflictError` when ANY existing user holds this
    username — per-store users AND store-less rows (legacy owners,
    superadmin). The cross-store login lookup is first-match-by-
    username, so a duplicate would shadow an account.
    """
    existing = (
        db.query(User)
          .filter(User.username == email)
          .first()
    )
    if existing is not None:
        raise SignupConflictError(
            "An account with this email already exists.",
        )

    slug = _allocate_unique_slug(db, store_name)
    now = utc_now()
    trial_end = now + timedelta(days=trial_days)
    grace_end = trial_end + timedelta(days=grace_days)
    store = Store(
        name=store_name, slug=slug, email=email,
        phone=phone, plan="trial",
        business_type=business_type,
        trial_ends_at=trial_end, grace_ends_at=grace_end,
    )
    if referred_by_code_id is not None:
        setattr(store, "referred_by_code_id", referred_by_code_id)
    db.add(store)
    db.flush()  # so store.id exists for the User FK

    owner = User(
        store_id=store.id, username=email,
        full_name=store_name, role="owner",
    )
    owner.set_password(password)
    db.add(owner)
    db.flush()
    db.add(StoreOwnerLink(owner_id=owner.id, store_id=store.id))
    db.flush()
    return SignupResult(store=store, owner=owner)


def create_store_for_owner(
    db: Session, owner: User, *,
    store_name: str,
    business_type: str = "cstore",
    phone: str = "",
    address: str = "",
    trial_days: int = DEFAULT_TRIAL_DAYS,
    grace_days: int = DEFAULT_GRACE_DAYS,
) -> Store:
    """Add another store under an EXISTING owner (U-5a).

    Same trial-window defaults as a fresh signup — subscriptions
    are per store, so the new location gets its own 7-day trial
    and subscribes on its own — plus the `StoreOwnerLink` row that
    puts it in the owner's umbrella (switcher, sibling-store
    customer upsert, rollups). No User row is created: the owner
    enters the store via /auth/switch-store and creates that
    store's team from inside it.

    Caller commits. `store_name` should be pre-stripped.
    """
    slug = _allocate_unique_slug(db, store_name)
    now = utc_now()
    trial_end = now + timedelta(days=trial_days)
    grace_end = trial_end + timedelta(days=grace_days)
    store = Store(
        name=store_name, slug=slug,
        email=owner.username or "",
        phone=phone, address=address,
        plan="trial",
        business_type=business_type,
        trial_ends_at=trial_end, grace_ends_at=grace_end,
    )
    db.add(store)
    db.flush()
    db.add(StoreOwnerLink(owner_id=owner.id, store_id=store.id))
    db.flush()
    return store
