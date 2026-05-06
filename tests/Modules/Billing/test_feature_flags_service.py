"""Unit tests for Billing.Services.feature_flags (PR 49).

The Service is a pure read over (StoreFeatureOverride, FeatureFlag).
Per CLAUDE.md invariant #6, undeclared flags MUST fail open (return
True). The legacy Flask wrapper at `app.store_feature_enabled` is
also smoke-tested so we know the delegation hop didn't drop a case.
"""
from unittest.mock import MagicMock


def _store(store_id=1):
    s = MagicMock()
    s.id = store_id
    return s


def _db_session(*, override=None, flag=None):
    """Stub a SQLAlchemy session whose .query(...).filter_by(...).first()
    returns whatever the test wants. Two filter_by chains (one per
    Model) collapse onto the same MagicMock, but the Service issues
    them sequentially — we use side_effect to hand back the right
    value in order."""
    db = MagicMock()
    chain = MagicMock()
    db.query.return_value = chain
    chain.filter_by.return_value = chain
    # The Service calls .first() at most twice: once for the override
    # lookup (when store is not None) and once for the global flag.
    chain.first.side_effect = [override, flag]
    return db


# ── store_feature_enabled ──────────────────────────────────


def test_per_store_override_wins_when_enabled():
    """Override row trumps the global default."""
    from api.Modules.Billing.Services import store_feature_enabled
    override = MagicMock()
    override.enabled = True
    flag = MagicMock()
    flag.enabled_by_default = False
    db = _db_session(override=override, flag=flag)
    assert store_feature_enabled(db, _store(), "tv_display") is True


def test_per_store_override_wins_when_disabled():
    """Same direction the other way: an override that disables a
    globally-on flag must short-circuit the global lookup."""
    from api.Modules.Billing.Services import store_feature_enabled
    override = MagicMock()
    override.enabled = False
    flag = MagicMock()
    flag.enabled_by_default = True
    db = _db_session(override=override, flag=flag)
    assert store_feature_enabled(db, _store(), "bank_sync") is False


def test_falls_back_to_global_default_when_no_override():
    from api.Modules.Billing.Services import store_feature_enabled
    flag = MagicMock()
    flag.enabled_by_default = True
    db = _db_session(override=None, flag=flag)
    assert store_feature_enabled(db, _store(), "bank_sync") is True


def test_falls_back_to_disabled_global_default():
    from api.Modules.Billing.Services import store_feature_enabled
    flag = MagicMock()
    flag.enabled_by_default = False
    db = _db_session(override=None, flag=flag)
    assert store_feature_enabled(db, _store(), "bank_sync") is False


def test_undeclared_flag_fails_open_returns_true():
    """CLAUDE.md invariant #6: a flag with no global row + no
    override returns True. New gated routes rely on this for
    forward-compat with flags they reference before the platform
    seed catches up."""
    from api.Modules.Billing.Services import store_feature_enabled
    db = _db_session(override=None, flag=None)
    assert store_feature_enabled(db, _store(), "brand_new_flag") is True


def test_none_store_skips_override_lookup():
    """Logged-out / superadmin contexts pass None; we should not
    hit the override table at all (no store_id to filter on)."""
    from api.Modules.Billing.Services import store_feature_enabled
    flag = MagicMock()
    flag.enabled_by_default = True
    db = MagicMock()
    chain = MagicMock()
    db.query.return_value = chain
    chain.filter_by.return_value = chain
    chain.first.return_value = flag
    assert store_feature_enabled(db, None, "bank_sync") is True
    # Only the FeatureFlag query is issued — no override probe.
    assert db.query.call_count == 1


def test_none_store_undeclared_still_fails_open():
    from api.Modules.Billing.Services import store_feature_enabled
    db = MagicMock()
    chain = MagicMock()
    db.query.return_value = chain
    chain.filter_by.return_value = chain
    chain.first.return_value = None
    assert store_feature_enabled(db, None, "anything") is True


# ── store_has_addon ────────────────────────────────────────


def test_store_has_addon_present():
    from api.Modules.Billing.Services import store_has_addon
    s = MagicMock()
    s.addons = "tv_display,bank_sync"
    assert store_has_addon(s, "tv_display") is True
    assert store_has_addon(s, "bank_sync") is True


def test_store_has_addon_absent():
    from api.Modules.Billing.Services import store_has_addon
    s = MagicMock()
    s.addons = "tv_display"
    assert store_has_addon(s, "bank_sync") is False


def test_store_has_addon_none_store():
    from api.Modules.Billing.Services import store_has_addon
    assert store_has_addon(None, "tv_display") is False


def test_store_has_addon_blank():
    from api.Modules.Billing.Services import store_has_addon
    s = MagicMock()
    s.addons = ""
    assert store_has_addon(s, "tv_display") is False


# ── legacy Flask wrapper smoke ─────────────────────────────


def test_legacy_app_helper_delegates():
    """The Flask wrapper at app.store_feature_enabled now hands the
    active session to the Service. Prove the delegation works
    end-to-end against the real ORM models."""
    from app import app as flask_app
    from app import store_feature_enabled as legacy_store_feature_enabled
    with flask_app.app_context():
        # Undeclared flag → fail-open True (matches Service contract)
        assert legacy_store_feature_enabled(None, "totally_made_up") is True


def test_legacy_app_has_addon_delegates():
    from app import store_has_addon as legacy_store_has_addon
    s = MagicMock()
    s.addons = "tv_display"
    assert legacy_store_has_addon(s, "tv_display") is True
    assert legacy_store_has_addon(None, "tv_display") is False
