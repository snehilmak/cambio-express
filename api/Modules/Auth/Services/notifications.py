"""Account notifications Service.

Per-user boolean toggles. The legacy Jinja form gated the
Trial-ending toggle as `trial_toggle_applies` — only admins/owners
of a trialing store could actually receive the email. Mirror that
gating here so the SPA renders the same disabled-when-N/A state.
"""
from typing import Optional

from sqlalchemy.orm import Session

from api.Modules.Auth.Models import User


def trial_toggle_applies(db: Session, user: User) -> bool:
    """True when this user's role + store make the Trial-ending
    reminder relevant. Mirrors the legacy logic in
    app.account_notifications: admin/owner role + active store +
    trial status in (active, expiring_soon, grace)."""
    if user.role not in ("admin", "owner"):
        return False
    if user.store_id is None:
        return False
    from api.Modules.Tenancy.Models import Store
    from app import get_trial_status
    store = db.get(Store, user.store_id)
    if store is None:
        return False
    return get_trial_status(store) in ("active", "expiring_soon", "grace")


def get_notifications_payload(db: Session, user: User) -> dict:
    """Return the GET payload for the notifications page."""
    return {
        "notify_trial_reminders":    bool(user.notify_trial_reminders),
        "notify_announcement_email": bool(user.notify_announcement_email),
        "trial_toggle_applies":      trial_toggle_applies(db, user),
        "role":                      user.role or "",
    }


def update_notifications(
    db: Session, user: User, *,
    notify_trial_reminders:    Optional[bool] = None,
    notify_announcement_email: Optional[bool] = None,
) -> None:
    """Apply changes. None = don't touch. Caller commits.

    No validation — booleans only. Pydantic enforces type at the
    boundary; if the SPA somehow sends a non-bool the route
    returns 422 before reaching here."""
    if notify_trial_reminders is not None:
        user.notify_trial_reminders = bool(notify_trial_reminders)
    if notify_announcement_email is not None:
        user.notify_announcement_email = bool(notify_announcement_email)
    db.flush()
