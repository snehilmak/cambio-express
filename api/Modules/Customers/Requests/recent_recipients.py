"""Schemas for the per-customer "recent recipients" endpoint.

Returns the last N distinct recipients a customer has sent to,
scoped to the caller's owner umbrella. Powers the chip-row above
the recipient_name input on the transfer form — most senders
send to the same 1-2 people, so a one-tap chip cuts a lot of
typing.
"""
from pydantic import BaseModel, ConfigDict


class RecentRecipientRow(BaseModel):
    """One recipient the customer has previously sent to."""

    model_config = ConfigDict(extra="forbid")

    name:    str
    country: str
    phone:   str


class RecentRecipientsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[RecentRecipientRow]
