"""Support — Request/response schemas."""
from pydantic import BaseModel, ConfigDict, Field


TICKET_CATEGORIES = ("bug", "feature", "question", "feedback")
TICKET_STATUSES = ("open", "in_progress", "resolved", "closed")
TICKET_PRIORITIES = ("P1", "P2", "P3", "P4")


class CreateTicketRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str = Field(..., min_length=1, max_length=30)
    subject: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1, max_length=5000)


class UpdateTicketRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str | None = None
    priority: str | None = None
    # Legacy single-reply field. Still accepted: setting it now ALSO
    # appends a staff message to the thread (the thread is the source
    # of truth; this column is dual-written for back-compat).
    admin_reply: str | None = None


class CreateMessageRequest(BaseModel):
    """One reply into a ticket's conversation thread."""

    model_config = ConfigDict(extra="forbid")

    body: str = Field(..., min_length=1, max_length=5000)


class MessageRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    ticket_id: int
    author_name: str
    # "user" (someone at the store) or "staff" (platform side) —
    # drives which side the chat bubble renders on.
    author_kind: str
    body: str
    created_at: str


class MessageListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[MessageRow]
    total: int


class TicketRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    store_id: int
    user_id: int
    submitted_by: str
    category: str
    priority: str | None
    subject: str
    body: str
    status: str
    admin_reply: str | None
    replied_at: str | None
    replied_by: str | None
    created_at: str
    updated_at: str
    closed_at: str | None
    store_name: str | None = None
    # Claim/assignment — which platform-staff person is working
    # the ticket (None = unclaimed).
    assigned_to_user_id: int | None = None
    assigned_to_name: str | None = None


class TicketListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tickets: list[TicketRow]
    total: int


class TicketResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket: TicketRow
