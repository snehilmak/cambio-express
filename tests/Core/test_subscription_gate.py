"""Server-side subscription enforcement (W-1).

The trial used to be enforced by the SPA CHOOSING to render a
re-subscribe screen — ``store_gate_status`` was called from one
endpoint, the shell payload, and nothing else. A store 30 days past
its trial could log in, read everything, and POST new rows.

These tests are that hole, closed, plus the ways closing it could go
wrong in the other direction: locking someone out of their own data,
or — worst of all — out of the checkout page they need to pay you.
"""
from datetime import timedelta

import pytest

from api.Core.Clock import utc_now
from api.Core.Subscription import write_block_reason
from api.Modules.Tenancy.Models import Store
from tests._app import db, db_session
from tests.conftest import login_admin


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _set_trial(store_id, *, days_past_trial_end, grace_days=4):
    """Move a store's trial window into the past by N days."""
    with db_session():
        s = db.session.get(Store, store_id)
        s.plan = "trial"
        s.trial_ends_at = utc_now() - timedelta(days=days_past_trial_end)
        s.grace_ends_at = s.trial_ends_at + timedelta(days=grace_days)
        db.session.commit()


def _active_trial(store_id, days_left=5):
    with db_session():
        s = db.session.get(Store, store_id)
        s.plan = "trial"
        s.trial_ends_at = utc_now() + timedelta(days=days_left)
        s.grace_ends_at = s.trial_ends_at + timedelta(days=4)
        db.session.commit()


def _write(client, token):
    """Any authenticated write. Roles is convenient — it is a plain
    POST with no money semantics to muddy the result."""
    return client.post(
        "/api/v2/admin/roles", headers=_headers(token),
        json={"name": f"probe-{utc_now().timestamp()}", "matrix": {}},
    )


# ── The hole, closed ────────────────────────────────────────


def test_writes_are_refused_once_the_trial_ends(client, test_store_id):
    """Day 8. This is the assertion that was false before W-1."""
    _set_trial(test_store_id, days_past_trial_end=1)
    token = login_admin(client, test_store_id)
    resp = _write(client, token)
    assert resp.status_code == 402, resp.text
    assert resp.json()["reason"] == "trial_ended"


def test_writes_are_refused_long_after_expiry(client, test_store_id):
    _set_trial(test_store_id, days_past_trial_end=30)
    token = login_admin(client, test_store_id)
    resp = _write(client, token)
    assert resp.status_code == 402
    assert resp.json()["reason"] == "subscription"


def test_a_frozen_store_cannot_write(client, test_store_id):
    with db_session():
        s = db.session.get(Store, test_store_id)
        s.plan = "pro"
        s.frozen_at = utc_now()
        db.session.commit()
    token = login_admin(client, test_store_id)
    resp = _write(client, token)
    assert resp.status_code == 402
    assert resp.json()["reason"] == "frozen"


# ── …without locking anyone out of what they own ────────────


def test_reads_still_work_after_the_trial_ends(client, test_store_id):
    """The read-only window. Someone whose trial lapsed overnight
    must still see the books they spent a week entering — locking
    them out earns a support ticket and a bad review."""
    _set_trial(test_store_id, days_past_trial_end=1)
    token = login_admin(client, test_store_id)
    h = _headers(token)
    for path in (
        "/api/v2/dashboard/summary",
        "/api/v2/admin/employees",
    ):
        assert client.get(path, headers=h).status_code == 200, path


def test_reads_still_work_long_after_expiry(client, test_store_id):
    """Their data is retained 180 days by design; refusing to show
    it back would contradict the product's own promise."""
    _set_trial(test_store_id, days_past_trial_end=30)
    token = login_admin(client, test_store_id)
    assert client.get(
        "/api/v2/dashboard/summary", headers=_headers(token),
    ).status_code == 200


def test_login_still_works_after_expiry(client, test_store_id):
    _set_trial(test_store_id, days_past_trial_end=30)
    assert login_admin(client, test_store_id)


def test_the_lapsed_operator_can_still_reach_checkout(
    client, test_store_id,
):
    """The one exemption that must never break: getting the gate
    wrong in the tight direction locks someone out of PAYING you."""
    _set_trial(test_store_id, days_past_trial_end=30)
    token = login_admin(client, test_store_id)
    resp = client.post(
        "/api/v2/billing/checkout", headers=_headers(token),
        json={"plan": "basic"},
    )
    # Whatever Stripe does in a test env, the subscription gate must
    # not be what stopped it.
    assert resp.status_code != 402, (
        "billing must stay writable for a lapsed store"
    )


def test_support_tickets_stay_open_to_a_lapsed_store(
    client, test_store_id,
):
    """Someone locked out needs to be able to say so."""
    _set_trial(test_store_id, days_past_trial_end=30)
    token = login_admin(client, test_store_id)
    resp = client.post(
        "/api/v2/tickets", headers=_headers(token),
        json={"subject": "Locked out", "body": "Please help"},
    )
    assert resp.status_code != 402


# ── An active trial is untouched ────────────────────────────


def test_an_active_trial_writes_normally(client, test_store_id):
    _active_trial(test_store_id, days_left=5)
    token = login_admin(client, test_store_id)
    assert _write(client, token).status_code == 201


def test_the_last_day_of_the_trial_still_writes(client, test_store_id):
    """Day 7 is still trial. The cut is at the END of the window,
    not the start of the last day."""
    with db_session():
        s = db.session.get(Store, test_store_id)
        s.plan = "trial"
        s.trial_ends_at = utc_now() + timedelta(hours=2)
        s.grace_ends_at = s.trial_ends_at + timedelta(days=4)
        db.session.commit()
    token = login_admin(client, test_store_id)
    assert _write(client, token).status_code == 201


def test_a_paid_store_writes_normally(client, test_store_id):
    with db_session():
        s = db.session.get(Store, test_store_id)
        s.plan = "pro"
        s.frozen_at = None
        db.session.commit()
    token = login_admin(client, test_store_id)
    assert _write(client, token).status_code == 201


# ── The pure predicate ──────────────────────────────────────


def test_no_store_scope_is_never_blocked():
    """Superadmin and an owner between stores are not on a store's
    subscription."""
    assert write_block_reason(None) is None


def test_predicate_matches_the_states(test_store_id):
    with db_session():
        s = db.session.get(Store, test_store_id)

        s.plan, s.frozen_at = "pro", None
        assert write_block_reason(s) is None

        s.plan = "trial"
        s.trial_ends_at = utc_now() + timedelta(days=3)
        s.grace_ends_at = s.trial_ends_at + timedelta(days=4)
        assert write_block_reason(s) is None, "expiring_soon still writes"

        s.trial_ends_at = utc_now() - timedelta(days=1)
        s.grace_ends_at = utc_now() + timedelta(days=3)
        assert write_block_reason(s)[0] == "trial_ended"

        s.grace_ends_at = utc_now() - timedelta(days=1)
        assert write_block_reason(s)[0] == "subscription"

        s.frozen_at = utc_now()
        assert write_block_reason(s)[0] == "frozen", (
            "a suspension outranks a lapsed plan"
        )
