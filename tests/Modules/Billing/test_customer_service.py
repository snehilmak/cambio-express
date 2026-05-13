"""Unit tests for Billing.Services.customer (PR 56).

`ensure_stripe_customer` hits Stripe SDK + commits the session,
so we mock both: `stripe.Customer.retrieve/create` via monkeypatch
and use a MagicMock session.
"""
from unittest.mock import MagicMock

import pytest


def _store(*, customer_id="", email="ops@example.com", name="Demo Store",
           store_id=42):
    s = MagicMock()
    s.id = store_id
    s.stripe_customer_id = customer_id
    s.email = email
    s.name = name
    return s


# ── reuse cached customer ──────────────────────────────────


def test_returns_cached_customer_id_when_valid(monkeypatch):
    """Cached id resolves via retrieve → return as-is, no mint, no
    commit."""
    import stripe
    from api.Modules.Billing.Services import ensure_stripe_customer
    retrieve = MagicMock(return_value=MagicMock(id="cus_existing"))
    create = MagicMock()
    monkeypatch.setattr(stripe.Customer, "retrieve", retrieve)
    monkeypatch.setattr(stripe.Customer, "create", create)

    db = MagicMock()
    s = _store(customer_id="cus_existing")
    result = ensure_stripe_customer(db, s)

    assert result == "cus_existing"
    retrieve.assert_called_once_with("cus_existing")
    assert create.call_count == 0
    assert db.commit.call_count == 0


# ── self-heal on missing customer ──────────────────────────


def test_self_heals_on_no_such_customer(monkeypatch):
    """Test→live migration left a stale id; retrieve fails with
    'No such customer'; we clear + mint fresh + commit."""
    import stripe
    from api.Modules.Billing.Services import ensure_stripe_customer
    retrieve = MagicMock(
        side_effect=stripe.error.InvalidRequestError(
            "No such customer 'cus_old'", param="customer",
        ),
    )
    create = MagicMock(return_value=MagicMock(id="cus_new"))
    monkeypatch.setattr(stripe.Customer, "retrieve", retrieve)
    monkeypatch.setattr(stripe.Customer, "create", create)

    db = MagicMock()
    s = _store(customer_id="cus_old")
    result = ensure_stripe_customer(db, s)

    assert result == "cus_new"
    assert s.stripe_customer_id == "cus_new"
    create.assert_called_once()
    assert db.commit.call_count == 1


def test_self_heals_on_resource_missing(monkeypatch):
    """The other Stripe error string that triggers the self-heal."""
    import stripe
    from api.Modules.Billing.Services import ensure_stripe_customer
    retrieve = MagicMock(
        side_effect=stripe.error.InvalidRequestError(
            "resource_missing: customer", param="customer",
        ),
    )
    create = MagicMock(return_value=MagicMock(id="cus_fresh"))
    monkeypatch.setattr(stripe.Customer, "retrieve", retrieve)
    monkeypatch.setattr(stripe.Customer, "create", create)

    db = MagicMock()
    s = _store(customer_id="cus_old")
    result = ensure_stripe_customer(db, s)
    assert result == "cus_fresh"


# ── propagate other Stripe errors on retrieve ──────────────


def test_propagates_other_invalid_request_errors(monkeypatch):
    """A non-customer InvalidRequestError (e.g. permissions) must
    propagate — we don't paper over real failures by minting."""
    import stripe
    from api.Modules.Billing.Services import ensure_stripe_customer
    retrieve = MagicMock(
        side_effect=stripe.error.InvalidRequestError(
            "Permission denied", param="customer",
        ),
    )
    monkeypatch.setattr(stripe.Customer, "retrieve", retrieve)

    db = MagicMock()
    s = _store(customer_id="cus_old")
    with pytest.raises(stripe.error.InvalidRequestError):
        ensure_stripe_customer(db, s)
    # Cache untouched.
    assert s.stripe_customer_id == "cus_old"


# ── mint when no cache ─────────────────────────────────────


def test_mints_when_no_cached_id(monkeypatch):
    import stripe
    from api.Modules.Billing.Services import ensure_stripe_customer
    create = MagicMock(return_value=MagicMock(id="cus_minted"))
    retrieve = MagicMock()
    monkeypatch.setattr(stripe.Customer, "create", create)
    monkeypatch.setattr(stripe.Customer, "retrieve", retrieve)

    db = MagicMock()
    s = _store(customer_id="")
    result = ensure_stripe_customer(db, s)

    assert result == "cus_minted"
    assert s.stripe_customer_id == "cus_minted"
    # Retrieve never called (no cache to verify).
    assert retrieve.call_count == 0
    # Create called with email/name/metadata.
    create.assert_called_once()
    kw = create.call_args.kwargs
    assert kw["email"] == s.email
    assert kw["name"] == s.name
    assert kw["metadata"] == {"store_id": str(s.id)}
    assert db.commit.call_count == 1


def test_mints_with_none_email_when_store_email_blank(monkeypatch):
    """Stripe accepts None for email; an empty-string email could
    cause API-side validation issues, so coerce to None."""
    import stripe
    from api.Modules.Billing.Services import ensure_stripe_customer
    create = MagicMock(return_value=MagicMock(id="cus_anon"))
    monkeypatch.setattr(stripe.Customer, "create", create)
    monkeypatch.setattr(
        stripe.Customer, "retrieve", MagicMock(),
    )

    db = MagicMock()
    s = _store(customer_id="", email="")
    ensure_stripe_customer(db, s)
    assert create.call_args.kwargs["email"] is None


# ── propagate Stripe errors on create ──────────────────────


def test_propagates_create_failure(monkeypatch):
    """Stripe create failure must propagate so the FC connect
    endpoint can surface it."""
    import stripe
    from api.Modules.Billing.Services import ensure_stripe_customer
    create = MagicMock(
        side_effect=stripe.error.APIConnectionError("network down"),
    )
    monkeypatch.setattr(stripe.Customer, "create", create)
    monkeypatch.setattr(
        stripe.Customer, "retrieve", MagicMock(),
    )

    db = MagicMock()
    s = _store(customer_id="")
    with pytest.raises(stripe.error.APIConnectionError):
        ensure_stripe_customer(db, s)
    # Customer id cache stays empty.
    assert s.stripe_customer_id == ""


# ── legacy Flask wrapper ───────────────────────────────────


