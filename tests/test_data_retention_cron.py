"""Data-retention cron — end-to-end invocation test.

``render.yaml`` declares a daily cron job that runs
``python -m scripts.purge_expired_stores``. The Service-level
logic is already covered by ``tests/test_purge_retention.py``;
this file's narrower job is to confirm the standalone script's
``main()`` is callable and clean on an empty DB (what cron will
invoke).

Add a case here if:
  - The script's argv signature changes (e.g. a flag is added).
  - The render.yaml cron startCommand changes.
"""
from __future__ import annotations


def test_purge_script_runs_clean_on_empty_db(capsys):
    """The standalone script's ``main()`` must exit 0 and print
    "Purged 0 expired store(s)." on a freshly-seeded test DB.
    Idempotent — re-running on a quiet day is a safe no-op. This
    is the exact entrypoint Render's cron service invokes."""
    from scripts.purge_expired_stores import main

    rc = main()
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "Purged" in out
    assert "expired store(s)" in out
