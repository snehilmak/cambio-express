"""Locked-day digest email — recipients + static copy.

Fired when a daily book is locked via the React editor's
"Lock day" button (or the legacy /daily/<date>/lock route, while
that still serves). Sends a one-page summary to the store's admins
+ linked owners so the owner sees the day's close-out without
having to dig into the SPA.

Per the trial-reminder pattern (PR #65) only the static copy +
recipient query live in this Service; the actual SMTP delivery +
Flask template render stay in app.py (`send_locked_day_digest`).

Idempotency note: we DON'T stamp a "digest_sent_at" on the
DailyReport — re-locking after an unlock + edit cycle is a
legitimate trigger (a corrected close-out) and the cashier hitting
"Lock day" twice in a row would already be a no-op at the Service
layer (already-locked re-locks don't audit, and the React editor
only fires once per click).
"""
from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session


LOCKED_DAY_SUBJECT = "Daily book locked — {store_name}, {date_human}"


LOCKED_DAY_BODY = """\
Hi {name},

The daily book for "{store_name}" on {date_human} was just locked
by {locked_by}.

  Receipts          {receipts}
  Disbursements     {disbursements}
  Over / short      {over_short}
  Net position      {net}

Open the day in DineroBook:
    {view_url}

You're getting this digest because you're listed as an owner or
admin of {store_name}. Turn it off on your notifications page:
    {notifications_url}

— DineroBook
"""


def eligible_recipients(db: Session, store) -> list:
    """Users who should get the digest for this store: admins +
    linked owners (via StoreOwnerLink) with `email` set and
    `notify_locked_day_digest=True`.

    Same dedup contract as `eligible_recipients` for trial
    reminders — the multi-store owner pattern means an owner's
    `User` row often sits in a different store, but
    `StoreOwnerLink` carries them in here.
    """
    from api.Modules.Tenancy.Models import StoreOwnerLink, User

    owner_user_ids = [
        link.owner_id for link in
        db.query(StoreOwnerLink).filter_by(store_id=store.id).all()
    ]
    conds = [User.store_id == store.id]
    if owner_user_ids:
        conds.append(User.id.in_(owner_user_ids))
    candidates = (
        db.query(User)
          .filter(
              User.is_active == True,  # noqa: E712 — SQLAlchemy boolean
              User.role.in_(("admin", "owner")),
              User.email != "",
              User.notify_locked_day_digest == True,  # noqa: E712
              or_(*conds),
          )
          .all()
    )
    return list({u.id: u for u in candidates}.values())
