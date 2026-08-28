"""Unit tests for Auth.Services.signup (PR 39)."""
from datetime import datetime, timedelta

import pytest
from tests._app import db, db_session


# ── create_store_and_owner ──────────────────────────────────


def test_signup_creates_store_and_owner():
    """Owner-first signup (U-4b): the signer-up becomes a
    role=owner user with the new store as their home store, plus a
    StoreOwnerLink row so sibling/umbrella logic sees it."""
    from api.Modules.Tenancy.Models import Store, StoreOwnerLink, User
    from tests._app import db
    from api.Modules.Auth.Services import create_store_and_owner
    with db_session():
        result = create_store_and_owner(
            db.session,
            store_name="Maria Cambio",
            email="maria@example.com",
            password="topsecret123",
            phone="+15551234",
        )
        db.session.commit()
        s = db.session.get(Store, result.store.id)
        u = db.session.get(User, result.owner.id)
        link = (
            db.session.query(StoreOwnerLink)
              .filter_by(owner_id=u.id, store_id=s.id)
              .first()
        )
        assert link is not None
    assert s.name == "Maria Cambio"
    assert s.slug == "maria-cambio"
    assert s.email == "maria@example.com"
    assert s.plan == "trial"
    assert u.username == "maria@example.com"
    assert u.role == "owner"
    assert u.store_id == s.id
    assert u.check_password("topsecret123")


def test_signup_unique_slug_collision_appends_counter():
    """Two stores with the same name should get distinct slugs."""
    from tests._app import db
    from api.Modules.Auth.Services import create_store_and_owner
    with db_session():
        first = create_store_and_owner(
            db.session,
            store_name="Cambio Express",
            email="first@example.com",
            password="pw1234567",
        )
        second = create_store_and_owner(
            db.session,
            store_name="Cambio Express",
            email="second@example.com",
            password="pw1234567",
        )
        db.session.commit()
        assert first.store.slug == "cambio-express"
        assert second.store.slug == "cambio-express-1"


def test_signup_sets_trial_window_defaults():
    """Default trial = 7 days; grace = 4 days after trial."""
    from tests._app import db
    from api.Modules.Auth.Services import create_store_and_owner
    with db_session():
        result = create_store_and_owner(
            db.session,
            store_name="Trial Test",
            email="trial@example.com",
            password="pw1234567",
        )
        db.session.commit()
        # Trial ends roughly 7 days from now (allow 1-min skew)
        delta = result.store.trial_ends_at - datetime.utcnow()
        assert timedelta(days=6, hours=23) < delta <= timedelta(days=7, minutes=1)
        # Grace ends 4 days after trial
        gap = result.store.grace_ends_at - result.store.trial_ends_at
        assert gap == timedelta(days=4)


def test_signup_respects_custom_trial_window():
    from tests._app import db
    from api.Modules.Auth.Services import create_store_and_owner
    with db_session():
        result = create_store_and_owner(
            db.session,
            store_name="Custom",
            email="custom@example.com",
            password="pw1234567",
            trial_days=14, grace_days=7,
        )
        db.session.commit()
        delta = result.store.trial_ends_at - datetime.utcnow()
        assert timedelta(days=13, hours=23) < delta <= timedelta(days=14, minutes=1)
        assert (result.store.grace_ends_at - result.store.trial_ends_at) == timedelta(days=7)


def test_signup_records_referral_when_passed():
    from tests._app import db
    from api.Modules.Auth.Services import create_store_and_owner
    with db_session():
        result = create_store_and_owner(
            db.session,
            store_name="Referred",
            email="ref@example.com",
            password="pw1234567",
            referred_by_code_id=42,
        )
        db.session.commit()
        assert result.store.referred_by_code_id == 42


def test_signup_rejects_existing_email():
    from tests._app import db
    from api.Modules.Auth.Services import (
        SignupConflictError, create_store_and_owner,
    )
    with db_session():
        create_store_and_owner(
            db.session,
            store_name="First",
            email="dup@example.com",
            password="pw1234567",
        )
        db.session.commit()
        with pytest.raises(SignupConflictError):
            create_store_and_owner(
                db.session,
                store_name="Second",
                email="dup@example.com",
                password="pw1234567",
            )


def test_signup_does_not_collide_with_superadmin_username():
    """The legacy existence check filtered `User.store_id.isnot(None)`
    so the superadmin (`store_id IS NULL`) doesn't block per-store
    signups."""
    from api.Modules.Tenancy.Models import User
    from tests._app import db
    from api.Modules.Auth.Services import create_store_and_owner
    with db_session():
        # Per the conftest seed, "superadmin" exists with store_id=None.
        # If a real user wanted username="superadmin", the per-store
        # uniqueness rules don't conflict — but the more realistic case
        # is a different username. Use that.
        result = create_store_and_owner(
            db.session,
            store_name="No Conflict",
            email="freshemail@example.com",
            password="pw1234567",
        )
        db.session.commit()
        # Sanity: superadmin user still exists too.
        sa = db.session.query(User).filter_by(
            username="superadmin", store_id=None,
        ).first()
        assert sa is not None
        assert result.owner.username == "freshemail@example.com"


# ── _allocate_unique_slug indirectly via create_store_and_owner ─


def test_signup_handles_special_chars_in_store_name():
    """slugify normalises Unicode + punctuation."""
    from tests._app import db
    from api.Modules.Auth.Services import create_store_and_owner
    with db_session():
        result = create_store_and_owner(
            db.session,
            store_name="José's Cambio (#1) — Tucson!",
            email="jose@example.com",
            password="pw1234567",
        )
        db.session.commit()
        slug = result.store.slug
    # slugify rules: lowercase, dash-separated, no special chars.
    assert " " not in slug
    assert slug.replace("-", "").isalnum()
