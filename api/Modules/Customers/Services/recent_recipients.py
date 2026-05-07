"""Recent-recipients lookup for the transfer form.

Returns the last N distinct recipients a given customer has sent
to, scoped to the caller's owner umbrella. Powers the "recent
recipients" chip row above the recipient_name input on the
transfer form — most senders send to the same 1-2 people, so a
one-tap chip cuts a lot of typing.

Scope = umbrella means a returning sender at Store B sees the same
chips they'd see at Store A. Canceled / Rejected transfers are
excluded — recipients of failed transfers aren't ones the sender
will reuse.
"""
from dataclasses import dataclass

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

# The Transfer + _OWNER_TRANSFER_EXCLUDED model + status filter are
# already re-exported on the Reports module side; we reuse those
# rather than build a parallel re-export.
from api.Modules.Customers.Repositories import (
    find_by_id_in_stores,
    sibling_store_ids,
)
from api.Modules.Reports.Models import Transfer, _OWNER_TRANSFER_EXCLUDED


@dataclass
class RecentRecipient:
    """Wire-shape for one chip row. Mirrors the JSON the legacy
    /api/customers/<id>/recent-recipients route already emits."""
    name: str
    country: str
    phone: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "country": self.country or "",
            "phone": self.phone or "",
        }


def list_recent_recipients(
    db: Session, customer_id: int, viewer_store_id: int,
    *, limit: int = 5,
) -> list[RecentRecipient]:
    """Return up to `limit` distinct recipients this customer has
    sent to, ordered by most-recent send date desc.

    `viewer_store_id` is the caller's current store; the lookup is
    restricted to the owner umbrella that contains that store. If
    the customer doesn't exist in the umbrella the result is an
    empty list (matches the legacy "404 → empty list" UX)."""
    siblings = sibling_store_ids(db, viewer_store_id)
    customer = find_by_id_in_stores(db, customer_id, siblings)
    if customer is None:
        return []
    rows = (
        db.query(
            Transfer.recipient_name,
            Transfer.country,
            Transfer.recipient_phone,
            func.max(Transfer.send_date),
        )
        .filter(
            Transfer.customer_id == customer_id,
            Transfer.store_id.in_(siblings),
            Transfer.status.notin_(_OWNER_TRANSFER_EXCLUDED),
            Transfer.recipient_name != "",
        )
        .group_by(
            Transfer.recipient_name,
            Transfer.country,
            Transfer.recipient_phone,
        )
        .order_by(desc(func.max(Transfer.send_date)))
        .limit(limit)
        .all()
    )
    return [
        RecentRecipient(name=name, country=country or "", phone=phone or "")
        for name, country, phone, _last in rows
    ]
