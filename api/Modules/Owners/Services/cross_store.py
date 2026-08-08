"""Owner-side cross-store defaults push.

Lets an owner update common store settings (federal tax rate,
timezone, weekly business hours, enforce-hours toggle) across
many of their linked stores in one POST. Each store update goes
through the same ``Admin.Services.store_info.update_store_info``
guard the per-store settings page uses, so the same validation
applies — bogus timezones, malformed hours, etc. surface as
per-store ``rejected`` rows rather than 4xx'ing the whole call.

Pattern mirrors ``bulk_users.bulk_add_user_to_stores`` so the
SPA result table renders identically.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from api.Modules.Admin.Repositories import find_store
from api.Modules.Admin.Services.store_info import update_store_info
from api.Modules.Owners.Repositories import get_store_names_map, owner_store_ids
from typing import Any


# Fields the owner can push cross-store. Subset of
# ``Admin.Services.store_info.EDITABLE_STORE_FIELDS`` —
# receipt customization is excluded because that surface is
# currently hidden from the SPA (see PR #602), and ``name`` /
# ``email`` are intentionally per-store identity fields.
CROSS_STORE_FIELDS: tuple[str, ...] = (
    "federal_tax_rate",
    "timezone",
    "store_hours",
    "enforce_business_hours",
    "timeclock_require_passkey",
    "phone",
    "address",
)


def apply_cross_store_defaults(
    db: Session,
    *,
    owner_id: int,
    store_ids: list[int],
    defaults: dict[str, Any],
) -> list[dict[str, Any]]:
    """Push ``defaults`` to every requested store that's in the
    owner's umbrella.

    Returns one result row per requested store with one of three
    statuses:

      ``updated``  — every field landed on the row
      ``rejected`` — store not in the owner's umbrella, OR a
                     field-level validation error
      (no ``skipped`` because store-info updates are idempotent
      — re-applying the same value is fine.)

    Caller commits. Per-store failures don't roll the whole
    batch back — each is reported in the response.
    """
    if not store_ids:
        raise ValueError("Pick at least one store.")
    if len(store_ids) > 50:
        raise ValueError("Cannot target more than 50 stores in one call.")
    if not defaults:
        raise ValueError("Pick at least one field to apply.")

    # Sanity-check the field whitelist before any DB writes so
    # an unknown key surfaces as 422 (validation error) rather
    # than per-store ``rejected`` rows.
    unknown = [k for k in defaults if k not in CROSS_STORE_FIELDS]
    if unknown:
        raise ValueError(
            f"Fields {unknown!r} are not cross-store-applicable.",
        )

    allowed = owner_store_ids(db, owner_id)
    name_lookup = get_store_names_map(db, list(set(store_ids)))

    results: list[dict[str, Any]] = []
    for sid in store_ids:
        store_name = name_lookup.get(sid, "")
        if sid not in allowed:
            results.append({
                "store_id": sid,
                "store_name": store_name,
                "status": "rejected",
                "detail": "Not in your store umbrella.",
            })
            continue
        store = find_store(db, sid)
        if store is None:
            results.append({
                "store_id": sid,
                "store_name": store_name,
                "status": "rejected",
                "detail": "Store row vanished mid-request.",
            })
            continue
        try:
            update_store_info(db, store, dict(defaults))
        except ValueError as exc:
            # Best-effort: a single store's validation failure
            # doesn't poison the rest of the batch.
            results.append({
                "store_id": sid,
                "store_name": store_name,
                "status": "rejected",
                "detail": str(exc),
            })
            continue
        results.append({
            "store_id": sid,
            "store_name": store_name,
            "status": "updated",
            "detail": "",
        })
    return results
