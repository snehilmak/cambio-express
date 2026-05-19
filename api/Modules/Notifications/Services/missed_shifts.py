"""Missed-shift digest — per-store, once-a-day email + push.

Phase 2 of the late-arrival / no-show backlog item.  Phase 1
(PR #625) shipped the "Late by Xm" badge that reads at table
time; this service runs out-of-band at end-of-day and notifies
admins / owners about shifts on the prior day that had **no
clock-in at all** — the cashier didn't show up.

Pattern mirrors ``Notifications/Services/daily_summary``:

  - **Pure queries**: ``find_missed_shifts`` + ``eligible_recipients``
    return rows without sending anything.  Trivial to unit-test.
  - **Side-effect orchestrator**: ``run(session, on_date=None)``
    is the cron entry point — iterates active stores, identifies
    missed shifts, sends one email per recipient (skipping
    stores with no misses).
  - **Worker entry**: ``send_missed_shift_digest(on_date_iso)``
    opens its own ``SessionLocal`` for the D5 enqueue pattern.

Recipient gating reuses the existing ``User.notify_daily_summary``
toggle since the audience (admins + linked owners) and intent
(close-out alerts) overlap.  A user opted out of daily summaries
won't get the missed-shift digest either; we can split into a
separate toggle if/when operators ask for it.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, time, timedelta
from typing import Any, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session


_log = logging.getLogger(__name__)


def find_missed_shifts(
    db: Session,
    *,
    store_id: int,
    on_date: date,
) -> list[Any]:
    """Return the ``TimeClockShift`` rows on ``on_date`` for
    ``store_id`` that have no corresponding ``TimeClockEntry``
    for the same ``(store_employee_id, shift_date)``.

    "Matching entry" is defined loosely: any clock-in on the
    shift's date for the same employee counts, regardless of
    whether the times overlap.  A cashier who scheduled 9-5,
    arrived at noon, and clocked in is NOT flagged as missed
    — the late-arrival badge in phase 1 handles that case.

    Pure read — caller commits nothing.
    """
    from api.Modules.TimeClock.Models import TimeClockEntry, TimeClockShift

    shifts = (
        db.query(TimeClockShift)
          .filter(
              TimeClockShift.store_id == store_id,
              TimeClockShift.shift_date == on_date,
          )
          .all()
    )
    if not shifts:
        return []

    # Build the set of (employee, date) pairs that have at least
    # one entry — one query covers all shifts.
    employee_ids = {int(s.store_employee_id) for s in shifts}
    start = datetime.combine(on_date, time.min)
    end   = datetime.combine(on_date + timedelta(days=1), time.min)
    entries = (
        db.query(TimeClockEntry.store_employee_id)
          .filter(
              TimeClockEntry.store_id == store_id,
              TimeClockEntry.store_employee_id.in_(employee_ids),
              TimeClockEntry.clock_in_at >= start,
              TimeClockEntry.clock_in_at <  end,
          )
          .all()
    )
    punched_in = {int(eid) for (eid,) in entries}
    return [
        s for s in shifts
        if int(s.store_employee_id) not in punched_in
    ]


def eligible_recipients(db: Session, store: Any) -> list[Any]:
    """Admins + linked owners with email set + the daily-summary
    toggle on + no hard-bounce flag.

    Reuses the daily-summary toggle by design — the audience
    (admins + owners) and intent (close-out close-of-day
    info) overlap.  Splitting into its own column is a
    follow-up if operators ask.
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
              User.notify_daily_summary == True,  # noqa: E712
              User.email_bounced_at.is_(None),
              or_(*conds),
          )
          .all()
    )
    # Dedup by user id — an owner linked to multiple stores can
    # match the join multiple times.
    return list({u.id: u for u in candidates}.values())


def _employee_name(db: Session, store_employee_id: int) -> str:
    from api.Modules.Tenancy.Models import StoreEmployee
    row = db.get(StoreEmployee, store_employee_id)
    return str(row.name) if row is not None else f"#{store_employee_id}"


def _fmt_time(t: time) -> str:
    """``time(9, 0)`` → ``"9:00 AM"``.  Drops leading zero on the
    hour for readability; AM/PM in 12-hour for the most common US
    operator base.  i18n is a separate backlog item."""
    h = t.hour % 12 or 12
    suffix = "AM" if t.hour < 12 else "PM"
    return f"{h}:{t.minute:02d} {suffix}"


