"""Trial-reminder Service: eligibility queries + the daily-cron
``run()`` orchestrator.

Two halves:

  - **Pure queries**: ``stores_due_for_reminder`` and
    ``eligible_recipients`` return rows without sending anything,
    so they're easy to unit-test.
  - **Side-effect orchestrator**: ``run(session, now=None,
    base_url=None)`` is the cron entry point — it fans out an
    email to every eligible recipient and stamps
    ``Store.trial_reminder_sent_at`` for dedup.

Per CLAUDE.md the trial-reminder dedup flag is
``Store.trial_reminder_sent_at``. ``run()`` stamps it after
sending; the cancellation Service clears it on resubscribe so a
second trial (post-reactivation) gets its own fresh reminder.
"""
import os
from datetime import datetime
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from api.Modules.Billing.Services.trial import (
    EXPIRING_SOON_THRESHOLD_DAYS,
    get_trial_status,
)
from api.Modules.Notifications.Services.smtp import send_email
from api.Modules.Notifications.Services.templates import render_email_template


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


def stores_due_for_reminder(db: Session, now: datetime | None = None) -> list[Any]:
    """Trial stores whose trial ends within
    `EXPIRING_SOON_THRESHOLD_DAYS` (3) days and haven't been
    reminded yet. Returns a list of `Store` rows.

    The status check is delegated to `get_trial_status` so the
    "expiring_soon" definition stays in one place.
    """
    from api.Modules.Tenancy.Models import Store
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


def eligible_recipients(db: Session, store: Any) -> list[Any]:
    """Users who should get the reminder for this store: admins +
    owners with `email` set and `notify_trial_reminders=True`.

    Owners linked via `StoreOwnerLink` are picked up even though
    their `User` row sits in a different store (the multi-store
    owner pattern).

    Deduplicated — the same user could be both admin of this
    store and an owner-link target.
    """
    from api.Modules.Tenancy.Models import StoreOwnerLink, User
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


def run(
    session: Session,
    *,
    now: datetime | None = None,
    base_url: str | None = None,
) -> int:
    """Send the trial-ending reminder to every eligible recipient.

    Returns the count of emails actually sent (skipping users with
    no email or ``notify_trial_reminders=False``). Idempotent on
    ``trial_reminder_sent_at``; same-day reruns are a no-op.

    The caller owns the session lifecycle — this function commits
    inside the session when at least one email goes out (so the
    dedup stamp lands), but never closes the session.
    """
    if now is None:
        now = datetime.utcnow()
    if base_url is None:
        base_url = os.environ.get("APP_BASE_URL", "https://dinerobook.com")

    sent = 0
    for store in stores_due_for_reminder(session, now):
        days_left = max(0, (store.trial_ends_at - now).days)
        trial_end_str = store.trial_ends_at.strftime("%B %d, %Y")
        subscribe_url = f"{base_url}/subscribe"
        notifications_url = f"{base_url}/account/notifications"
        any_sent = False
        for u in eligible_recipients(session, store):
            body = TRIAL_REMINDER_BODY.format(
                name=u.full_name or u.username,
                store_name=store.name,
                trial_end_date=trial_end_str,
                days=days_left,
                subscribe_url=subscribe_url,
                notifications_url=notifications_url,
            )
            html = render_email_template(
                "emails/trial_reminder.html",
                preheader=(
                    f"Your DineroBook trial for {store.name} "
                    f"ends on {trial_end_str}."
                ),
                name=u.full_name or "",
                store_name=store.name,
                trial_end_date=trial_end_str,
                days=days_left,
                subscribe_url=subscribe_url,
                notifications_url=notifications_url,
                year=now.year,
                base_url=base_url,
            )
            subject = TRIAL_REMINDER_SUBJECT.format(days=days_left)
            send_email(session, u.email, subject, body, html)
            # Fan out a Web Push too — best-effort, gated on the
            # per-kind toggle so a user who opted out of trial-
            # reminder pushes still gets the email.  Tag scoped to
            # the store so a later reminder for the same store
            # coalesces with the earlier one.
            try:
                from api.Modules.Notifications.Services.push import (
                    send_push, user_wants_push,
                )
                if user_wants_push(u, "trial_reminder"):
                    send_push(
                        session,
                        user_id=int(u.id),
                        title=subject,
                        body=(
                            f"Your DineroBook trial for "
                            f"{store.name} ends on {trial_end_str}."
                        ),
                        url="/app/admin/subscription",
                        tag=f"trial_reminder:{store.id}",
                    )
            except Exception as exc:  # pragma: no cover — push best-effort
                import logging
                logging.getLogger(__name__).warning(
                    "trial-reminder push failed for user %s: %s",
                    u.id, exc,
                )
            any_sent = True
            sent += 1
        if any_sent:
            store.trial_reminder_sent_at = now
    if sent:
        session.commit()
    return sent
