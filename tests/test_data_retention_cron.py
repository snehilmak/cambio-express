"""Data-retention cron — end-to-end CLI invocation test.

`render.yaml` declares a daily cron job that runs
`flask purge-expired-stores`. The Service-level logic is already
covered by `tests/test_purge_retention.py` — this file's narrower
job is to confirm the Flask CLI wrapper IS callable as the cron
will invoke it (Click's `CliRunner` exercises the same code path
`flask <name>` takes).

Add a case here if:
  - The CLI's argv signature changes (e.g. a flag is added).
  - The render.yaml cron startCommand changes.
"""
from __future__ import annotations

from flask.testing import FlaskCliRunner

from app import app as flask_app


def test_purge_cli_runs_clean_on_empty_db():
    """With no expired stores, the CLI must exit 0 and print
    "Purged 0 expired store(s)." Idempotent — re-running on a
    quiet day is a safe no-op."""
    runner: FlaskCliRunner = flask_app.test_cli_runner()
    result = runner.invoke(args=["purge-expired-stores"])
    assert result.exit_code == 0, result.output
    assert "Purged" in result.output
    assert "expired store(s)" in result.output


def test_purge_cli_registered_under_expected_name():
    """The Render cron startCommand calls `flask
    purge-expired-stores`. Regression guard against a refactor
    that silently renames the click command."""
    # Walk the registered CLI commands and confirm the entry exists.
    names = list(flask_app.cli.commands.keys())
    assert "purge-expired-stores" in names, names
