"""TimeClock — Models.

``TimeClockEntry`` holds one row per employee shift. The shift
is scoped per ``StoreEmployee`` (the human roster row), not per
``User`` (the login) — multiple cashiers commonly share one
in-store ``employee`` login. The login that initiated / closed
the punch is captured separately for audit.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Index, Integer,
    LargeBinary, String,
)

from api.Core.Database import Base


class TimeClockEntry(Base):
    __tablename__ = "time_clock_entry"

    id                  = Column(Integer, primary_key=True)
    store_id            = Column(
        Integer, ForeignKey("store.id"), nullable=False, index=True,
    )
    store_employee_id   = Column(
        Integer, ForeignKey("store_employee.id"),
        nullable=False, index=True,
    )
    # The User session that initiated the clock-in. Often the
    # shared per-store ``employee`` login; sometimes a personal
    # admin login if the cashier-roster row maps to an admin too.
    clock_in_user_id    = Column(Integer, ForeignKey("user.id"), nullable=True)
    # The User session that closed the shift. May differ from
    # ``clock_in_user_id`` if the shift starts on a counter
    # terminal and ends on a back-office laptop.
    clock_out_user_id   = Column(Integer, ForeignKey("user.id"), nullable=True)
    # UTC timestamps; SPA formats per ``Store.timezone``.
    clock_in_at         = Column(DateTime, nullable=False, default=datetime.utcnow)
    clock_out_at        = Column(DateTime, nullable=True)
    # Denormalized so payroll rollups don't have to subtract on
    # every row. Computed at clock-out.
    hours_worked        = Column(Float, nullable=True)
    notes               = Column(String(500), default="")
    # Break tracking. ``break_started_at`` is set while the
    # cashier is on break (non-null = currently paused);
    # ``break_minutes`` is the running total across multiple
    # pause/resume cycles inside the same shift. ``clock_out``
    # subtracts ``break_minutes`` from the elapsed wall-clock
    # to compute ``hours_worked``, so a 9-to-5 shift with a
    # 60-min lunch records 7.0 hours.
    break_started_at    = Column(DateTime, nullable=True)
    break_minutes       = Column(Float, default=0.0, nullable=True)
    # Payroll workflow status. ``pending`` is the default for
    # fresh entries (clock-in / clock-out / admin back-fill);
    # the admin moves rows to ``approved`` before they count
    # toward payroll, or ``rejected`` if the shift shouldn't be
    # paid. ``approved_hours`` is the headline payroll number
    # on the admin view.
    status              = Column(String(20), default="pending", nullable=True)
    # True whenever an admin has edited the row after the fact.
    # Set automatically by ``admin_update_entry`` on any
    # non-no-op patch. Surfaces as an "Adjusted: Yes" badge in
    # the admin view so a payroll reviewer can spot rows that
    # don't match what the cashier originally punched.
    adjusted            = Column(Boolean, default=False, nullable=True)

    __table_args__ = (
        # "Is this employee currently clocked in?" — open rows
        # have ``clock_out_at IS NULL``. Composite index keeps
        # the lookup a single index probe per employee.
        Index("ix_time_clock_employee_open",
              "store_employee_id", "clock_out_at"),
    )


class StoreEmployeePasskey(Base):
    """One row per roster member's registered WebAuthn passkey.

    Distinct from the user-side ``Passkey`` table because
    multiple cashiers commonly share a single ``employee``
    ``User`` login in this codebase — user→passkey doesn't
    identify the cashier, roster→passkey does. The admin
    registers each active roster member's device once from the
    Settings → Time clock credentials page; afterwards every
    clock-in / clock-out demands a fresh assertion against the
    same credential when ``Store.timeclock_require_passkey``
    is True.

    v1 caps at one passkey per roster row (the unique
    constraint on ``store_employee_id`` enforces that). If a
    cashier swaps devices the admin deletes the old row and
    re-registers.
    """

    __tablename__ = "store_employee_passkey"

    id                    = Column(Integer, primary_key=True)
    store_id              = Column(
        Integer, ForeignKey("store.id"),
        nullable=False, index=True,
    )
    store_employee_id     = Column(
        Integer, ForeignKey("store_employee.id"),
        nullable=False, unique=True,
    )
    # WebAuthn credential metadata — same shape as the user-side
    # ``Passkey`` table. ``credential_id`` is up to 1023 bytes per
    # spec; we store the raw bytes (LargeBinary, not text-encoded).
    credential_id         = Column(
        LargeBinary, unique=True, nullable=False,
    )
    public_key            = Column(LargeBinary, nullable=False)
    sign_count            = Column(Integer, default=0, nullable=False)
    aaguid                = Column(String(64), default="")
    # Display name the admin assigns at registration time
    # ("Maria's iPhone", "Punch terminal Touch ID", etc.).
    name                  = Column(String(120), default="")
    registered_at         = Column(DateTime, default=datetime.utcnow)
    last_used_at          = Column(DateTime, nullable=True)
    # User session that walked the cashier through registration —
    # for the admin audit-trail view.
    registered_by_user_id = Column(
        Integer, ForeignKey("user.id"), nullable=True,
    )


__all__ = ["StoreEmployeePasskey", "TimeClockEntry"]
