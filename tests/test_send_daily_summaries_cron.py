"""Daily-summary cron — end-to-end invocation test.

``render.yaml`` declares a daily cron that runs
``python -m scripts.send_daily_summaries``. The Service-level
logic is covered by
``tests/Modules/Notifications/test_daily_summary.py``; this file's
narrower job is to confirm the standalone script's ``main()`` is
callable, accepts ``--date YYYY-MM-DD``, and exits 0 — exactly
what cron invokes nightly.
"""
from __future__ import annotations


def test_summaries_script_runs_clean_on_empty_db(capsys):
    """``main()`` exits 0 on a freshly-seeded test DB (no extra
    transfers / reports beyond the conftest seeds). Prints the
    canonical summary line so an ops dashboard scraping cron logs
    has a stable string to count on."""
    from scripts.send_daily_summaries import main

    rc = main([])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "daily-summary email(s) for yesterday." in out


def test_summaries_script_accepts_explicit_date(capsys):
    """``--date 2026-05-15`` backfills a specific day. Useful
    when an earlier cron run failed and the operator wants to
    replay it from the shell."""
    from scripts.send_daily_summaries import main

    rc = main(["--date", "2026-05-15"])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "for 2026-05-15." in out


def test_summaries_script_rejects_bad_date(capsys):
    """A malformed ``--date`` value gets rejected with a non-zero
    exit instead of trickling into the orchestrator and crashing
    halfway through the cron run."""
    from scripts.send_daily_summaries import main

    rc = main(["--date", "not-a-date"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "Bad --date" in err
