"""Lottery — Request/response schemas.

Money crosses the API as dollars floats (the app-wide contract);
cents stay in the DB + Services (P0-3 convention).
"""
from pydantic import BaseModel, ConfigDict, Field


class GameWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    game_number:      str = Field(..., min_length=1, max_length=20)
    name:             str = Field(..., min_length=1, max_length=120)
    ticket_price:     float = Field(..., ge=0)
    tickets_per_pack: int = Field(..., ge=1, le=10000)


class GameUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name:             str | None = Field(None, min_length=1, max_length=120)
    ticket_price:     float | None = Field(None, ge=0)
    tickets_per_pack: int | None = Field(None, ge=1, le=10000)
    is_active:        bool | None = None


class GameRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    game_number: str
    name: str
    ticket_price: float
    tickets_per_pack: int
    is_active: bool


class GameListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    games: list[GameRow]


class GameResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    game: GameRow


class PackReceiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    game_id:     int = Field(..., ge=1)
    pack_number: str = Field(..., min_length=1, max_length=40)
    received_on: str = Field(..., min_length=10, max_length=10)  # YYYY-MM-DD


class PackActivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activated_on:   str = Field(..., min_length=10, max_length=10)
    opening_ticket: int = Field(0, ge=0)
    bin_number:     str = Field("", max_length=10)


class PackDateRequest(BaseModel):
    """Settle / return — just the effective date."""

    model_config = ConfigDict(extra="forbid")

    on: str = Field(..., min_length=10, max_length=10)


class PackRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    game_id: int
    game_number: str
    game_name: str
    ticket_price: float
    tickets_per_pack: int
    pack_number: str
    status: str
    bin_number: str
    received_on: str | None
    activated_on: str | None
    settled_on: str | None
    opening_ticket: int


class PackListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    packs: list[PackRow]


class PackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pack: PackRow


class DayCountWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pack_id:        int = Field(..., ge=1)
    closing_ticket: int = Field(..., ge=0)


class DayCountRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pack_id: int
    pack_number: str
    bin_number: str
    game_number: str
    game_name: str
    ticket_price: float
    counted: bool
    closing_ticket: int | None
    previous_reference: int
    sold: int
    value: float


class DaySummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str
    rows: list[DayCountRow]
    total_sold: int
    total_value: float
    uncounted_active_packs: int
