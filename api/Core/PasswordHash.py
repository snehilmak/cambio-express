"""Password hashing — stdlib-only, werkzeug-format-compatible.

The legacy hashes stored in ``User.password_hash`` were written by
``werkzeug.security.generate_password_hash`` (scrypt by default
on werkzeug 3.x, pbkdf2:sha256 in older versions). We read and
write the exact same string format so PR #556's werkzeug-dep
removal is invisible to existing DBs — no migration, no forced
password rotation.

Format
------
Werkzeug's hash strings look like::

    <method>$<salt>$<hex-hash>

Supported methods (compatible with werkzeug 0.x → 3.x):

* ``scrypt:N:r:p`` — N cost factor, r block size, p parallelism.
  Default for new hashes (matches werkzeug 3.x's default).
* ``pbkdf2:sha256:<iterations>`` — read-only support for hashes
  written by older werkzeug versions still in the wild.

New hashes always use scrypt with werkzeug 3.x's defaults so a
re-hash round-trip is bit-identical.

API
---
Drop-in replacement for ``werkzeug.security`` — same two function
names + signatures::

    generate_password_hash(password, method=..., salt_length=16) -> str
    check_password_hash(stored_hash, password) -> bool

Both ``method`` knobs (``"scrypt:32768:8:1"``, ``"pbkdf2:sha256:N"``)
that the test conftest patches in are accepted so the speed-up
hook keeps working without changes.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets


# ── Defaults ────────────────────────────────────────────────────
#
# Match werkzeug 3.x's defaults so re-hashes are byte-identical
# and a side-by-side comparison of stored hashes can't tell the
# old and new implementations apart.

_DEFAULT_METHOD = "scrypt:32768:8:1"
_DEFAULT_SALT_LENGTH = 16
_DEFAULT_DKLEN_BYTES = 64  # 64-byte derived key → 128 hex chars


# ── Salt ────────────────────────────────────────────────────────


def _random_salt(length: int) -> str:
    """Werkzeug uses alnum characters for salts; mirror that so the
    stored hash format is indistinguishable. ``secrets.choice`` is
    a cryptographic-quality source."""
    alphabet = (
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789"
    )
    return "".join(secrets.choice(alphabet) for _ in range(length))


# ── KDF dispatch ────────────────────────────────────────────────


def _derive_scrypt(password: str, salt: str, n: int, r: int, p: int,
                   dklen: int) -> str:
    # ``maxmem`` must be at least 128 * n * r * p bytes for OpenSSL
    # not to error out at default-cap. Add a small headroom slot to
    # cover overhead.
    maxmem = 128 * n * r * p + 8 * 1024 * 1024
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt.encode("utf-8"),
        n=n, r=r, p=p, dklen=dklen, maxmem=maxmem,
    ).hex()


def _derive_pbkdf2(password: str, salt: str, algo: str,
                   iterations: int, dklen: int | None) -> str:
    return hashlib.pbkdf2_hmac(
        algo,
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
        dklen=dklen,
    ).hex()


# ── Public API ──────────────────────────────────────────────────


def generate_password_hash(
    password: str,
    method: str = _DEFAULT_METHOD,
    salt_length: int = _DEFAULT_SALT_LENGTH,
) -> str:
    """Hash ``password`` and return the werkzeug-format string.

    Always writes a fresh hash with ``method`` (default scrypt) and
    a fresh random salt. The returned string is the canonical
    ``<method>$<salt>$<hex>`` form that ``check_password_hash``
    knows how to round-trip.
    """
    salt = _random_salt(salt_length)
    parts = method.split(":")
    kind = parts[0]
    if kind == "scrypt":
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
        hex_hash = _derive_scrypt(
            password, salt, n, r, p, _DEFAULT_DKLEN_BYTES,
        )
    elif kind == "pbkdf2":
        algo = parts[1]
        iterations = int(parts[2])
        hex_hash = _derive_pbkdf2(
            password, salt, algo, iterations, dklen=None,
        )
    else:
        raise ValueError(f"Unsupported hash method: {method!r}")
    return f"{method}${salt}${hex_hash}"


def check_password_hash(stored: str, password: str) -> bool:
    """Constant-time check of ``password`` against ``stored``.

    Parses the stored ``<method>$<salt>$<hex>`` envelope, replays
    the KDF with the same parameters, compares via
    ``hmac.compare_digest``. Returns ``False`` (never raises) on
    any parse / decode error — matches werkzeug's behaviour so
    malformed-hash rows can't crash login.
    """
    if not stored or not password:
        return False
    try:
        method, salt, hex_hash = stored.split("$")
    except ValueError:
        return False
    parts = method.split(":")
    try:
        kind = parts[0]
        if kind == "scrypt":
            n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
            candidate = _derive_scrypt(
                password, salt, n, r, p, len(hex_hash) // 2,
            )
        elif kind == "pbkdf2":
            algo = parts[1]
            iterations = int(parts[2])
            candidate = _derive_pbkdf2(
                password, salt, algo, iterations,
                dklen=len(hex_hash) // 2,
            )
        else:
            return False
    except (ValueError, IndexError):
        return False
    return hmac.compare_digest(candidate, hex_hash)


__all__ = ["generate_password_hash", "check_password_hash"]
