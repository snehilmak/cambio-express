"""Trial-reminder Service: who gets the reminder + the static
subject/body templates the reminder uses.

The actual mail delivery + template rendering stay in app.py for
now (they need Flask's `render_template` + the Resend SDK
wrapper). What this module owns:

  - `TRIAL_REMINDER_SUBJECT` / `TRIAL_REMINDER_BODY` constants
    (changing copy means editing one place).
  - `stores_due_for_reminder(db, now)` — every trial store whose
    trial ends in ≤ 3 days and hasn't been reminded yet.
  - `eligible_recipients(db, store)` — admins + owners of the
    store with email + `notify_trial_reminders=True`.
    Owners that live in another store's user row but are linked
    via `StoreOwnerLink` count too.

Per CLAUDE.md the trial-reminder dedup flag is
`Store.trial_reminder_sent_at`. The cron caller stamps it after
sending; the cancellation Service clears it on resubscribe so a
second trial (post-reactivation) gets its own fresh reminder.
"""
from datetime import datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from api.Modules.Billing.Services.trial import (
    EXPIRING_SOON_THRESHOLD_DAYS,
    get_trial_status,
)


TRIAL_REMINDER_SUBJECT = "Your DineroBook trial ends in {days} days"

TRIAL_REMINDER_BODY = """\
Hi {name},

Just a heads-up that your DineroBook trial for "{store_name}" ends on
{trial_end_date}. That's {days} days from today.

To keep your books, reports, and transfer history, subscribe before
then:
    {subscribe_url}

No action is required if you'd rather let the trial expire; we keep
your data for 180 days after cancellation so you can come back.

Don't want trial reminders anymore? Turn them off on your
notifications page:
    {notifications_url}

— DineroBook
"""


def stores_due_for_reminder(db: Session, now: datetime | None = None):
    """Trial stores whose trial ends within
    `EXPIRING_SOON_THRESHOLD_DAYS` (3) days and haven't been
    reminded yet. Returns a list of `Store` rows.

    The status check is delegated to `get_trial_status` so the
    "expiring_soon" definition stays in one place.
    """
    from app import Store
    if now is None:
        now = datetime.utcnow()
    candidates = (
        db.query(Store)
          .filter(
              Store.plan == "trial",
              Store.trial_ends_at.isnot(None),
              Store.trial_reminder_sent_at.is_(None),
          )
          .all()
    )
    return [s for s in candidates if get_trial_status(s) == "expiring_soon"]


def eligible_recipients(db: Session, store) -> list:
    """Users who should get the reminder for this store: admins +
    owners with `email` set and `notify_trial_reminders=True`.

    Owners linked via `StoreOwnerLink` are picked up even though
    their `User` row sits in a different store (the multi-store
    owner pattern).

    Deduplicated — the same user could be both admin of this
    store and an owner-link target.
    """
    from app import StoreOwnerLink, User
    # NOTE: the legacy `app._trial_reminder_recipients` referenced
    # `link.user_id` which doesn't exist on `StoreOwnerLink` (the
    # FK column is `owner_id`). That code path never fired in
    # production because trial stores don't have owner-links, but
    # the Service uses the correct attribute so the multi-store
    # owner case actually works the day a trial store gets one.
    owner_user_ids = [
        link.owner_id for link in
        db.query(StoreOwnerLink).filter_by(store_id=store.id).all()
    ]
    conds = [User.store_id == store.id]
    if owner_user_ids:
        # Owners live in a different store's user row but link back.
        conds.append(User.id.in_(owner_user_ids))
    candidates = (
        db.query(User)
          .filter(
              User.is_active == True,  # noqa: E712 — SQLAlchemy boolean
              User.role.in_(("admin", "owner")),
              User.email != "",
              User.notify_trial_reminders == True,  # noqa: E712
              or_(*conds),
          )
          .all()
    )
    # Same user could be an owner AND an admin of this store.
    return list({u.id: u for u in candidates}.values())
