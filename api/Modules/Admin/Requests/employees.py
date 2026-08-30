"""Unified Employees hub — request/response schemas (E-1)."""
from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class EmployeeLoginInfo(BaseModel):
    """The login half of a person, when one is linked."""

    model_config = ConfigDict(extra="forbid")

    user_id:   int
    username:  str
    role:      str
    is_active: bool
    has_custom_permissions: bool


class EmployeeRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id:          int
    name:        str
    is_active:   bool
    hourly_rate: float
    hired_on:      str | None  # ISO date or null
    date_of_birth: str | None
    email:         str
    phone:         str
    address_line1: str
    address_line2: str
    payroll_schedule: str
    login: EmployeeLoginInfo | None


class LoginOnlyRow(BaseModel):
    """A store login with no HR record yet — shown in the hub with
    Link / Create-record actions so it can't go invisible."""

    model_config = ConfigDict(extra="forbid")

    user_id:   int
    username:  str
    full_name: str
    role:      str
    is_active: bool


class EmployeesListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[EmployeeRow]
    login_only: list[LoginOnlyRow]


class EmployeeCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=120)
    hourly_rate: float = Field(0.0, ge=0, le=10_000)
    hired_on:      date | None = None
    date_of_birth: date | None = None
    email:         str = Field("", max_length=255)
    phone:         str = Field("", max_length=40)
    address_line1: str = Field("", max_length=255)
    address_line2: str = Field("", max_length=255)
    payroll_schedule: str = Field("", max_length=20)
    # Optionally attach an existing login at creation time.
    user_id: int | None = None


class EmployeeUpdateRequest(BaseModel):
    """PATCH semantics — omitted fields stay unchanged. The two
    ``clear_*`` flags reset the nullable dates (None can't be the
    clear sentinel on an optional field)."""

    model_config = ConfigDict(extra="forbid")

    name:        str | None = Field(None, min_length=1, max_length=120)
    is_active:   bool | None = None
    hourly_rate: float | None = Field(None, ge=0, le=10_000)
    hired_on:      date | None = None
    date_of_birth: date | None = None
    clear_hired_on:      bool = False
    clear_date_of_birth: bool = False
    email:         str | None = Field(None, max_length=255)
    phone:         str | None = Field(None, max_length=40)
    address_line1: str | None = Field(None, max_length=255)
    address_line2: str | None = Field(None, max_length=255)
    payroll_schedule: str | None = Field(None, max_length=20)


class EmployeeLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int = Field(..., ge=1)
