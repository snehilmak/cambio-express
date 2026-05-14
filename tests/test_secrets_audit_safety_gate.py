"""Seed-password safety warning regression tests.

Production boots are expected to set ``SUPERADMIN_PASSWORD`` and
``ADMIN_PASSWORD`` so the public defaults in the repo aren't the
real credentials. ``api.Core.Boot.warn_default_seed_passwords``
fires a CRITICAL log line when either is missing while
``APP_BASE_URL`` points at HTTPS — operators see it via Sentry /
Render logs and can rotate.

Each test runs in a subprocess so we get a clean env per case.
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
        "RATELIMIT_ENABLED": "0",
        "DINEROBOOK_SKIP_INIT_DB": "1",
        **env_overrides,
    }
    # Wipe inherited values that would mask the test's env_overrides.
    for k in ("SUPERADMIN_PASSWORD", "ADMIN_PASSWORD"):
        if k not in env_overrides:
            env.pop(k, None)
    res = subprocess.run(
        [sys.executable, "-c", script],
        env=env, capture_output=True, text=True, timeout=60,
    )
    return res.returncode, res.stdout, res.stderr


def test_dev_boot_does_not_warn_about_seed_passwords():
    """No APP_BASE_URL = not prod — the warning is silent."""
    rc, out, err = _run(
        "from api.Core.Boot import warn_default_seed_passwords;"
        " warn_default_seed_passwords(); print('OK')",
        env_overrides={},
    )
    assert rc == 0, f"stderr:\n{err}\nstdout:\n{out}"
    assert "OK" in out
    combined = (out + err).lower()
    assert "seed password fallback" not in combined


def test_prod_boot_warns_for_missing_admin_password():
    """Missing SUPERADMIN_PASSWORD / ADMIN_PASSWORD with
    APP_BASE_URL=https://... must log a CRITICAL warning."""
    rc, out, err = _run(
        "from api.Core.Boot import warn_default_seed_passwords;"
        " warn_default_seed_passwords(); print('OK')",
        env_overrides={"APP_BASE_URL": "https://dinerobook.com"},
    )
    assert rc == 0, f"stderr:\n{err}\nstdout:\n{out}"
    assert "OK" in out
    combined = (out + err).lower()
    assert "seed password fallback" in combined, (
        f"expected seed-password warning; out:\n{out}\nerr:\n{err}"
    )


def test_prod_boot_no_warning_with_admin_passwords_set():
    """When the seed-password env vars ARE set, the CRITICAL
    warning must NOT fire."""
    rc, out, err = _run(
        "from api.Core.Boot import warn_default_seed_passwords;"
        " warn_default_seed_passwords(); print('OK')",
        env_overrides={
            "APP_BASE_URL": "https://dinerobook.com",
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
