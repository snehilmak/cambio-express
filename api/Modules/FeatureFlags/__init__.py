"""FeatureFlags module — superadmin-managed global feature switches.

Each flag has a slug-style `key`, a human label + description, and
an `enabled_by_default` baseline. The legacy
`store_feature_enabled(store, key)` helper resolves a flag to:

  per-store override → global default → fail-open True

so undeclared flags don't block the codebase. Per-store overrides
live in a separate StoreFeatureOverride table; this module
manages the global rows.
"""