def _format_digest_body(
    db: Session,
    *,
    store_name: str,
    on_date: date,
    missed: list[Any],
) -> tuple[str, str]:
    """Return ``(subject, plain_body)`` for the digest email.

    Keeps the body small — operators want the list of names +
    shift times, not a full report.  Plain-text only for v1; an
    HTML template can drop in once we have a Jinja file for it.
    """
    date_str = on_date.strftime("%a %b %d, %Y")
    subject = f"{store_name} — {len(missed)} missed shift" + (
        "s" if len(missed) != 1 else ""
    ) + f" · {date_str}"
    lines = [
        f"Missed shifts on {date_str} at {store_name}:",
        "",
    ]
    for s in missed:
        name = _employee_name(db, int(s.store_employee_id))
        lines.append(
            f"  · {name} — scheduled {_fmt_time(s.start_time)} to "
            f"{_fmt_time(s.end_time)}",
        )
    lines += [
        "",
        "No clock-in recorded for these cashiers on the planned "
        "date.  Re-schedule or back-fill via the admin time-clock "
        "page if the punch was actually made on a different "
        "terminal.",
    ]
    return subject, "\n".join(lines)


def run(
    db: Session,
    *,
    on_date: Optional[date] = None,
    base_url: Optional[str] = None,
) -> int:
    """Cron orchestrator.  Iterates active stores, finds missed
    shifts on ``on_date`` (defaults to yesterday), and emails +
    pushes the digest to opted-in admins/owners.

    Returns the count of notifications attempted (one per
    recipient).  Idempotent at the per-store level via
    ``Store.missed_shifts_sent_for`` so a re-run on the same
    day skips already-sent stores.

    Stores with zero missed shifts get nothing — empty inbox >
    "good news!" emails.
    """
    if on_date is None:
        on_date = (datetime.utcnow() - timedelta(days=1)).date()

    from api.Modules.Notifications.Services.push import (
        send_push, user_wants_push,
    )
    from api.Modules.Notifications.Services.smtp import send_email
    from api.Modules.Tenancy.Models import Store

    base_url = (
        base_url
        or os.environ.get("APP_BASE_URL")
        or "https://dinerobook.com"
    ).rstrip("/")

    stores = (
        db.query(Store)
          .filter(
              Store.is_active == True,  # noqa: E712 — SQLAlchemy boolean
          )
          .all()
    )

    attempted = 0
    for store in stores:
        # Dedup: skip stores already notified for this date.
        sent_for = getattr(store, "missed_shifts_sent_for", None)
        if sent_for == on_date:
            continue
        misses = find_missed_shifts(
            db, store_id=int(store.id), on_date=on_date,
        )
        if not misses:
            # Stamp the marker so a same-day re-run skips this
            # store rather than re-querying.
            setattr(store, "missed_shifts_sent_for", on_date)
            continue
        recipients = eligible_recipients(db, store)
        subject, body = _format_digest_body(
            db,
            store_name=str(store.name or "Your store"),
            on_date=on_date,
            missed=misses,
        )
        for u in recipients:
            send_email(db, str(u.email), subject, body)
            try:
                if user_wants_push(u, "missed_shift"):
                    send_push(
                        db,
                        user_id=int(u.id),
                        title=subject,
                        body=f"{len(misses)} missed shift"
                             + ("s" if len(misses) != 1 else "")
                             + " — tap to review.",
                        url="/app/admin/timeclock/schedule",
                        tag=f"missed_shifts:{store.id}:{on_date.isoformat()}",
                    )
            except Exception as exc:  # pragma: no cover — push is best-effort
                _log.warning(
                    "missed-shift push failed for user %s: %s", u.id, exc,
                )
            attempted += 1
        setattr(store, "missed_shifts_sent_for", on_date)
    db.commit()
    return attempted


def send_missed_shift_digest(on_date_iso: Optional[str] = None) -> int:
    """Worker entry-point for the D5 enqueue pattern.  Takes a
    primitive ``on_date_iso`` so RQ can pickle the args; opens
    its own ``SessionLocal`` since the request session is
    closed by the time the worker runs.
    """
    from api.Core.Database import SessionLocal

    parsed: Optional[date] = None
    if on_date_iso:
        try:
            parsed = date.fromisoformat(on_date_iso)
        except ValueError:
            _log.warning(
                "send_missed_shift_digest: bad on_date_iso=%r — "
                "falling back to yesterday", on_date_iso,
            )
    with SessionLocal() as session:
        return run(session, on_date=parsed)
