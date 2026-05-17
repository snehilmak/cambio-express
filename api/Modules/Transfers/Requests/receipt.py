"""Schemas for the printable transfer receipt.

Backs ``GET /api/v2/transfers/{id}/receipt``. The SPA renders a
print-optimized page (``/app/transfers/{id}/receipt``) for the
operator to hand to the customer; this endpoint hands back the
transfer fields + the store's branding metadata in one shot so
the route doesn't have to chain two fetches.
"""
from pydantic import BaseModel, ConfigDict


class ReceiptStore(BaseModel):
    """Store header — branding + identifiers printed at the top
    of the receipt. Legal-info fields are empty strings unless
    the operator filled them on /app/settings — the renderer
    suppresses the corresponding line when blank."""

    model_config = ConfigDict(extra="forbid")

    name:             str
    address:          str
    phone:            str
    email:            str
    receipt_logo_url: str
    receipt_footer:   str
    receipt_tax_id:   str
    legal_name:       str = ""
    ein:              str = ""
    legal_address:    str = ""


class ReceiptTransfer(BaseModel):
    """Transfer body — the ledger details the customer signs off on.

    Every numeric field is a plain ``float`` (USD). Dates / times
    are ISO-8601 strings — the SPA formats per the user's locale.
    Empty strings on optional fields render as blanks rather than
    a missing column."""

    model_config = ConfigDict(extra="forbid")

    id:                   int
    send_date:            str
    created_at:           str
    company:              str
    service_type:         str
    sender_name:          str
    sender_phone:         str
    sender_phone_country: str
    sender_address:       str
    recipient_name:       str
    recipient_phone:      str
    country:              str
    confirm_number:       str
    send_amount:          float
    fee:                  float
    federal_tax:          float
    total_collected:      float
    status:               str
    employee_name:        str


class TransferReceiptResponse(BaseModel):
    """Full receipt payload — both halves in one envelope."""

    model_config = ConfigDict(extra="forbid")

    store:    ReceiptStore
    transfer: ReceiptTransfer
