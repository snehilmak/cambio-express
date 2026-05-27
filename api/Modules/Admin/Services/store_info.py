"""Store-info update Service.

Mirrors the legacy admin-settings store tab's POST handler:
mutate the editable fields on the Store row, leave
slug/plan/billing/retention server-managed.
"""
from sqlalchemy.orm import Session

from api.Modules.Admin.Models import Store
from typing import Any


# Whitelist of fields the admin tab can write. Slug + billing +
# retention fields stay out of this list — they're managed by
# superadmin / the Stripe webhook.
EDITABLE_STORE_FIELDS: tuple[str, ...] = (
    "name", "email", "phone", "address", "federal_tax_rate",
    # Receipt customization — see ``Tenancy.Models.Store`` for the
    # per-field copy. Cleared by an empty string ("" wipes the
    # logo / footer / tax-id back to the default layout).
    "receipt_logo_url", "receipt_footer", "receipt_tax_id",
    # IANA timezone. Empty string == "unset, fall back to the
    # next layer of the per-request render chain (user.timezone
    # → store.timezone → browser default)".
    "timezone",
    # Weekly business hours — validated via
    # ``Services.store_hours.validate_hours_payload``.
    "store_hours",
    # Opt-in toggle: gate transfer create / update when current
    # store-local time is outside the configured open window.
    # Default False on the column; flips on from the Settings
    # page only.
    "enforce_business_hours",
    # Anti-buddy-punching gate on the time-clock punch flow.
    # When True, every clock-in / clock-out requires a fresh
    # WebAuthn assertion from the roster member's registered
    # passkey (Windows Hello / Touch ID / Face ID / hardware
    # key). Roster members register via the admin credentials
    # page first.
    "timeclock_require_passkey",
    # Geofence gate. ``timeclock_require_geofence`` is the
    # toggle; the lat/lng/radius columns store the pinned
    # location + tolerance the server checks at punch time.
    "timeclock_geofence_lat",
    "timeclock_geofence_lng",
    "timeclock_geofence_radius_m",
    "timeclock_require_geofence",
    # Lateness threshold (store-local minutes) for the
    # "Late by Xm" pill on the payroll history view.  Default 5.
    "timeclock_late_minutes_threshold",
    "legal_name",
    "ein",
    "business_address",
)


# Whitelist of timezone strings the settings dropdown can write.
# Mirrors ``Auth.Services.profile.TIMEZONE_CHOICES`` so the admin
# tab and personal profile offer the same picker.
ALLOWED_TIMEZONES: tuple[str, ...] = (
    "",  # explicit clear
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Phoenix",
    "America/Los_Angeles",
    "America/Anchorage",
    "Pacific/Honolulu",
    "America/Mexico_City",
    "America/Bogota",
    "America/Lima",
    "America/Santiago",
    "America/Buenos_Aires",
    "America/Sao_Paulo",
    "Europe/London",
    "Europe/Madrid",
    "Asia/Manila",
    "Asia/Karachi",
    "UTC",
)


def update_store_info(
    db: Session, store: Store, fields: dict[str, Any],
) -> Store:
    """Apply `fields` to the Store row, restricted to
    EDITABLE_STORE_FIELDS. Raises ValueError if the caller
    passes an unknown key (defensive — Pydantic should already
    have rejected it via extra=forbid).

    Caller commits.
    """
    # Lazy import — keeps the validation logic colocated with its
    # tests but out of the module-load critical path.
    from api.Modules.Admin.Services.store_hours import (
        validate_hours_payload,
    )
    for k, v in fields.items():
        if k not in EDITABLE_STORE_FIELDS:
            raise ValueError(f"Field {k!r} is not admin-editable")
        if v is None:
            continue
        if k == "timezone" and v not in ALLOWED_TIMEZONES:
            # Strict whitelist — keeps a hand-edited POST from
            # writing a bogus tz string that the rendering layer
            # would silently swallow.
            raise ValueError(
                f"Timezone {v!r} is not in the allowed list."
            )
        if k == "store_hours":
            # Re-validate the shape at the service layer so a
            # bad payload coming from a non-SPA caller (CLI,
            # scripts) still hits the same guard.
            v = validate_hours_payload(v)
        if k == "enforce_business_hours":
            # Coerce truthy values so a CLI / curl POST with "1"
            # or "true" still writes a Boolean column cleanly.
            v = bool(v)
        if k == "timeclock_require_passkey":
            v = bool(v)
        if k == "timeclock_require_geofence":
            v = bool(v)
        if k == "timeclock_late_minutes_threshold":
            v = max(0, min(240, int(v)))
        setattr(store, k, v)
    db.flush()
    return store
