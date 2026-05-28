"""Resend webhook helpers.

Verifies Svix-style signatures over the raw body, and applies the
side-effects we care about for sending hygiene (hard-bounce + spam
complaint → suppress + flip notify_* toggles off).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import datetime

from sqlalchemy.orm import Session

from api.Modules.Tenancy.Models import User
from api.Core.Clock import utc_now


_REPLAY_WINDOW_SECONDS = 5 * 60


def verify_resend_signature(secret, svix_id, svix_timestamp, svix_signature,
                            raw_body):
    """Verify a Svix-style signature header. Returns True on match.

    Header may carry multiple space-separated 'v1,{base64}' entries
    after a key rotation; accept any. Secret looks like 'whsec_...'.
    """
    if not (secret and svix_id and svix_timestamp and svix_signature):
        return False
    try:
        ts_int = int(svix_timestamp)
        now_int = int(utc_now().timestamp())
        if abs(now_int - ts_int) > _REPLAY_WINDOW_SECONDS:
            return False
    except ValueError:
        return False
    if not secret.startswith("whsec_"):
        return False
    try:
        secret_bytes = base64.b64decode(secret[len("whsec_"):])
    except Exception:
        return False
    signed_payload = f"{svix_id}.{svix_timestamp}.".encode() + raw_body
    expected = hmac.new(secret_bytes, signed_payload, hashlib.sha256).digest()
    expected_b64 = base64.b64encode(expected).decode()
    for sig in svix_signature.split():
        if "," not in sig:
            continue
        version, value = sig.split(",", 1)
        if version != "v1":
            continue
        if hmac.compare_digest(value, expected_b64):
            return True
    return False


def apply_resend_side_effects(db: Session, event_type, to_addr, bounce_type):
    """Hard-bounce → stamp email_bounced_at. Complaint → same, plus
    flip every notify_* toggle off."""
    if not to_addr:
        return
    from sqlalchemy import func
    users = (db.query(User)
             .filter(func.lower(User.email) == to_addr.lower())
             .all())
    if not users:
        return
    now = utc_now()
    for u in users:
        if event_type == "email.bounced" and bounce_type == "hard":
            u.email_bounced_at = now
        elif event_type == "email.complained":
            u.email_bounced_at = now
            u.notify_trial_reminders = False
            u.notify_announcement_email = False
            u.notify_locked_day_digest = False
