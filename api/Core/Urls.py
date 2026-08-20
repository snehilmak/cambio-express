"""Canonical application base URL.

One place for the ``APP_BASE_URL``-with-production-fallback rule
that email/link builders across the codebase all need. The
consistency sweep found 8 independent re-implementations of the
same two lines — this helper replaces them so the fallback host
can never drift per-module.
"""
import os


def get_base_url() -> str:
    """The app's public base URL, no trailing slash.

    ``APP_BASE_URL`` env when set (dev/staging), else the canonical
    production domain."""
    return (
        os.environ.get("APP_BASE_URL") or "https://dinerobook.com"
    ).rstrip("/")
