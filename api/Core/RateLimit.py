"""Shared slowapi Limiter for FastAPI.

The Flask side uses ``app.limiter`` (created in ``app.py``); the
FastAPI side uses this module-level singleton so controllers can
import it without depending on the ``api.main.create_app()``
lifecycle. Storage backend + enable-flag match the Flask twin —
both read the same env vars (``RATELIMIT_STORAGE_URI``,
``RATELIMIT_ENABLED``), so a single Redis URL in prod gives the
two apps a shared bucket.

Tuning lives in the per-route decorators (auth controllers); this
module only constructs the limiter.
"""
from __future__ import annotations

import os

from slowapi import Limiter
from slowapi.util import get_remote_address


_storage = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
_enabled = os.environ.get("RATELIMIT_ENABLED", "1") not in (
    "0", "false", "False",
)


limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_storage,
    strategy="fixed-window",
    enabled=_enabled,
    headers_enabled=True,
)
# slowapi >=0.1.9 reads `RATELIMIT_ENABLED` from os.environ itself
# and stores the raw string, which is truthy (e.g. "0" is truthy in
# Python). Overwrite with an actual bool so the test suite's
# `enabled=False` actually disables the limiter.
limiter.enabled = _enabled
