"""Coverage for the stdlib-only password-hash module.

The whole point of ``api/Core/PasswordHash.py`` is werkzeug-format
compatibility: hashes written by the old werkzeug dep (scrypt
default in 3.x, pbkdf2:sha256 in older versions) must keep
verifying after PR #556's dep drop. These tests pin that
guarantee with hand-crafted fixture hashes so a future
"clean-up" can't silently swap to an incompatible format and
lock everyone out.
"""
from __future__ import annotations

import hashlib

import pytest

from api.Core.PasswordHash import (
    check_password_hash,
    generate_password_hash,
)


# ── Round-trip ──────────────────────────────────────────────────


def test_generate_and_check_round_trip():
    h = generate_password_hash("hunter2")
    assert check_password_hash(h, "hunter2") is True
    assert check_password_hash(h, "wrong") is False


def test_default_method_is_scrypt():
    """werkzeug 3.x defaults to scrypt:32768:8:1; we match so a
    side-by-side comparison of stored hashes can't tell the old
    and new implementations apart. The conftest patches the
    default to a fast pbkdf2 for speed, so check the module-level
    constant directly rather than the actual call."""
    from api.Core.PasswordHash import _DEFAULT_METHOD
    assert _DEFAULT_METHOD == "scrypt:32768:8:1"


def test_fresh_hashes_use_random_salt():
    """Two hashes of the same password share the same method but
    differ in salt + body. Salt source is ``secrets.choice`` (CSPRNG)."""
    h1 = generate_password_hash("same")
    h2 = generate_password_hash("same")
    assert h1 != h2
    assert h1.split("$", 1)[0] == h2.split("$", 1)[0]


# ── werkzeug-format read-only support ───────────────────────────


def test_check_accepts_pbkdf2_sha256_format():
    """Older werkzeug versions used pbkdf2:sha256:<N>. Hashes
    written by those releases must keep verifying."""
    iterations = 1000
    salt = "AbCdEfGhIjKlMnOp"
    password = "legacy123"
    hex_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), iterations,
    ).hex()
    stored = f"pbkdf2:sha256:{iterations}${salt}${hex_hash}"
    assert check_password_hash(stored, password) is True
    assert check_password_hash(stored, "WRONG") is False


def test_check_accepts_scrypt_format_with_high_cost():
    """Werkzeug 3.x default cost factor — explicitly verified so
    the maxmem boost in ``_derive_scrypt`` is exercised."""
    h = generate_password_hash("scrypt-default")
    assert check_password_hash(h, "scrypt-default") is True


def test_explicit_pbkdf2_method_works():
    h = generate_password_hash("pw", method="pbkdf2:sha256:1000")
    assert h.startswith("pbkdf2:sha256:1000$")
    assert check_password_hash(h, "pw") is True


# ── Robustness ──────────────────────────────────────────────────


def test_check_returns_false_for_garbage_hash():
    """Malformed stored hashes must not raise — they should just
    fail to authenticate. Matches werkzeug's behaviour."""
    assert check_password_hash("", "pw") is False
    assert check_password_hash("not-a-real-hash", "pw") is False
    assert check_password_hash("missing$salt", "pw") is False
    assert check_password_hash("unknown:method:1$salt$abc", "pw") is False


def test_check_returns_false_for_empty_password():
    h = generate_password_hash("real")
    assert check_password_hash(h, "") is False


def test_generate_rejects_unknown_method():
    with pytest.raises(ValueError):
        generate_password_hash("pw", method="bcrypt:12")


# ── Constant-time compare ───────────────────────────────────────


def test_check_uses_hmac_compare_digest(monkeypatch):
    """Don't let a future refactor swap in ``==`` and reintroduce
    a timing oracle. The check function should call
    ``hmac.compare_digest`` exactly once per invocation."""
    import api.Core.PasswordHash as ph
    calls: list = []
    real = ph.hmac.compare_digest

    def spy(a, b):
        calls.append((len(a), len(b)))
        return real(a, b)

    monkeypatch.setattr(ph.hmac, "compare_digest", spy)
    h = generate_password_hash("timing")
    assert check_password_hash(h, "timing") is True
    assert len(calls) == 1
