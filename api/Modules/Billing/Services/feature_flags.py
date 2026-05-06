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


def store_feature_enabled(
    db: Session, store: Store | None, flag_key: str,
) -> bool:
    """Resolve a feature flag for a store.

    Lookup priority:
      1. per-store override (StoreFeatureOverride row) — if present,
         that value wins regardless of the global default.
      2. global default (FeatureFlag.enabled_by_default).
      3. fail-open: undeclared flag → True (CLAUDE.md invariant #6).

    Reads the same DB the legacy helper does; the only difference is
    the explicit `db` parameter so the Service can be exercised from
    any caller (Flask, FastAPI, CLI, tests).
    """
    if store is not None:
        override = (
            db.query(StoreFeatureOverride)
              .filter_by(store_id=store.id, flag_key=flag_key)
              .first()
        )
        if override is not None:
            return bool(override.enabled)
    flag = db.query(FeatureFlag).filter_by(key=flag_key).first()
    if flag is None:
        # Unknown flag = allow by default (fail-open for undeclared
        # features). See CLAUDE.md invariant #6.
        return True
    return bool(flag.enabled_by_default)


def store_has_addon(store: Store | None, addon_key: str) -> bool:
    """Single predicate every add-on-gated route uses.

    Reads the comma-separated `Store.addons` field; doesn't touch
    the DB. Future `customer.subscription.updated` syncs that flip
    add-ons via the same field automatically propagate to every
    gated surface.
    """
    return addon_key in store_addon_keys(store)
