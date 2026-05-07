"""Calendar-date → naive datetime boundary helpers.

Two pure functions that every reporting query uses to convert a
date selection into the start / end of that period for SQL
timestamp comparisons (`BankTransaction.posted_at`,
`Transfer.created_at`, `EmailEvent.created_at`, etc).

Pure functions — no DB, no I/O.
"""
from datetime import date, datetime


def day_start(d: date) -> datetime:
    """`00:00:00` of the given date as a naive datetime.

    Used by every SA report data fn that converts a calendar
    date into the start of the period for SQL timestamp
    comparisons.
    """
    return datetime(d.year, d.month, d.day)


def day_end(d: date) -> datetime:
    """`23:59:59` of the given date as a naive datetime — the
    end-of-period counterpart to `day_start`.
    """
    return datetime(d.year, d.month, d.day, 23, 59, 59)
