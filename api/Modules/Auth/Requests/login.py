"""Pydantic schemas for the login endpoint."""
from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """POST body for /auth/login. `store_id` is None for the
    superadmin scope; positive integer otherwise."""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1)
    store_id: int | None = None


class LoginCrossStoreRequest(BaseModel):
    """POST body for /auth/login-cross-store. The SPA's generic
    landing page doesn't know which store a user belongs to — this
    endpoint takes username + password only and looks up the
    user's home store across all stores (first match wins, like
    the legacy Flask `/login` POST). Employees get rejected here
    because they're expected to use their store's slug-scoped
    sign-in URL.
    """

    model_config = ConfigDict(extra="forbid")

    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1)


class ChangePasswordRequest(BaseModel):
    """POST body for /auth/change-password. Takes the user's
    current password (proof of identity) plus the new password
    twice. Same validation rules as the legacy /account/security
    form — length ≥ 8 and the two new entries must match."""

    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(..., min_length=1)
    new_password:     str = Field(..., min_length=1)
    confirm_password: str = Field(..., min_length=1)


class ForgotPasswordRequest(BaseModel):
    """POST body for /auth/forgot-password. Always responds 200
    regardless of whether the email exists — the legacy contract
    is "Check your email" so attackers can't enumerate registered
    addresses."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(..., min_length=1, max_length=255)


class ResetPasswordRequest(BaseModel):
    """POST body for /auth/reset-password. Uses the raw
    one-time token from the emailed reset link."""

    model_config = ConfigDict(extra="forbid")

    token:            str = Field(..., min_length=1, max_length=255)
    new_password:     str = Field(..., min_length=8, max_length=200)
    confirm_password: str = Field(..., min_length=8, max_length=200)


class SignupRequest(BaseModel):
    """POST body for /auth/signup. Mirrors the legacy /signup
    Jinja form. Returns a JWT on success so the SPA can drop
    the new admin straight onto the dashboard without a second
    login round-trip."""

    model_config = ConfigDict(extra="forbid")

    store_name: str = Field(..., min_length=1, max_length=120)
    email:      str = Field(..., min_length=3, max_length=255)
    password:   str = Field(..., min_length=8, max_length=200)
    phone:      str = Field("", max_length=40)
    ref_code:   str = Field("", max_length=64)


class SignupResponse(BaseModel):
    """Same shape as LoginResponse — the SPA uses identical code
    paths to handle both flows."""

    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 30 * 60
    user_id: int
    username: str
    full_name: str = ""
    role: str
    store_id: int | None
    permissions: list[str]


class ReferralPreviewResponse(BaseModel):
    """GET /auth/referral/{code} return shape. Powers the green
    'You'll get $X off' banner that shows up on /signup when the
    code resolves to an active ReferralCode row."""

    model_config = ConfigDict(extra="forbid")

    code: str
    reward_referee_cents: int


class LoginResponse(BaseModel):
    """Login response. Two shapes:

    - **Full success**: `access_token` is the bearer JWT the client
      must send as `Authorization: Bearer <token>` on subsequent
      calls. `requires_totp` is False, `pending_token` is None.

    - **2FA pending**: `requires_totp=True` and `pending_token` is a
      short-lived JWT (5min) the SPA exchanges via
      `/auth/login/totp` or `/auth/login/recovery` for a real
      `access_token`. In this shape `access_token` is empty.

    Clients should branch on `requires_totp` first.
    """

    model_config = ConfigDict(extra="forbid")

    access_token: str = ""
    token_type: str = "Bearer"
    expires_in: int = 30 * 60
    user_id: int
    username: str = ""
    full_name: str = ""
    role: str = ""
    store_id: int | None = None
    permissions: list[str] = []
    # 2FA-pending fields. None / False on the full-success path.
    requires_totp: bool = False
    pending_token: str | None = None
    has_recovery_codes: bool = False
    # Set when `requires_totp=True` AND the user hasn't enrolled yet,
    # so the SPA routes to /app/login/2fa/enroll instead of
    # /app/login/2fa. False on every other shape.
    enroll_required: bool = False


class TotpLoginRequest(BaseModel):
    """POST body for /auth/login/totp. Exchange the 2FA-pending
    token + the user's 6-digit TOTP code for a real access token."""

    model_config = ConfigDict(extra="forbid")

    pending_token: str = Field(..., min_length=1)
    code:          str = Field(..., min_length=1, max_length=10)


class RecoveryLoginRequest(BaseModel):
    """POST body for /auth/login/recovery. Exchange the 2FA-pending
    token + a single-use recovery code for a real access token.
    The recovery code is consumed on success."""

    model_config = ConfigDict(extra="forbid")

    pending_token: str = Field(..., min_length=1)
    code:          str = Field(..., min_length=1, max_length=40)


class TotpEnrollStartRequest(BaseModel):
    """POST body for /auth/login/totp/enroll/start. Given a 2FA-pending
    token from a successful password login, mint or reuse a TOTP
    secret and return the QR/secret payload the SPA renders."""

    model_config = ConfigDict(extra="forbid")

    pending_token: str = Field(..., min_length=1)


class TotpEnrollStartResponse(BaseModel):
    """Payload the SPA renders on the enrollment page: the QR SVG
    string, the manual-entry secret split into 4-char chunks, and
    the username + issuer for users keying secrets manually."""

    model_config = ConfigDict(extra="forbid")

    qr_svg:         str
    secret:         str
    secret_chunks:  str
    username:       str
    issuer:         str


class TotpEnrollFinishRequest(BaseModel):
    """POST body for /auth/login/totp/enroll/finish. Given the
    pending token + the 6-digit code from the user's authenticator
    app, mark enrollment complete and return the freshly-minted
    one-shot recovery codes."""

    model_config = ConfigDict(extra="forbid")

    pending_token: str = Field(..., min_length=1)
    code:          str = Field(..., min_length=1, max_length=10)


class TotpEnrollFinishResponse(BaseModel):
    """Recovery codes returned on successful enrollment. The SPA
    holds these in component state and shows them once — there is
    no GET endpoint to re-fetch them."""

    model_config = ConfigDict(extra="forbid")

    recovery_codes: list[str]


class TotpEnrollConfirmRequest(BaseModel):
    """POST body for /auth/login/totp/enroll/confirm. Finalises the
    login after the user has confirmed they saved their recovery
    codes. Returns a full LoginResponse with access_token."""

    model_config = ConfigDict(extra="forbid")

    pending_token: str = Field(..., min_length=1)


class OwnerSignupRequest(BaseModel):
    """POST body for /auth/signup/owner. Mirrors the legacy
    /signup/owner Jinja form. Returns a JWT on success so the SPA
    drops the new owner straight onto /owner/dashboard."""

    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(..., min_length=1, max_length=120)
    email:     str = Field(..., min_length=3, max_length=255)
    password:  str = Field(..., min_length=8, max_length=200)


class OwnerSignupResponse(BaseModel):
    """Same shape as LoginResponse — the SPA reuses the standard
    auth handoff (set token, then navigate). `store_id` is always
    None for owners (they manage many stores via invite codes)."""

    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 30 * 60
    user_id: int
    username: str
    full_name: str = ""
    role: str
    store_id: int | None
    permissions: list[str]


class StoreLookupResponse(BaseModel):
    """GET /auth/store-by-slug/{slug} — public lookup so the SPA's
    per-store login page can render the store name in its branding
    pane before the user authenticates. Inactive / unknown slugs
    return 404."""

    model_config = ConfigDict(extra="forbid")

    store_id: int
    name: str
    slug: str
