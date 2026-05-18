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
    Column, DateTime, Float, ForeignKey, Index, Integer, String,
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

    __table_args__ = (
        # "Is this employee currently clocked in?" — open rows
        # have ``clock_out_at IS NULL``. Composite index keeps
        # the lookup a single index probe per employee.
        Index("ix_time_clock_employee_open",
              "store_employee_id", "clock_out_at"),
    )


__all__ = ["TimeClockEntry"]
