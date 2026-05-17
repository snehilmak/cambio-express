"""Account notifications Service.

Per-user boolean toggles plus ``*_applies`` predicates that gate
which toggles render as interactive vs. greyed-out informational
on the SPA — keeps the UI honest about which channels actually
apply to the current role + store state.
"""
from typing import Optional

from sqlalchemy.orm import Session

from api.Modules.Auth.Models import User


def trial_toggle_applies(db: Session, user: User) -> bool:
    """True when this user's role + store make the Trial-ending
    reminder relevant — admin / owner role on a store currently
    in trial (``active`` / ``expiring_soon`` / ``grace``)."""
    if user.role not in ("admin", "owner"):
        return False
    if user.store_id is None:
        return False
    from api.Modules.Billing.Services import get_trial_status
    from api.Modules.Tenancy.Models import Store
    store = db.get(Store, user.store_id)
    if store is None:
        return False
    return get_trial_status(store) in ("active", "expiring_soon", "grace")


def locked_day_digest_applies(user: User) -> bool:
    """True for admins / owners — employees never receive the
    digest so showing them an interactive toggle would be
    misleading. Cross-checked against the eligibility filter in
    ``Notifications.Services.locked_day_digest.eligible_recipients``."""
    return user.role in ("admin", "owner")


def daily_summary_applies(user: User) -> bool:
    """Same gating as the locked-day digest — admins / owners only.
    Cross-checked against
    ``Notifications.Services.daily_summary.eligible_recipients``."""
    return user.role in ("admin", "owner")


def get_notifications_payload(db: Session, user: User) -> dict:
    """Return the GET payload for the notifications page."""
    return {
        "notify_trial_reminders":    bool(user.notify_trial_reminders),
        "notify_announcement_email": bool(user.notify_announcement_email),
        "notify_locked_day_digest":  bool(user.notify_locked_day_digest),
        "notify_daily_summary":      bool(user.notify_daily_summary),
        "trial_toggle_applies":      trial_toggle_applies(db, user),
        "locked_day_digest_applies": locked_day_digest_applies(user),
        "daily_summary_applies":     daily_summary_applies(user),
        "role":                      user.role or "",
    }


def update_notifications(
    db: Session, user: User, *,
    notify_trial_reminders:    Optional[bool] = None,
    notify_announcement_email: Optional[bool] = None,
    notify_locked_day_digest:  Optional[bool] = None,
    notify_daily_summary:      Optional[bool] = None,
) -> None:
    """Apply changes. None = don't touch. Caller commits.

    No validation — booleans only. Pydantic enforces type at the
    boundary; a non-bool gets rejected with 422 before reaching
    this layer."""
    if notify_trial_reminders is not None:
        user.notify_trial_reminders = bool(notify_trial_reminders)
    if notify_announcement_email is not None:
        user.notify_announcement_email = bool(notify_announcement_email)
    if notify_locked_day_digest is not None:
        user.notify_locked_day_digest = bool(notify_locked_day_digest)
    if notify_daily_summary is not None:
        user.notify_daily_summary = bool(notify_daily_summary)
    db.flush()
