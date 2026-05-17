"""Pydantic schemas for the admin store-info endpoints."""
from pydantic import BaseModel, ConfigDict, Field


class StoreHourEntry(BaseModel):
    """One row in the weekly schedule. ``day`` is 0..6 (ISO,
    0=Monday). ``open`` / ``close`` are "HH:MM" 24-hour strings.
    ``closed`` overrides the open/close pair — when True the
    times are ignored at the gating layer.

    Pydantic-level validation is intentionally light (string
    presence + range) — the deeper checks (open < close, no
    duplicate days, exactly 7 entries) live in
    ``Services.store_hours.validate_hours_payload`` so they can
    be tested without instantiating a request."""

    model_config = ConfigDict(extra="forbid")

    day:    int  = Field(..., ge=0, le=6)
    open:   str  = Field(..., max_length=5)
    close:  str  = Field(..., max_length=5)
    closed: bool = False


class StoreInfoRow(BaseModel):
    """Read shape — fields the SPA's settings page renders.
    Slug / plan / billing fields are read-only here; the
    superadmin owns those.

    Receipt customization fields drive ``/app/transfers/{id}/receipt``
    — empty values fall back to the default layout (store name +
    system footer)."""

    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    slug: str
    email: str = ""
    phone: str = ""
    address: str = ""
    plan: str = "trial"
    federal_tax_rate: float = 0.01
    is_active: bool = True
    receipt_logo_url: str = ""
    receipt_footer:   str = ""
    receipt_tax_id:   str = ""
    timezone:         str = ""
    timezone_choices: list[str] = []
    # Always exactly 7 entries on the read side (the adapter
    # substitutes defaults when the column is NULL) so the SPA
    # can render a complete schedule without nullability checks.
    store_hours:      list[StoreHourEntry] = []


class StoreInfoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store: StoreInfoRow


class StoreInfoUpdateRequest(BaseModel):
    """PUT body. Only the operator-editable fields. Slug,
    plan, billing, retention etc. stay server-managed."""

    model_config = ConfigDict(extra="forbid")

    name:             str | None = Field(None, max_length=120)
    email:            str | None = Field(None, max_length=120)
    phone:            str | None = Field(None, max_length=40)
    address:          str | None = Field(None, max_length=255)
    federal_tax_rate: float | None = Field(None, ge=0, le=1)
    receipt_logo_url: str | None = Field(None, max_length=500)
    receipt_footer:   str | None = Field(None, max_length=500)
    receipt_tax_id:   str | None = Field(None, max_length=40)
    timezone:         str | None = Field(None, max_length=60)
    store_hours:      list[StoreHourEntry] | None = None
