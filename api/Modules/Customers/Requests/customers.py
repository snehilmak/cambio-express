"""Pydantic schemas for customer search + upsert.

`CustomerRow` mirrors the dict shape produced by `Customer.to_dict()`
in `app.py` so the React frontend gets the same payload shape from
both surfaces. Any field renamed here must also be renamed in the
service-layer adapter that fills the dict — those are the two
points of drift to keep aligned.
"""
from pydantic import BaseModel, ConfigDict, Field


class CustomerRow(BaseModel):
    """One row in the autocomplete picker. The JSON keys match the
    legacy `Customer.to_dict()` output 1:1."""

    model_config = ConfigDict(extra="forbid")

    id: int
    full_name: str
    dob: str = ""
    address: str = ""
    phone_country: str = ""
    phone_number: str = ""
    home_store_id: int
    home_store_name: str = ""


class CustomerSearchResponse(BaseModel):
    """Autocomplete response envelope.

    `matches`: ILIKE substring hits on `full_name` or `phone_number`,
    sorted by `updated_at` desc.
    `suggestions`: fuzzy near-misses (different list so the UI can
    label "Did you mean…?"). Empty unless the query is >= 4 chars
    AND `matches` has room (< 5 entries).
    """

    model_config = ConfigDict(extra="forbid")

    matches: list[CustomerRow] = Field(default_factory=list)
    suggestions: list[CustomerRow] = Field(default_factory=list)


class CustomerUpsertRequest(BaseModel):
    """Body for POST upsert (the new transfer form's hidden submission).

    All fields except `full_name` are optional — empty strings are
    legal placeholders for senders without a phone or address on file.
    `customer_id` is honored only when the target lives in the
    caller's owner umbrella (enforced by the Repository layer).
    """

    model_config = ConfigDict(extra="forbid")

    full_name: str
    phone_country: str = "+1"
    phone_number: str = ""
    address: str = ""
    dob: str = ""
    customer_id: int | None = None


class CustomerUpsertResponse(BaseModel):
    """Single-customer payload returned by upsert. Same shape as one
    `CustomerRow` so the frontend can reuse the row component."""

    model_config = ConfigDict(extra="forbid")

    customer: CustomerRow
