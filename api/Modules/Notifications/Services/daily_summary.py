"""Daily-summary digest — per-store nightly email.

Fired once a night by the ``send_daily_summaries`` cron (or
manually via the CLI). One email per store, one recipient per
opted-in admin / owner. Body carries the prior day's transfer
count + send-amount sum + receipts + disbursements + over/short
so the owner sees the close-out numbers in their inbox by
morning without having to log in.

Three halves:

  - **Pure queries**: ``stores_with_activity`` and
    ``eligible_recipients`` return rows without sending anything.
    Easy to unit-test.
  - **Aggregator**: ``compute_daily_totals(session, store_id, on_date)``
    rolls up Transfer + DailyReport into a single dict.
    Pure read, no commits.
  - **Side-effect orchestrator**: ``run(session, on_date=None)``
    is the cron entry point — iterates active stores, computes
    totals, renders the email + delivers via SMTP. Idempotent at
    the per-store level via ``Store.daily_summary_sent_for``
    (a date column) so a re-run on the same day is a no-op.

A store with zero transfers AND no daily-report row for the day
is skipped — nothing to summarize.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from api.Modules.Notifications.Services.smtp import send_email
from api.Modules.Notifications.Services.templates import render_email_template
from api.Core.Clock import utc_now


_log = logging.getLogger(__name__)


DAILY_SUMMARY_SUBJECT = (
    "Daily summary — {store_name}, {date_human}"
)


DAILY_SUMMARY_BODY = """\
Hi {name},

Here's yesterday's close-out for "{store_name}" ({date_human}):

  Transfers logged   {transfer_count}
  Send volume        {send_volume}
  Receipts           {receipts}
  Disbursements      {disbursements}
  Over / short       {over_short}
  Net position       {net}

Open the day in DineroBook:
    {view_url}

You're getting this digest because you're listed as an owner or
admin of {store_name}. Turn it off on your notifications page:
    {notifications_url}

