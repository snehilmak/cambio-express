"""Unit tests for ``store_gate_status`` (PR C).

The gate helper decides whether a store's users get locked out of the
app to a re-subscribe / suspended screen, and why. Pure function —
these tests build transient ``Store`` instances (no DB) and assert the
precedence rules:

  frozen  >  subscription-lapsed  >  usable
"""
from datetime import timedelta

from api.Core.Clock import utc_now
from api.Modules.Billing.Services import store_gate_status
from api.Modules.Billing.Services.store_state import (
    GATE_REASON_FROZEN, GATE_REASON_SUBSCRIPTION,
)
from api.Modules.Tenancy.Models import Store


def _store(**kw) -> Store:
    """Transient Store with explicit attrs (column defaults don't apply
    until flush, so every field the helper reads is set here)."""
    s = Store()
    s.plan = kw.get("plan", "trial")
    s.trial_ends_at = kw.get("trial_ends_at")
    s.grace_ends_at = kw.get("grace_ends_at")
    s.frozen_at = kw.get("frozen_at")
    return s


def test_none_store_is_not_gated():
    # Superadmin has no store scope → never gated.
    assert store_gate_status(None) == {"gated": False, "reason": ""}


def test_active_trial_not_gated():
    now = utc_now()
    s = _store(plan="trial", trial_ends_at=now + timedelta(days=10),
               grace_ends_at=now + timedelta(days=14))
    assert store_gate_status(s)["gated"] is False


def test_paid_plan_not_gated():
    assert store_gate_status(_store(plan="pro"))["gated"] is False
    assert store_gate_status(_store(plan="basic"))["gated"] is False


def test_grace_is_not_gated():
    # Grace = trial_ends_at passed but grace_ends_at hasn't. The store
    # still works (reduced) — we deliberately do NOT gate during grace.
    now = utc_now()
    s = _store(plan="trial", trial_ends_at=now - timedelta(days=1),
               grace_ends_at=now + timedelta(days=3))
    assert store_gate_status(s)["gated"] is False


def test_inactive_plan_is_subscription_gated():
    s = _store(plan="inactive")
    assert store_gate_status(s) == {
        "gated": True, "reason": GATE_REASON_SUBSCRIPTION,
    }


def test_expired_grace_is_subscription_gated():
    now = utc_now()
    s = _store(plan="trial", trial_ends_at=now - timedelta(days=10),
               grace_ends_at=now - timedelta(days=3))
    assert store_gate_status(s) == {
        "gated": True, "reason": GATE_REASON_SUBSCRIPTION,
    }


def test_frozen_is_gated():
    s = _store(plan="basic", frozen_at=utc_now())
    assert store_gate_status(s) == {
        "gated": True, "reason": GATE_REASON_FROZEN,
    }


def test_frozen_takes_precedence_over_subscription():
    # A frozen, also-lapsed store reports "frozen" — re-subscribing
    # wouldn't lift a superadmin suspension, so the more specific state
    # wins and the SPA shows "contact support", not "re-subscribe".
    s = _store(plan="inactive", frozen_at=utc_now())
    assert store_gate_status(s)["reason"] == GATE_REASON_FROZEN
