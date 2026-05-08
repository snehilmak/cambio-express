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
        setattr(store, k, v)
    db.flush()
    return store
