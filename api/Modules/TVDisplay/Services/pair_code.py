"""TV pair-code helpers.

The Fire TV / Google TV companion app gets a 6-char pair code +
opaque device token on launch (POST /api/tv-pair/init); the
operator types the code on /tv-display to bind it to their store.

Code alphabet excludes ambiguous chars (O / 0 / I / 1 / L / B / 8).
"""
from __future__ import annotations

import secrets
from datetime import timedelta

from sqlalchemy.orm import Session

from api.Modules.TVDisplay.Models import TVPairing, TVPendingPair


PAIR_CODE_ALPHABET = "ACDEFGHJKMNPQRTUVWXYZ234579"
PAIR_CODE_LIFETIME = timedelta(minutes=10)


def generate_pair_code() -> str:
    """6-char code. Brute-force resistance is the 10-min expiry +
    addon gate, not the code length (27**6 ~ 387M)."""
    return "".join(secrets.choice(PAIR_CODE_ALPHABET) for _ in range(6))


def generate_device_token(db: Session) -> str:
    """32-byte URL-safe random. Loops 8x on collision against
    TVPairing or TVPendingPair before raising."""
    for _ in range(8):
        t = secrets.token_urlsafe(24)
        if (not db.query(TVPairing).filter_by(device_token=t).first()
                and not db.query(TVPendingPair).filter_by(device_token=t).first()):
            return t
    raise RuntimeError("Could not mint a unique device_token")
