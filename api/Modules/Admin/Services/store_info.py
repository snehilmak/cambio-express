"""Store-info update Service.

Mirrors the legacy admin-settings store tab's POST handler:
mutate the editable fields on the Store row, leave
slug/plan/billing/retention server-managed.
"""
from sqlalchemy.orm import Session

from api.Modules.Admin.Models import Store


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
    db: Session, store: Store, fields: dict,
) -> Store:
    """Apply `fields` to the Store row, restricted to
    EDITABLE_STORE_FIELDS. Raises ValueError if the caller
    passes an unknown key (defensive — Pydantic should already
    have rejected it via extra=forbid).

    Caller commits.
    """
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
        setattr(store, k, v)
    db.flush()
    return store
