"""Prod-secret safety gate regression tests.

`app.py` refuses to boot if `APP_BASE_URL=https://...` AND
`SECRET_KEY` is unset (signals a prod deploy still running the
dev-fallback signing key). Also emits a CRITICAL warning for
missing `SUPERADMIN_PASSWORD` / `ADMIN_PASSWORD` in prod.

These tests run in subprocesses so each one gets a fresh env
without polluting the test session's already-loaded `app`
module. See `tests/test_rate_limiting.py` for the same pattern.
"""
from __future__ import annotations

import os
import subprocess
import sys


def _run(script: str, *, env_overrides: dict) -> tuple[int, str, str]:
    env = {
        **os.environ,
        "DATABASE_URL": "sqlite:///:memory:",
        "STRIPE_SECRET_KEY": "sk_test_fake_key",
        "STRIPE_BASIC_PRICE_ID": "price_basic_test",
        "STRIPE_PRO_PRICE_ID": "price_pro_test",
        "STRIPE_WEBHOOK_SECRET": "whsec_test_secret",
        "SPA_CUTOVER_ENABLED": "0",
        "RATELIMIT_ENABLED": "0",
        **env_overrides,
    }
    # Wipe inherited values that would mask the test's env_overrides.
    for k in ("SECRET_KEY", "SUPERADMIN_PASSWORD", "ADMIN_PASSWORD"):
        if k not in env_overrides:
            env.pop(k, None)
    res = subprocess.run(
        [sys.executable, "-c", script],
        env=env, capture_output=True, text=True, timeout=60,
    )
    return res.returncode, res.stdout, res.stderr


def test_dev_boot_still_works_without_secret_key():
    """A normal dev/CI run (no APP_BASE_URL) must boot with the
    dev-fallback SECRET_KEY — every other test in the suite
    implicitly depends on this."""
    rc, out, err = _run("import app; print('OK')", env_overrides={})
    assert rc == 0, f"stderr:\n{err}\nstdout:\n{out}"
    assert "OK" in out


def test_prod_boot_refuses_with_missing_secret_key():
    """APP_BASE_URL=https://... with no SECRET_KEY set must raise
    RuntimeError at import time. Catches the catastrophic
    deploy-with-default-secret state where session cookies are
    forgeable from public Git history."""
    rc, out, err = _run(
        "import app; print('SHOULD-NOT-REACH')",
        env_overrides={"APP_BASE_URL": "https://dinerobook.com"},
    )
    assert rc != 0, "prod-boot must fail without SECRET_KEY"
    assert "SECRET_KEY" in err, err[:500]
    assert "Refusing to boot" in err, err[:500]
    assert "SHOULD-NOT-REACH" not in out


def test_prod_boot_succeeds_with_real_secret_key():
    """APP_BASE_URL=https://... WITH a real SECRET_KEY env var
    must boot successfully — the safety gate must not over-fire
    on the happy path."""
    rc, out, err = _run(
        "import app; print('OK', app.app.secret_key != 'dinerobook-dev-secret-change-in-prod')",
        env_overrides={
            "APP_BASE_URL": "https://dinerobook.com",
            "SECRET_KEY": "abc123-real-random-prod-value-do-not-use",
        },
    )
    assert rc == 0, f"stderr:\n{err}\nstdout:\n{out}"
    assert "OK True" in out


def test_prod_boot_logs_critical_for_missing_admin_password():
    """Missing SUPERADMIN_PASSWORD / ADMIN_PASSWORD in prod
    should NOT fail boot — but it must log a CRITICAL warning so
    Sentry / Render → Logs surface it."""
    rc, out, err = _run(
        "import app; print('OK')",
        env_overrides={
            "APP_BASE_URL": "https://dinerobook.com",
            "SECRET_KEY": "abc123-real-random-prod-value-do-not-use",
        },
    )
    assert rc == 0, f"stderr:\n{err}\nstdout:\n{out}"
    # Boot succeeded
    assert "OK" in out
    # CRITICAL warning landed (structlog emits to stderr by default).
    combined = (out + err).lower()
    assert "seed password fallback" in combined, (
        f"expected seed-password warning; out:\n{out}\nerr:\n{err}"
    )


def test_prod_boot_no_warning_with_admin_passwords_set():
    """When the seed-password env vars ARE set, the CRITICAL
    warning must NOT fire."""
    rc, out, err = _run(
        "import app; print('OK')",
        env_overrides={
            "APP_BASE_URL": "https://dinerobook.com",
            "SECRET_KEY": "abc123-real-random-prod-value-do-not-use",
            "SUPERADMIN_PASSWORD": "real-superadmin-password",
            "ADMIN_PASSWORD": "real-admin-password",
        },
    )
    assert rc == 0, f"stderr:\n{err}\nstdout:\n{out}"
    combined = (out + err).lower()
    assert "seed password fallback" not in combined, (
        f"unexpected seed-password warning when env vars are set; "
        f"out:\n{out}\nerr:\n{err}"
    )
