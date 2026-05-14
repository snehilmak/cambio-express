"""Rate limiter regression tests.

Validates the slowapi wiring in api/main.py + api/Core/RateLimit.
The conftest globally disables rate limiting via
`RATELIMIT_ENABLED=0` so every other test in the suite doesn't get
429'd; we exercise the 429 path in a subprocess with the env var
set fresh.

Tuning notes — if you bump the limits on the auth controller, update
the expected counts here too.
"""
from __future__ import annotations

import os
import subprocess
import sys


def test_slowapi_limiter_disabled_in_test_env():
    """The conftest forces RATELIMIT_ENABLED=0. The slowapi limiter
    must pick that up at import time. Regression guard for the
    `os.environ["RATELIMIT_ENABLED"] = "0"` line in conftest.py
    and the explicit `limiter.enabled = _enabled` override in
    api/Core/RateLimit.py (slowapi otherwise stores the env-var
    string instead of a bool)."""
    from api.Core.RateLimit import limiter as slow_limiter

    assert slow_limiter.enabled is False


# ── Subprocess-based assertions ───────────────────────────────
#
# slowapi decides whether to enforce limits at import time. To
# exercise the 429 path we spawn a fresh subprocess with
# RATELIMIT_ENABLED=1 set in the env before `import app` runs.

def _run_in_subprocess(script: str) -> tuple[int, str, str]:
    """Run `script` in a fresh Python process with the limiter on."""
    env = {
        **os.environ,
        "RATELIMIT_ENABLED": "1",
        "DATABASE_URL": "sqlite:///:memory:",
        "SECRET_KEY": "test-secret-key-for-ci",
        "STRIPE_SECRET_KEY": "sk_test_fake_key",
        "STRIPE_BASIC_PRICE_ID": "price_basic_test",
        "STRIPE_PRO_PRICE_ID": "price_pro_test",
        "STRIPE_WEBHOOK_SECRET": "whsec_test_secret",
        "SPA_CUTOVER_ENABLED": "0",
    }
    res = subprocess.run(
        [sys.executable, "-c", script],
        env=env, capture_output=True, text=True, timeout=60,
    )
    return res.returncode, res.stdout, res.stderr


def test_fastapi_login_429_with_limiter_enabled_at_boot():
    """slowapi: 429 within a small burst when the limiter is
    enabled at boot. The subprocess hits the production
    ``asgi_app`` directly via Starlette's ``TestClient`` — same
    transport tests use everywhere else."""
    script = (
        "from starlette.testclient import TestClient\n"
        "from asgi import asgi_app\n"
        "with TestClient(asgi_app) as c:\n"
        "    statuses = []\n"
        "    for _ in range(15):\n"
        "        r = c.post('/api/v2/auth/login',\n"
        "            json={'username':'nope','password':'wrong','store_id':0})\n"
        "        statuses.append(r.status_code)\n"
        "        if r.status_code == 429:\n"
        "            break\n"
        "assert 429 in statuses, f'never saw 429: {statuses}'\n"
        "print('OK')\n"
    )
    rc, out, err = _run_in_subprocess(script)
    assert rc == 0, f"stderr:\n{err}\nstdout:\n{out}"
    assert "OK" in out
