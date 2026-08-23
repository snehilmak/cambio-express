"""Feature-flag + add-on resolution.

Two related helpers, both pure reads:
  store_feature_enabled — per-store override → global default →
                          fail-open (undeclared flag = True).
  store_has_addon       — predicate over the comma-separated
                          Store.addons string.

Per CLAUDE.md invariant #6: undeclared flags fail open. Don't
change that without a coordinated plan — there are gated routes
that depend on it for forward-compat with new flag keys.
"""
from sqlalchemy.orm import Session

from api.Modules.Billing.Models import (
    FeatureFlag,
    Store,
    StoreFeatureOverride,
)
from api.Modules.Billing.Services.store_state import store_addon_keys


# ── Business-type module bundles (the pivot, HANDOFF.md §2) ────────
#
# ``module_*`` flags gate whole PRODUCT MODULES per business type —
# a convenience store shouldn't see the money-transfer ledger it
# never uses, while the original MSB profile keeps everything. The
# resolution order in ``store_feature_enabled`` slots the bundle
# BETWEEN the per-store override and the global default, so:
#   • superadmin can still flip any module per store (override wins),
#   • non-module flags behave exactly as before,
#   • an unknown business_type falls through to the old behavior
#     (fail-open — same spirit as CLAUDE.md invariant #6).
#
# NOTE: module flags are a product/UX boundary, not a security
# boundary — routes stay store-scoped regardless. When modules
# become billing-tiered, add backend enforcement at that point.
MODULE_FLAG_KEYS = (
    "module_money_services", "module_lottery", "module_day_close",
)

_BUSINESS_TYPE_MODULE_DEFAULTS: dict[str, dict[str, bool]] = {
    # module_money_services: money-transfer ledger + ACH batches +
    # sender directory. Check cashing / returned checks are NOT in
    # this bundle — plenty of c-stores cash checks, so those
    # surfaces stay available to every type.
    # module_lottery: games / packs / day-close counts. ON for the
    # retail types that sell scratch-offs; OFF for the pure
    # money-services profile (override available per store).
    # module_day_close: register/shift Z-report totals + department
    # sales (P1-7). ON for the retail types; OFF for msb_hybrid,
    # whose day-close is the daily book itself.
    "cstore": {
        "module_money_services": False,
        "module_lottery": True,
        "module_day_close": True,
    },
    "gas_station": {
        "module_money_services": False,
        "module_lottery": True,
        "module_day_close": True,
    },
    "grocery": {
        "module_money_services": False,
        "module_lottery": True,
        "module_day_close": True,
    },
    "msb_hybrid": {
        "module_money_services": True,
        "module_lottery": False,
        "module_day_close": False,
    },
}


def module_bundle_default(
    business_type: str | None, flag_key: str,
) -> bool | None:
    """The business-type bundle's answer for a module flag, or None
    when the bundle has no opinion (non-module flag, or unknown
    type)."""
    if business_type is None:
        return None
    return _BUSINESS_TYPE_MODULE_DEFAULTS.get(business_type, {}).get(flag_key)


def store_feature_enabled(
    db: Session, store: Store | None, flag_key: str,
) -> bool:
    """Resolve a feature flag for a store.

    Lookup priority:
      1. per-store override (StoreFeatureOverride row) — if present,
         that value wins regardless of the global default.
      2. business-type module bundle (``module_*`` flags only) —
         which modules this kind of business gets by default.
      3. global default (FeatureFlag.enabled_by_default).
      4. fail-open: undeclared flag → True (CLAUDE.md invariant #6).

    Reads the same DB the legacy helper does; the only difference is
    the explicit `db` parameter so the Service can be exercised from
    any caller (FastAPI, CLI, tests).
    """
    if store is not None:
        override = (
            db.query(StoreFeatureOverride)
              .filter_by(store_id=store.id, flag_key=flag_key)
              .first()
        )
        if override is not None:
            return bool(override.enabled)
        bundled = module_bundle_default(
            getattr(store, "business_type", None), flag_key,
        )
        if bundled is not None:
            return bundled
    flag = db.query(FeatureFlag).filter_by(key=flag_key).first()
    if flag is None:
        # Unknown flag = allow by default (fail-open for undeclared
        # features). See CLAUDE.md invariant #6.
        return True
    return bool(flag.enabled_by_default)


def enabled_module_flags(db: Session, store: Store | None) -> list[str]:
    """The module flags currently ON for this store — the SPA reads
    this off /auth/session-status to decide which nav sections and
    routes to show. ``store=None`` (superadmin / owner without store
    scope) enables everything: platform operators see all modules."""
    if store is None:
        return list(MODULE_FLAG_KEYS)
    return [
        key for key in MODULE_FLAG_KEYS
        if store_feature_enabled(db, store, key)
    ]


def store_has_addon(store: Store | None, addon_key: str) -> bool:
    """Single predicate every add-on-gated route uses.

    Reads the comma-separated `Store.addons` field; doesn't touch
    the DB. Future `customer.subscription.updated` syncs that flip
    add-ons via the same field automatically propagate to every
    gated surface.
    """
    return addon_key in store_addon_keys(store)
