"""Data-retention cron — end-to-end invocation tests.

``render.yaml`` declares a daily cron job that runs
``python -m scripts.purge_expired_stores``. The Service-level logic
is already covered by ``tests/test_purge_retention.py`` — this
file's narrower job is to confirm:

  - The standalone script's ``main()`` is callable and clean on an
    empty DB (what cron will invoke).
  - The legacy ``flask purge-expired-stores`` CLI wrapper still
    works (back-compat for any operator running the old form
    during the rollout window).

Add a case here if:
  - The script's argv signature changes (e.g. a flag is added).
  - The render.yaml cron startCommand changes.
"""
from __future__ import annotations

from flask.testing import FlaskCliRunner

from app import app as flask_app


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


def test_purge_cli_runs_clean_on_empty_db():
    """Legacy back-compat path: ``flask purge-expired-stores``
    still works. Kept for the rollout window between the standalone
    script landing and ``app.py`` being deleted."""
    runner: FlaskCliRunner = flask_app.test_cli_runner()
    result = runner.invoke(args=["purge-expired-stores"])
    assert result.exit_code == 0, result.output
    assert "Purged" in result.output
    assert "expired store(s)" in result.output


def test_purge_cli_registered_under_expected_name():
    """Regression guard against a refactor that silently renames
    the click command — same expectation as before, kept until the
    legacy CLI goes away in Step 8."""
    names = list(flask_app.cli.commands.keys())
    assert "purge-expired-stores" in names, names