— DineroBook
"""


@dataclass
class DailyTotals:
    """One day's roll-up for a single store. ``has_activity`` is
    True when there's a Transfer or DailyReport row to summarize —
    callers skip the email when False."""
    on_date:         date
    transfer_count:  int
    send_volume:     float
    receipts:        float
    disbursements:   float
    over_short:      float
    has_activity:    bool


def _fmt_money_2(n: float) -> str:
    try:
        return "${:,.2f}".format(float(n or 0))
    except (TypeError, ValueError):
        return "$0.00"


def compute_daily_totals(
    db: Session, store_id: int, on_date: date,
) -> DailyTotals:
    """Roll up Transfer + DailyReport activity for ``store_id`` on
    ``on_date``. Pure read — no commits.

    Excludes Canceled / Rejected transfers from the count + volume
    (matches the rest of the platform's revenue queries — see
    ``api.Modules.Owners.Services.OWNER_TRANSFER_EXCLUDED``).
    """
    from api.Modules.DailyBook.Models import DailyReport
    from api.Modules.Owners.Services import OWNER_TRANSFER_EXCLUDED
    from api.Modules.Transfers.Models import Transfer

    transfers = (
        db.query(Transfer)
          .filter(
              Transfer.store_id == store_id,
              Transfer.send_date == on_date,
              Transfer.status.notin_(OWNER_TRANSFER_EXCLUDED),
          )
          .all()
    )
    transfer_count = len(transfers)
    send_volume = sum(float(t.send_amount or 0) for t in transfers)

    report = (
        db.query(DailyReport)
          .filter_by(store_id=store_id, report_date=on_date)
          .one_or_none()
    )
    if report is not None:
        receipts      = float(report.total_receipts or 0)
        disbursements = float(report.total_disbursements or 0)
        over_short    = float(report.over_short or 0)
    else:
        receipts = disbursements = over_short = 0.0

    has_activity = transfer_count > 0 or report is not None
    return DailyTotals(
        on_date=on_date,
        transfer_count=transfer_count,
        send_volume=send_volume,
        receipts=receipts,
        disbursements=disbursements,
        over_short=over_short,
        has_activity=has_activity,
    )


def eligible_recipients(db: Session, store: Any) -> list[Any]:
    """Admins + linked owners with email set + the daily-summary
    toggle on + no recent hard bounce.

    Mirrors the ``locked_day_digest.eligible_recipients`` query
    so a user opted out of one digest stays opted out of that
    one only — the two toggles are independent."""
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
              User.notify_daily_summary == True,  # noqa: E712
              User.email_bounced_at.is_(None),
              or_(*conds),
          )
          .all()
    )
    return list({u.id: u for u in candidates}.values())


def stores_with_activity(db: Session, on_date: date) -> list[Any]:
    """Active stores that had at least one Transfer OR DailyReport
    row on ``on_date``. The cron iterates these — skipping idle
    stores keeps the inbox clean (no 0/0/0 summary emails for a
    store that didn't transact)."""
    from api.Modules.DailyBook.Models import DailyReport
    from api.Modules.Tenancy.Models import Store
    from api.Modules.Transfers.Models import Transfer

    transfer_store_ids = {
        sid for (sid,) in
        db.query(Transfer.store_id)
          .filter(Transfer.send_date == on_date)
          .distinct()
          .all()
    }
    report_store_ids = {
        sid for (sid,) in
        db.query(DailyReport.store_id)
          .filter(DailyReport.report_date == on_date)
          .distinct()
          .all()
    }
    store_ids = transfer_store_ids | report_store_ids
    if not store_ids:
        return []
    return (
        db.query(Store)
          .filter(Store.id.in_(store_ids), Store.is_active == True)  # noqa: E712
          .all()
    )


def run(
    session: Session, *,
    on_date: Optional[date] = None,
    base_url: Optional[str] = None,
) -> int:
    """Send one daily-summary email per (store × eligible recipient)
    for ``on_date`` (defaults to yesterday in UTC). Returns the
    total emails attempted.

    Idempotent: stamps ``Store.daily_summary_sent_for`` after a
    successful pass. A re-run on a store with the stamp already at
    ``on_date`` is a no-op. The cancellation Service does NOT
    clear the stamp — once we've sent for a day, we've sent.

    The caller owns the session lifecycle.
    """

    if on_date is None:
        on_date = date.today() - timedelta(days=1)
    base_url = (
        base_url
        or os.environ.get("APP_BASE_URL")
        or "https://dinerobook.com"
    ).rstrip("/")

    sent_total = 0
    stores = stores_with_activity(session, on_date)
    for store in stores:
        # Skip stores we've already summarized for this date — the
        # stamp lets a cron re-run safely (a flaky earlier pass can
        # be re-invoked without duplicating emails).
        if (
            getattr(store, "daily_summary_sent_for", None) == on_date
        ):
            continue

        try:
            totals = compute_daily_totals(session, store.id, on_date)
        except Exception:  # pragma: no cover — defensive log only
            _log.exception(
                "daily-summary: totals query failed for store_id=%s",
                store.id,
            )
            continue
        if not totals.has_activity:
            # stores_with_activity should have filtered this already,
            # but keep the defensive guard so a race window between
            # the discovery query and the per-store query doesn't
            # send a zero-totals email.
            continue

        try:
            recipients = eligible_recipients(session, store)
        except Exception:  # pragma: no cover — defensive log only
            _log.exception(
                "daily-summary: recipient query failed for store_id=%s",
                store.id,
            )
            continue

        date_iso = on_date.isoformat()
        date_human = on_date.strftime("%B %d, %Y")
        view_url = f"{base_url}/app/daily/edit?date={date_iso}"
        notifications_url = f"{base_url}/app/account/notifications"
        net = totals.receipts - totals.disbursements + totals.over_short
        subject = DAILY_SUMMARY_SUBJECT.format(
            store_name=store.name, date_human=date_human,
        )

        for user in recipients:
            body = DAILY_SUMMARY_BODY.format(
                name=user.full_name or user.username,
                store_name=store.name,
                date_human=date_human,
                transfer_count=totals.transfer_count,
                send_volume=_fmt_money_2(totals.send_volume),
                receipts=_fmt_money_2(totals.receipts),
                disbursements=_fmt_money_2(totals.disbursements),
                over_short=_fmt_money_2(totals.over_short),
                net=_fmt_money_2(net),
                view_url=view_url,
                notifications_url=notifications_url,
            )
            try:
                html = render_email_template(
                    "emails/daily_summary.html",
                    preheader=(
                        f"{totals.transfer_count} transfers · "
                        f"{_fmt_money_2(totals.send_volume)} sent"
                    ),
                    name=user.full_name or user.username,
                    store_name=store.name,
                    date_human=date_human,
                    transfer_count=totals.transfer_count,
                    send_volume=_fmt_money_2(totals.send_volume),
                    receipts=_fmt_money_2(totals.receipts),
                    disbursements=_fmt_money_2(totals.disbursements),
                    over_short=_fmt_money_2(totals.over_short),
                    net=_fmt_money_2(net),
                    net_negative=net < 0,
                    view_url=view_url,
                    notifications_url=notifications_url,
                    year=utc_now().year,
                    base_url=base_url,
                )
            except Exception:  # pragma: no cover — template path
                _log.exception(
                    "daily-summary: template render failed for "
                    "store_id=%s user_id=%s", store.id, user.id,
                )
                continue
            try:
                send_email(session, user.email, subject, body, html)
                sent_total += 1
            except Exception:  # pragma: no cover — best-effort SMTP
                _log.exception(
                    "daily-summary: send_email failed for "
                    "store_id=%s user_id=%s", store.id, user.id,
                )
            # Fan out a Web Push too — best-effort, doesn't block the
            # email path if VAPID isn't configured (helper short-
            # circuits to 0).  Honors the per-kind push toggle so a
            # user who opted out of daily-summary pushes still gets
            # the email.  Tagged so multi-device deliveries coalesce
            # into one notification per device.
            try:
                from api.Modules.Notifications.Services.push import (
                    send_push, user_wants_push,
                )
                if user_wants_push(user, "daily_summary"):
                    send_push(
                        session,
                        user_id=int(user.id),
                        title=subject,
                        body=(
                            f"{totals.transfer_count} transfers · "
                            f"{_fmt_money_2(totals.send_volume)} sent · "
                            f"net {_fmt_money_2(net)}"
                        ),
                        url=f"/app/daily/edit?date={date_iso}",
                        tag=f"daily_summary:{store.id}:{date_iso}",
                    )
            except Exception as exc:  # pragma: no cover — push best-effort
                _log.warning(
                    "daily-summary push failed for user %s: %s",
                    user.id, exc,
                )

        store.daily_summary_sent_for = on_date
        session.commit()

    return sent_total


def send_daily_summary(on_date_iso: Optional[str] = None) -> int:
    """Worker entry-point for the D5 enqueue pattern. Takes a
    primitive ``on_date_iso`` (so RQ can pickle the args) and opens
    its own ``SessionLocal`` since the request session is closed by
    the time the worker runs.

    Returns the count of emails attempted, mirroring ``run()``.
    """
    from api.Core.Database import SessionLocal

    parsed: Optional[date] = None
    if on_date_iso:
        try:
            parsed = date.fromisoformat(on_date_iso)
        except ValueError:
            _log.warning(
                "send_daily_summary: bad on_date_iso=%r — falling back "
                "to yesterday", on_date_iso,
            )
    with SessionLocal() as session:
        return run(session, on_date=parsed)
