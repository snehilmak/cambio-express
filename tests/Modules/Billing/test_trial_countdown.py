"""The trial countdown shown in the topbar (W-1).

A trial user previously got NO warning anywhere in the chrome —
nothing until the gate slammed. This is the countdown, and the rules
that keep it honest.
"""
from datetime import timedelta

import pytest

from api.Core.Clock import utc_now
from api.Modules.Billing.Services.trial import (
    trial_banner, trial_days_left,
)
from api.Modules.Tenancy.Models import Store
from tests._app import db, db_session
from tests.conftest import login_admin


def _store(store_id, *, plan="trial", hours_left=None, grace_days=4,
           frozen=False):
    with db_session():
        s = db.session.get(Store, store_id)
        s.plan = plan
        s.frozen_at = utc_now() if frozen else None
        if hours_left is None:
            s.trial_ends_at = None
            s.grace_ends_at = None
        else:
            s.trial_ends_at = utc_now() + timedelta(hours=hours_left)
            s.grace_ends_at = s.trial_ends_at + timedelta(days=grace_days)
        db.session.commit()
        return db.session.get(Store, store_id)


def test_days_left_rounds_up(test_store_id):
    """30 hours left must read as 2 days, not 1. A countdown that
    undersells the time it describes reads as a bug the first time
    someone checks a calendar."""
    s = _store(test_store_id, hours_left=30)
    assert trial_days_left(s) == 2


def test_a_few_hours_left_still_reads_as_a_day(test_store_id):
    s = _store(test_store_id, hours_left=3)
    assert trial_days_left(s) == 1
    assert "1 day left" in str(trial_banner(s)["message"])


def test_a_full_week_reads_as_seven(test_store_id):
    s = _store(test_store_id, hours_left=7 * 24)
    assert trial_days_left(s) == 7


def test_the_banner_is_present_from_day_one(test_store_id):
    """Not just near the end — an indicator that appears on day four
    reads as an alarm."""
    s = _store(test_store_id, hours_left=7 * 24)
    banner = trial_banner(s)
    assert banner is not None
    assert banner["status"] == "active"
    assert banner["tone"] == "neutral"


def test_the_tone_escalates_at_the_shared_threshold(test_store_id):
    """Reuses EXPIRING_SOON_THRESHOLD_DAYS so the chip, the status
    machine and the reminder cron never disagree about when to nag."""
    from api.Modules.Billing.Services.trial import (
        EXPIRING_SOON_THRESHOLD_DAYS,
    )
    assert EXPIRING_SOON_THRESHOLD_DAYS == 3

    calm = trial_banner(_store(test_store_id, hours_left=5 * 24))
    assert calm["tone"] == "neutral"

    urgent = trial_banner(_store(test_store_id, hours_left=2 * 24))
    assert urgent["tone"] == "warning"
    assert urgent["status"] == "expiring_soon"


def test_a_paid_store_shows_nothing(test_store_id):
    """`trial: null` — the chip must not render for someone who
    already pays."""
    s = _store(test_store_id, plan="pro", hours_left=None)
    assert trial_banner(s) is None


def test_the_grace_window_says_read_only(test_store_id):
    s = _store(test_store_id, hours_left=-24)
    banner = trial_banner(s)
    assert banner["status"] == "grace"
    assert banner["tone"] == "negative"
    assert "view and export" in str(banner["message"])


def test_a_fully_expired_store_says_lapsed(test_store_id):
    s = _store(test_store_id, hours_left=-24 * 30)
    banner = trial_banner(s)
    assert banner["status"] == "expired"
    assert banner["tone"] == "negative"


def test_the_countdown_reaches_the_spa(client, test_store_id):
    """It has to actually arrive on the payload the shell reads."""
    _store(test_store_id, hours_left=2 * 24)
    token = login_admin(client, test_store_id)
    resp = client.get(
        "/api/v2/auth/session-status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    trial = resp.json()["trial"]
    assert trial is not None
    assert trial["days_left"] == 2
    assert trial["tone"] == "warning"
