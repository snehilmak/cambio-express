"""Locked-day digest email — recipients + fanout orchestrator.

Fired when a daily book is locked via the React editor's
"Lock day" button (or the legacy /daily/<date>/lock route, while
that still serves). Sends a one-page summary to the store's admins
+ linked owners so the owner sees the day's close-out without
having to dig into the SPA.

Two halves:

  - **Pure queries**: ``eligible_recipients`` returns rows without
    sending anything. Easy to unit-test.
  - **Side-effect orchestrator**: ``run(session, report,
    base_url=None)`` is the SMTP fanout — renders the email body
    + delivers via ``smtp.send_email``.

Idempotency note: we DON'T stamp a "digest_sent_at" on the
DailyReport — re-locking after an unlock + edit cycle is a
legitimate trigger (a corrected close-out) and the cashier hitting
"Lock day" twice in a row would already be a no-op at the Service
layer (already-locked re-locks don't audit, and the React editor
only fires once per click).
"""
from __future__ import annotations

import logging
import os

from sqlalchemy import or_
from sqlalchemy.orm import Session

from api.Modules.Notifications.Services.format import fmt_money_2 as _fmt_money_2
from api.Modules.Notifications.Services.smtp import send_email
from api.Modules.Notifications.Services.templates import render_email_template
from typing import Any
from api.Core.Clock import utc_now


_log = logging.getLogger(__name__)


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


def eligible_recipients(db: Session, store: Any) -> list[Any]:
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


def run(session: Session, report: Any, base_url: str | None = None) -> int:
    """Mail the daily-book close-out summary to every eligible
    recipient (admins + linked owners with the toggle on). Returns
    the count of emails actually sent.

    Safe to call inside the lock route — failures during email
    send don't roll back the lock (we catch + log, matching the
    trial-reminder cron's policy of "deliverability is
    best-effort, don't punish the user for a flaky SMTP").

    The caller owns the session lifecycle.
    """
    from api.Modules.Tenancy.Models import Store, User

    if report is None or report.store_id is None:
        return 0
    store = session.get(Store, report.store_id)
    if store is None:
        return 0
    base_url = (
        base_url
        or os.environ.get("APP_BASE_URL")
        or "https://dinerobook.com"
    ).rstrip("/")
    date_iso = report.report_date.isoformat() if report.report_date else ""
    date_human = (
        report.report_date.strftime("%B %d, %Y")
        if report.report_date else ""
    )
    locked_by_user = (
        session.get(User, report.locked_by) if report.locked_by else None
    )
    locked_by_name = (
        (locked_by_user.full_name or locked_by_user.username)
        if locked_by_user else "an admin"
    )
    view_url = f"{base_url}/app/daily/edit?date={date_iso}"
    notifications_url = f"{base_url}/app/account/notifications"

    receipts = float(report.total_receipts or 0)
    disbursements = float(report.total_disbursements or 0)
    over_short = float(report.over_short or 0)
    net = receipts - disbursements + over_short

    try:
        recipients = eligible_recipients(session, store)
    except Exception:
        _log.exception("locked-day digest: recipient query failed")
        return 0

    sent = 0
    for u in recipients:
        body = LOCKED_DAY_BODY.format(
            name=u.full_name or u.username,
            store_name=store.name,
            date_human=date_human,
            locked_by=locked_by_name,
            receipts=_fmt_money_2(receipts),
            disbursements=_fmt_money_2(disbursements),
            over_short=_fmt_money_2(over_short),
            net=_fmt_money_2(net),
            view_url=view_url,
            notifications_url=notifications_url,
        )
        try:
            html = render_email_template(
                "emails/locked_day_digest.html",
                preheader=(
                    f"Daily book locked for {store.name} on "
                    f"{date_human}. Net {_fmt_money_2(net)}."
                ),
                name=u.full_name or "",
                store_name=store.name,
                date_human=date_human,
                locked_by=locked_by_name,
                receipts=_fmt_money_2(receipts),
                disbursements=_fmt_money_2(disbursements),
                over_short=_fmt_money_2(over_short),
                net=_fmt_money_2(net),
                net_negative=(net < 0),
                view_url=view_url,
                notifications_url=notifications_url,
                year=utc_now().year,
                base_url=base_url,
            )
            subject = LOCKED_DAY_SUBJECT.format(
                store_name=store.name, date_human=date_human,
            )
            if send_email(session, u.email, subject, body, html):
                sent += 1
            # Fan out a Web Push too — gated on the per-kind toggle.
            # Tag is scoped to (store, date) so a re-lock (rare,
            # admin reopens + relocks) coalesces with the original.
            try:
                from api.Modules.Notifications.Services.push import (
                    send_push, user_wants_push,
                )
                if user_wants_push(u, "locked_day_digest"):
                    send_push(
                        session,
                        user_id=int(u.id),
                        title=subject,
                        body=(
                            f"Locked by {locked_by_name}. "
                            f"Net {_fmt_money_2(net)}."
                        ),
                        url=f"/app/daily/edit?date={date_iso}",
                        tag=f"locked_day_digest:{store.id}:{date_iso}",
                    )
            except Exception as exc:  # pragma: no cover — push best-effort
                _log.warning(
                    "locked-day digest push failed for user %s: %s",
                    u.id, exc,
                )
        except Exception:
            _log.exception(
                "locked-day digest: send failed for user_id=%s", u.id,
            )
    return sent


def send_locked_day_digest(report_id: int) -> int:
    """Worker entry-point for the locked-day digest fan-out.

    Takes a primitive ``report_id`` (not the SQLAlchemy ORM
    object) so the function can be queued by RQ — see
    ``api.Core.Jobs.enqueue``. Opens its own ``SessionLocal``
    since the caller's session is already closed by the time
    the worker runs.

    Returns the number of digest emails sent, mirroring the
    underlying ``run()`` signature.
    """
    from api.Core.Database import SessionLocal
    from api.Modules.DailyBook.Models import DailyReport

    with SessionLocal() as session:
        report = session.get(DailyReport, report_id)
        if report is None:
            import logging
            logging.getLogger(__name__).warning(
                "locked-day digest worker called for report_id=%s "
                "but row disappeared; skipping.", report_id,
            )
            return 0
        return run(session, report)
