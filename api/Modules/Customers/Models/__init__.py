"""Customers — Models.

* ``Customer`` — the per-store customer directory row, autofilled
                 on the transfer form for returning senders.

``Store`` and ``StoreOwnerLink`` are re-exported from
``api/Modules/Tenancy/Models`` so the existing umbrella-resolution
imports keep working.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Column, Date, DateTime, ForeignKey, Index, Integer, String,
    UniqueConstraint,
)

from api.Core.Database import Base


class Customer(Base):
    """Per-store customer directory used to autofill returning-sender
    info.

    Unique within a store on ``(phone_country, phone_number)`` so the
    same person can be reached the same way twice. Soft fields
    (address, dob) are free to update on each visit — newest values
    win.
    """

    __tablename__ = "customer"
    id            = Column(Integer, primary_key=True)
    store_id      = Column(Integer, ForeignKey("store.id"), nullable=False)
    full_name     = Column(String(120), nullable=False)
    dob           = Column(Date, nullable=True)
    address       = Column(String(255), default="")
    phone_country = Column(String(8),  default="+1")
    phone_number  = Column(String(40), default="")
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("store_id", "phone_country", "phone_number",
                          name="uq_customer_store_phone"),
        # Umbrella-upsert lookup: ``find_by_phone_in_stores()`` filters
        # ``store_id IN (sibling_ids) AND phone_country = ? AND
        # phone_number = ?``. The unique constraint above leads with
        # ``store_id``, so it forces N index seeks for an N-store
        # umbrella. Indexing on (phone_country, phone_number) lets the
        # planner do a single seek and filter on store_id — cheaper
        # for owner umbrellas with several stores, no worse for
        # single-store admins.
        Index("ix_customer_phone", "phone_country", "phone_number"),
    )

    def to_dict(
        self,
        current_store_id: int | None = None,
        home_names: dict[int, str] | None = None,
    ) -> dict[str, Any]:
        """JSON payload for the autocomplete.

        When ``current_store_id`` is passed and doesn't match this
        customer's home store, ``home_store_name`` is filled from
        ``home_names`` (id → name map) so the UI can label the row
        "from Store X".
        """
        d = {
            "id": self.id,
            "full_name": self.full_name,
            "dob": self.dob.isoformat() if self.dob else "",
            "address": self.address or "",
            "phone_country": self.phone_country or "",
            "phone_number": self.phone_number or "",
            "home_store_id": self.store_id,
            "home_store_name": "",
        }
        if current_store_id is not None and self.store_id != current_store_id:
            d["home_store_name"] = (home_names or {}).get(int(self.store_id), "")
        return d


# Re-export sibling-store models for the existing umbrella-resolution
# imports.
from api.Modules.Tenancy.Models import Store, StoreOwnerLink  # noqa: E402


__all__ = ["Customer", "Store", "StoreOwnerLink"]
