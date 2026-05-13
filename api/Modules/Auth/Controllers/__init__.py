"""Auth module — Controllers (FastAPI router).

Mounts at `/api/v2/auth/*`. PR 20 ships the password-flow login
endpoint plus the JWT verification dependency that subsequent
modules (and PR 21+ Auth endpoints — TOTP, passkey, refresh) will
share.

  POST /auth/login → returns LoginResponse (access_token + user
                     summary + permissions claim list).
  GET  /auth/me   → returns the verified principal from the bearer
                     token (no DB roundtrip — claims-only).
"""
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy.orm import Session

import jwt

from api.Core.Database import get_db
from api.Core.RateLimit import limiter as _rate_limiter
from api.Modules.Auth.Models import User
from api.Modules.Auth.Requests import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginCrossStoreRequest,
    LoginRequest,
    LoginResponse,
    NotificationsResponse,
    NotificationsUpdateRequest,
    OwnerSignupRequest,
    OwnerSignupResponse,
    ProfileResponse,
    ProfileUpdateRequest,
    RecoveryLoginRequest,
    ReferralPreviewResponse,
    ResetPasswordRequest,
    SignupRequest,
    SignupResponse,
    StoreLookupResponse,
    TotpEnrollConfirmRequest,
    TotpEnrollFinishRequest,
    TotpEnrollFinishResponse,
    TotpEnrollStartRequest,
    TotpEnrollStartResponse,
    TotpLoginRequest,
)
from api.Modules.Auth.Services import (
    LoginPendingResult,
    LoginResult,
    ProfileValidationError,
    authenticate_password,
    authenticate_password_cross_store,
    change_password,
    confirm_recovery_codes_saved,
    consume_password_reset_token,
    create_owner,
    create_store_and_admin,
    decode_access_token,
    finalize_2fa_with_recovery_code,
    finalize_2fa_with_totp,
    finish_totp_enrollment,
    get_notifications_payload,
    get_profile_payload,
    issue_access_token,
    issue_password_reset_token,
    permissions_for,
    start_totp_enrollment,
    update_notifications,
    update_profile,
    verify_password_reset_token,
)
from api.Modules.Auth.Services.jwt_issuer import (
    DEFAULT_ACCESS_TOKEN_TTL_SECONDS,
    JWTIssuer,
)
from api.Modules.Auth.Services.login import (
    AuthenticationError,
    TotpEnrollmentRequired,
)
from api.Modules.Auth.Services.signup import SignupConflictError


router = APIRouter()


def get_principal(
    authorization: str | None = Header(default=None),
) -> dict:
    """FastAPI dependency: decode + verify a Bearer JWT and return the
    claims dict. Raises 401 on missing / malformed / expired / bad
    signature. Use this on any route that needs an authenticated
    caller (downstream modules will adopt this once the JWT cutover
    completes)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Empty bearer token")
    try:
        return decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401, detail="Token has expired",
            headers={"WWW-Authenticate": 'Bearer error="expired"'},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401, detail="Invalid token",
            headers={"WWW-Authenticate": 'Bearer error="invalid"'},
        )


def _to_login_response(
    result: LoginResult | LoginPendingResult,
) -> LoginResponse:
    """Translate a Service result (full or pending) into the
    polymorphic `LoginResponse` shape. Centralised so the four
    login-ish routes (login, login-cross-store, login/totp,
    login/recovery) all emit the exact same envelope."""
    if isinstance(result, LoginPendingResult):
        return LoginResponse(
            requires_totp=True,
            pending_token=result.pending_token,
            user_id=result.user_id,
            has_recovery_codes=result.has_recovery_codes,
            enroll_required=result.enroll_required,
            expires_in=DEFAULT_ACCESS_TOKEN_TTL_SECONDS,
        )
    return LoginResponse(
        access_token=result.access_token,
        expires_in=DEFAULT_ACCESS_TOKEN_TTL_SECONDS,
        user_id=result.user_id,
        username=result.username,
        full_name=result.full_name,
        role=result.role,
        store_id=result.store_id,
        permissions=result.permissions,
    )


# Cookie name + lifetime preserved from the legacy /login/<slug>
# Flask handler so behaviour stays identical: an installed-PWA
# employee who lands on `/` (or any chrome-only legacy page)
# still gets bounced to their store's sign-in URL via the
# `_active_store_from_cookie` helper. Set on every per-store
# login here too.
_LAST_STORE_SLUG_COOKIE = "ds_last_store"
_LAST_STORE_SLUG_MAX_AGE = 60 * 60 * 24 * 365  # 1 year


def _set_last_store_slug_cookie(response: Response, slug: str) -> None:
    """Mirror app._set_last_store_slug_cookie. Used by the
    per-store login flow so the SPA's `/app/login/{slug}` page
    sets the same cookie the legacy Flask route did."""
    response.set_cookie(
        key=_LAST_STORE_SLUG_COOKIE,
        value=slug,
        max_age=_LAST_STORE_SLUG_MAX_AGE,
        httponly=True,
        samesite="lax",
    )


def _record_login_event(db: Session, user_id: int, *, method: str = "") -> None:
    """Append a LoginEvent + bump User.last_login_at. Called by every
    SPA-side login path so the DAU/MAU report stays accurate. Mirrors
    `app._record_login`, but uses the FastAPI request-scoped session
    rather than Flask's. Caller is responsible for committing."""
    from datetime import datetime
    from api.Modules.Auth.Models import LoginEvent
    from api.Modules.Tenancy.Models import User
    u = db.query(User).filter(User.id == user_id).first()
    if u is None:
        return
    u.last_login_at = datetime.utcnow()
    db.add(LoginEvent(
        user_id=u.id, role=u.role or "",
        method=method, at=datetime.utcnow(),
    ))


@router.post("/login", response_model=LoginResponse)
@_rate_limiter.limit("10/minute;50/hour")
def login_route(
    request: Request,
    body: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    try:
        result = authenticate_password(
            db,
            store_id=body.store_id,
            username=body.username,
            password=body.password,
        )
    except AuthenticationError:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
        )
    except TotpEnrollmentRequired as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    # Record the LoginEvent so DAU/MAU stays accurate. Legacy Flask
    # /login routes did this via app._record_login; the SPA path
    # mirrors it here so the report doesn't go dark on migrated users.
    _record_login_event(db, result.user_id, method="password")
    # If we authed against a specific store (per-store login flow),
    # remember it in the cookie so legacy /-route fallbacks redirect
    # the user to their store's URL on next visit.
    if body.store_id is not None:
        from api.Modules.Tenancy.Models import Store
        store = db.query(Store).filter(Store.id == body.store_id).first()
        if store is not None and store.slug:
            _set_last_store_slug_cookie(response, store.slug)
    db.commit()
    return _to_login_response(result)


@router.get(
    "/store-by-slug/{slug}", response_model=StoreLookupResponse,
)
def store_by_slug_route(
    slug: str, db: Session = Depends(get_db),  # noqa: ARG001
) -> StoreLookupResponse:
    """Public store lookup for the SPA's per-store login page.
    Mirrors the legacy `/login/<slug>` route's "store must exist
    + be active" guard — inactive / unknown slugs return 404 so
    the SPA shows the same opaque-not-found shell.

    Returns just the public-safe fields (id, name, slug). No
    private detail (Stripe IDs, plan, retention dates) is exposed
    here — that lives behind the JWT-protected /admin/store-info
    endpoint."""
    from api.Modules.Tenancy.Models import Store
    s = (
        db.query(Store)
          .filter(Store.slug == (slug or "").strip().lower())
          .first()
    )
    if s is None or not s.is_active:
        raise HTTPException(status_code=404, detail="Store not found")
    return StoreLookupResponse(
        store_id=s.id, name=s.name or "", slug=s.slug or "",
    )


@router.post("/login-cross-store", response_model=LoginResponse)
def login_cross_store_route(
    body: LoginCrossStoreRequest, db: Session = Depends(get_db),
) -> LoginResponse:
    """Cross-store JWT login for the SPA's generic landing page.
    Same response shape as `/auth/login`, but takes
    username + password only — the user's home store is looked
    up across every store. Employees are rejected here so they
    use their store's slug-scoped sign-in page (parity with the
    legacy Flask `/login` POST)."""
    try:
        result = authenticate_password_cross_store(
            db, username=body.username, password=body.password,
        )
    except AuthenticationError as exc:
        # Same opaque 401 for invalid creds AND for the
        # employee-rejection path — never leak which one tripped.
        raise HTTPException(
            status_code=401, detail=str(exc) or "Invalid username or password",
        )
    except TotpEnrollmentRequired as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _to_login_response(result)


@router.post("/login/totp", response_model=LoginResponse)
def login_totp_route(
    body: TotpLoginRequest, db: Session = Depends(get_db),
) -> LoginResponse:
    """Exchange a 2FA-pending token + 6-digit TOTP code for a real
    access token. Pending token comes from the previous
    `/auth/login` (or `/auth/login-cross-store`) response when
    `requires_totp=True`."""
    try:
        result = finalize_2fa_with_totp(
            db, pending_token=body.pending_token, code=body.code,
        )
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=401, detail=str(exc) or "Invalid verification code",
        )
    db.commit()  # no-op for TOTP, but keep call shape symmetric with /recovery
    return _to_login_response(result)


@router.post("/login/recovery", response_model=LoginResponse)
def login_recovery_route(
    body: RecoveryLoginRequest, db: Session = Depends(get_db),
) -> LoginResponse:
    """Exchange a 2FA-pending token + a single-use recovery code
    for a real access token. Recovery code is consumed on success."""
    try:
        result = finalize_2fa_with_recovery_code(
            db, pending_token=body.pending_token, code=body.code,
        )
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=401, detail=str(exc) or "Invalid recovery code",
        )
    db.commit()
    return _to_login_response(result)


@router.post(
    "/login/totp/enroll/start", response_model=TotpEnrollStartResponse,
)
def login_totp_enroll_start_route(
    body: TotpEnrollStartRequest, db: Session = Depends(get_db),
) -> TotpEnrollStartResponse:
    """Mint a TOTP secret for the still-pending user and return the
    QR SVG + secret + chunks the SPA renders. Idempotent — refreshes
    return the same secret so a half-scanned QR stays valid."""
    try:
        payload = start_totp_enrollment(db, pending_token=body.pending_token)
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc) or "Invalid pending token")
    db.commit()
    return TotpEnrollStartResponse(**payload)


@router.post(
    "/login/totp/enroll/finish", response_model=TotpEnrollFinishResponse,
)
def login_totp_enroll_finish_route(
    body: TotpEnrollFinishRequest, db: Session = Depends(get_db),
) -> TotpEnrollFinishResponse:
    """Verify the user's first 6-digit code, mark enrollment
    complete, and return one-shot recovery codes. The SPA holds
    these in component state and shows them once — they are not
    retrievable later."""
    try:
        codes = finish_totp_enrollment(
            db, pending_token=body.pending_token, code=body.code,
        )
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=401, detail=str(exc) or "Invalid verification code",
        )
    db.commit()
    return TotpEnrollFinishResponse(recovery_codes=codes)


@router.post(
    "/login/totp/enroll/confirm", response_model=LoginResponse,
)
def login_totp_enroll_confirm_route(
    body: TotpEnrollConfirmRequest, db: Session = Depends(get_db),
) -> LoginResponse:
    """User has saved their recovery codes. Exchange the still-valid
    pending token for a real access token. Symmetric with
    /login/totp and /login/recovery — same envelope shape."""
    try:
        result = confirm_recovery_codes_saved(
            db, pending_token=body.pending_token,
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc) or "Invalid pending token")
    db.commit()
    return _to_login_response(result)


@router.get("/me")
def me_route(claims: dict = Depends(get_principal)) -> dict:
    """Echo the verified JWT claims. Useful for the React app's first
    paint to confirm the token is still valid + render user chrome
    without a separate DB roundtrip."""
    return {
        "user_id": int(claims["sub"]),
        "username": claims.get("username", ""),
        "full_name": claims.get("name", ""),
        "role": claims.get("role", ""),
        "store_id": claims.get("store_id"),
        "permissions": claims.get("perms", []),
    }


@router.get("/profile", response_model=ProfileResponse)
def get_profile_route(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> ProfileResponse:
    """Full Profile-page payload for the authed user. Includes
    editable fields (full_name, email, phone, timezone), read-only
    metadata (role, created_at, last_login_at), and the timezone
    dropdown options. Powers /app/account/profile."""
    user = db.query(User).filter(User.id == int(claims["sub"])).one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return ProfileResponse(**get_profile_payload(user))


@router.put("/profile", response_model=ProfileResponse)
def update_profile_route(
    body: ProfileUpdateRequest,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> ProfileResponse:
    """Update one or more profile fields. Field-level validation
    errors come back as 422 with a `field_errors` dict the SPA
    renders inline (same shape the legacy Jinja form used)."""
    user = db.query(User).filter(User.id == int(claims["sub"])).one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        update_profile(
            db, user,
            full_name=body.full_name,
            email=body.email,
            phone=body.phone,
            timezone=body.timezone,
        )
    except ProfileValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"field_errors": exc.field_errors},
        )
    db.commit()
    return ProfileResponse(**get_profile_payload(user))


@router.get("/notifications", response_model=NotificationsResponse)
def get_notifications_route(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> NotificationsResponse:
    """Per-user notification preferences. Powers
    /app/account/notifications. `trial_toggle_applies` tells the
    SPA whether the Trial-ending toggle should render as
    interactive or as a greyed-out informational row."""
    user = db.query(User).filter(User.id == int(claims["sub"])).one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return NotificationsResponse(**get_notifications_payload(db, user))


@router.put("/notifications", response_model=NotificationsResponse)
def update_notifications_route(
    body: NotificationsUpdateRequest,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> NotificationsResponse:
    """Apply notification preference changes. Both fields
    optional — None means 'don't touch'. Returns the canonical
    state after the update."""
    user = db.query(User).filter(User.id == int(claims["sub"])).one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    update_notifications(
        db, user,
        notify_trial_reminders=body.notify_trial_reminders,
        notify_announcement_email=body.notify_announcement_email,
    )
    db.commit()
    return NotificationsResponse(**get_notifications_payload(db, user))


@router.post("/change-password")
def change_password_route(
    body: ChangePasswordRequest,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> dict:
    """Self-service password change. Authed via JWT — the user
    proves identity twice (current via password, ownership via
    bearer token). Returns either `{"status": "ok"}` on success
    or 422 with a field-level error message on validation
    failure (length / mismatch / bad current).
    """
    user_id = int(claims["sub"])
    user = db.query(User).filter_by(id=user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    errors = change_password(
        db, user,
        body.current_password,
        body.new_password,
        body.confirm_password,
    )
    if errors:
        # Surface the first field error as the FastAPI detail —
        # matches how the SPA currently consumes 422 messages.
        field, msg = next(iter(errors.items()))
        raise HTTPException(
            status_code=422, detail={"field": field, "message": msg},
        )
    db.commit()
    return {"status": "ok"}


@router.post("/signup", response_model=SignupResponse, status_code=201)
@_rate_limiter.limit("5/hour;20/day")
def signup_route(
    request: Request,
    body: SignupRequest,
    db: Session = Depends(get_db),
) -> SignupResponse:
    """Self-service signup. Creates a (Store, admin User) pair
    and returns a JWT scoped to the new store, so the SPA can
    drop the user straight onto the dashboard.

    Mirrors the legacy /signup Flask form's contract:
      • email + store_name normalised (stripped, email lowered)
      • email collision returns 409
      • trial defaults: 7-day trial + 4-day grace

    Referral codes are honoured the same way the legacy /signup
    handler does it: a code that doesn't resolve is silently
    dropped (it's a nice-to-have, not a hard requirement). Stripe
    / TOTP set-up flows still belong on Flask.

    Honors the SIGNUP_CLOSED env var: when "1" we 503 every
    request before touching the DB, so an attacker hitting the
    API directly can't bypass the legacy /signup HTML guard.
    """
    from app import SIGNUP_CLOSED
    if SIGNUP_CLOSED:
        raise HTTPException(
            status_code=503,
            detail="Signups are temporarily closed. "
                   "Existing customers can still sign in.",
        )
    email = (body.email or "").strip().lower()
    store_name = (body.store_name or "").strip()
    if "@" not in email or "." not in email:
        raise HTTPException(
            status_code=422,
            detail={"field": "email", "message": "Enter a valid email."},
        )
    referred_by_code_id: int | None = None
    ref_raw = (body.ref_code or "").strip().upper()
    if ref_raw:
        from app import lookup_referral_code
        ref = lookup_referral_code(ref_raw)
        if ref is not None:
            referred_by_code_id = ref.id
    try:
        result = create_store_and_admin(
            db,
            store_name=store_name,
            email=email,
            password=body.password,
            phone=(body.phone or "").strip(),
            referred_by_code_id=referred_by_code_id,
        )
    except SignupConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={"field": "email", "message": str(exc)},
        )
    db.commit()

    # Issue a JWT scoped to the new store. Same shape as login —
    # the SPA stores it in localStorage and lands on /dashboard.
    perms = permissions_for(result.admin.role)
    issuer = JWTIssuer(
        sub=result.admin.id,
        role=result.admin.role,
        store_id=result.store.id,
        permissions=perms,
        full_name=result.admin.full_name or "",
        username=result.admin.username,
    )
    token = issue_access_token(issuer)
    return SignupResponse(
        access_token=token,
        expires_in=DEFAULT_ACCESS_TOKEN_TTL_SECONDS,
        user_id=result.admin.id,
        username=result.admin.username,
        full_name=result.admin.full_name or "",
        role=result.admin.role,
        store_id=result.store.id,
        permissions=perms,
    )


@router.post(
    "/signup/owner", response_model=OwnerSignupResponse, status_code=201,
)
def signup_owner_route(
    body: OwnerSignupRequest, db: Session = Depends(get_db),
) -> OwnerSignupResponse:
    """Self-service signup for a multi-store owner. Creates a User
    with `role="owner"` and `store_id=None`. Owners then connect to
    individual stores via invite codes from /owner/locations.

    Mirrors the legacy /signup/owner Flask form's contract:
      • full_name, email normalised (stripped, email lowered)
      • email collision (any null-store user OR any per-store admin)
        returns 409 with the same friendly message
      • returns a JWT scoped to the owner so the SPA drops the user
        straight onto /owner/dashboard

    Honors the SIGNUP_CLOSED env var: when "1" we 503 every
    request so an attacker hitting the API directly can't bypass
    the legacy /signup/owner HTML guard.
    """
    from app import SIGNUP_CLOSED
    if SIGNUP_CLOSED:
        raise HTTPException(
            status_code=503,
            detail="Signups are temporarily closed. "
                   "Existing customers can still sign in.",
        )
    email = (body.email or "").strip().lower()
    full_name = (body.full_name or "").strip()
    if "@" not in email or "." not in email:
        raise HTTPException(
            status_code=422,
            detail={"field": "email", "message": "Enter a valid email."},
        )
    try:
        result = create_owner(
            db, full_name=full_name, email=email, password=body.password,
        )
    except SignupConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={"field": "email", "message": str(exc)},
        )
    db.commit()

    perms = permissions_for(result.owner.role)
    issuer = JWTIssuer(
        sub=result.owner.id,
        role=result.owner.role,
        store_id=None,
        permissions=perms,
        full_name=result.owner.full_name or "",
        username=result.owner.username,
    )
    token = issue_access_token(issuer)
    return OwnerSignupResponse(
        access_token=token,
        expires_in=DEFAULT_ACCESS_TOKEN_TTL_SECONDS,
        user_id=result.owner.id,
        username=result.owner.username,
        full_name=result.owner.full_name or "",
        role=result.owner.role,
        store_id=None,
        permissions=perms,
    )


@router.get("/referral/{code}", response_model=ReferralPreviewResponse)
def referral_preview_route(
    code: str, db: Session = Depends(get_db),  # noqa: ARG001
) -> ReferralPreviewResponse:
    """Resolve a referral code so the SPA's /signup page can show
    the green '$X off your first paid month' banner. Returns 404
    when the code isn't recognised — matches the legacy Jinja
    behaviour where an unknown code silently dropped without a
    banner. The actual application-of-credit happens at signup
    time inside `create_store_and_admin`."""
    from app import lookup_referral_code
    ref = lookup_referral_code((code or "").strip().upper())
    if ref is None:
        raise HTTPException(status_code=404, detail="Referral code not found")
    return ReferralPreviewResponse(
        code=ref.code, reward_referee_cents=ref.reward_referee_cents,
    )


@router.post("/forgot-password")
@_rate_limiter.limit("5/minute;20/hour")
def forgot_password_route(
    request: Request,
    body: ForgotPasswordRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Issue a reset token for the user identified by `email`.

    Per the CLAUDE.md security invariant the response is always
    `{"status": "ok"}` regardless of whether the address matches
    a known user — attackers must not be able to enumerate
    registered emails via this endpoint. Inactive / superadmin /
    unknown emails silently no-op.

    The raw token is logged to the operator console only when
    SMTP isn't configured (matching the legacy /forgot-password
    Flask flow). Production setups deliver via SMTP and never
    log the URL — the SMTP send happens inline below, lifted from
    the now-retired legacy Flask handler.
    """
    issued = issue_password_reset_token(db, body.email)
    db.commit()
    if issued is not None:
        _deliver_password_reset_email(issued)
    return {"status": "ok"}


def _deliver_password_reset_email(issued) -> None:
    """Send the password-reset email. Lifted verbatim from the
    legacy /forgot-password Flask handler — same body copy, same
    HTML template, same SMTP-fallback log line — so the SPA's
    /app/forgot-password gives users an identical email."""
    import os
    from datetime import datetime
    from flask import render_template, url_for
    from app import _send_email, app as flask_app
    u = issued.user
    with flask_app.test_request_context():
        # url_for(_external=True) needs a request context; in
        # production the dispatcher already sets one, but for a
        # FastAPI-only call (no Flask request frame) we synthesise
        # one. Routes resolved here are still the canonical Flask
        # ones; the SPA equivalent path /app/reset-password?token=
        # is what the email actually sends — see below.
        base_url = os.environ.get("APP_BASE_URL", "https://dinerobook.com")
        reset_url = f"{base_url}/app/reset-password?token={issued.raw_token}"
        body = (
            "Hi,\n\n"
            "Someone (hopefully you) requested a password reset for your "
            "DineroBook account. Follow this link within the next hour to "
            "set a new password:\n\n"
            f"  {reset_url}\n\n"
            "If you didn't request this you can safely ignore this email "
            "— your current password will keep working.\n"
        )
        try:
            html = render_template(
                "emails/password_reset.html",
                preheader="Reset your DineroBook password — link expires in 1 hour.",
                name=u.full_name or "",
                reset_url=reset_url,
                year=datetime.utcnow().year,
                base_url=base_url,
            )
        except Exception:
            html = None
    to_addr = (u.email or u.username).strip()
    delivered = _send_email(
        to_addr, "Reset your DineroBook password", body, html=html,
    )
    if not delivered:
        flask_app.logger.warning(
            f"[password-reset] email send skipped for {u.username}; "
            f"reset URL: {reset_url}"
        )


@router.post("/reset-password")
@_rate_limiter.limit("5/minute;20/hour")
def reset_password_route(
    request: Request,
    body: ResetPasswordRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Consume a one-time reset token and set a new password.
    Same validation rules as change_password (length ≥ 8 +
    matching confirm)."""
    if body.new_password != body.confirm_password:
        raise HTTPException(
            status_code=422,
            detail={
                "field": "confirm_password",
                "message": "Passwords do not match.",
            },
        )
    token = verify_password_reset_token(db, body.token)
    if token is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "This reset link is invalid or has expired. "
                "Request a new one from the forgot-password page."
            ),
        )
    consume_password_reset_token(db, token, body.new_password)
    db.commit()
    return {"status": "ok"}


# ── Passkey management (list + register + delete) ───────────
#
# Login verification still lives on the legacy /login/passkey/*
# routes (it's tied to the Flask session promotion path the SPA
# doesn't drive yet). Registration moved here so the SPA's
# Settings page can run the full enrollment dance — the
# WebAuthn challenge bridges between begin and finish via a
# short-lived signed JWT (`purpose: passkey-register`) since
# FastAPI doesn't share Flask's `session` dict.

@router.post("/passkeys/register/begin")
def passkey_register_begin_route(
    request: Request,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> dict:
    """Mint a WebAuthn registration challenge for the authed
    user. Returns the challenge-options JSON that the SPA passes
    to `navigator.credentials.create()`, plus a `register_token`
    the SPA echoes back on `/passkeys/register/finish` so the
    server can verify the credential against the same challenge.
    """
    from api.Modules.Tenancy.Models import User
    from webauthn import generate_registration_options, options_to_json
    from webauthn.helpers import bytes_to_base64url
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )
    from api.Modules.Auth.Services import (
        is_enrolled, issue_passkey_register_token, needs_totp,
        passkey_exclude_credentials, passkey_is_eligible,
        passkey_rp_id, passkey_rp_name,
    )

    sub = claims.get("sub")
    if sub is None:
        raise HTTPException(status_code=401, detail="JWT missing sub claim")
    user = db.query(User).filter(User.id == int(sub)).one_or_none()
    if user is None or not passkey_is_eligible(user):
        raise HTTPException(
            status_code=403,
            detail="Passkeys aren't enabled for this account.",
        )
    # Mirrors legacy `_passkey_eligible`: superadmin must be 2FA-
    # enrolled before adding a passkey, since a passkey skips TOTP.
    if needs_totp(user) and not is_enrolled(user):
        raise HTTPException(
            status_code=403,
            detail="Enroll TOTP before adding a passkey.",
        )

    host = request.url.netloc
    options = generate_registration_options(
        rp_id=passkey_rp_id(host),
        rp_name=passkey_rp_name(),
        user_id=str(user.id).encode("utf-8"),
        user_name=user.username,
        user_display_name=user.full_name or user.username,
        exclude_credentials=passkey_exclude_credentials(db, user),
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    challenge_b64 = bytes_to_base64url(options.challenge)
    return {
        "options_json":   options_to_json(options),
        "register_token": issue_passkey_register_token(
            user.id, challenge_b64,
        ),
    }


@router.post("/passkeys/register/finish")
def passkey_register_finish_route(
    body: dict,
    request: Request,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> dict:
    """Verify the credential the browser produced + the still-valid
    register_token, then persist the new Passkey row. Returns the
    new passkey's metadata (matches the GET /passkeys row shape so
    the SPA can append it client-side without a refetch)."""
    import jwt as _jwt
    from api.Modules.Auth.Models import Passkey
    from api.Modules.Tenancy.Models import User
    from webauthn import verify_registration_response
    from webauthn.helpers import base64url_to_bytes
    from api.Modules.Auth.Services import (
        decode_passkey_register_token,
        passkey_is_eligible, passkey_origin, passkey_rp_id,
    )

    sub = claims.get("sub")
    if sub is None:
        raise HTTPException(status_code=401, detail="JWT missing sub claim")
    user = db.query(User).filter(User.id == int(sub)).one_or_none()
    if user is None or not passkey_is_eligible(user):
        raise HTTPException(
            status_code=403,
            detail="Passkeys aren't enabled for this account.",
        )

    register_token = (body or {}).get("register_token") or ""
    credential = (body or {}).get("credential")
    name = ((body or {}).get("name") or "").strip()[:120] or "Passkey"
    if not register_token or credential is None:
        raise HTTPException(status_code=400, detail="Missing register_token or credential.")
    try:
        reg_claims = decode_passkey_register_token(register_token)
    except _jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc) or "register_token invalid or expired",
        )
    # Belt + suspenders: token MUST belong to the authed user.
    if int(reg_claims.get("sub") or 0) != user.id:
        raise HTTPException(status_code=400, detail="register_token does not match this user.")

    host = request.url.netloc
    try:
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(reg_claims["challenge"]),
            expected_origin=passkey_origin(request.url.scheme, host),
            expected_rp_id=passkey_rp_id(host),
            require_user_verification=False,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Passkey could not be verified ({type(exc).__name__}).",
        )

    p = Passkey(
        user_id=user.id,
        credential_id=verification.credential_id,
        public_key=verification.credential_public_key,
        sign_count=verification.sign_count,
        name=name,
        aaguid=str(verification.aaguid or ""),
    )
    db.add(p); db.commit(); db.refresh(p)
    return {
        "passkey": {
            "id":            p.id,
            "name":          p.name or "",
            "created_at":    p.created_at.isoformat() if p.created_at else "",
            "last_used_at":  p.last_used_at.isoformat() if p.last_used_at else "",
        }
    }


# ── Passkey management (list + delete) ──────────────────────
#
# Login verification (the assertion flow on
# /login/passkey/*) stays on Flask for now — it's tied to the
# session promotion path the SPA doesn't yet drive end-to-end.
# orchestration that's a separate migration. Read + delete are
# pure server-side and ship here so the SPA's settings page can
# show the user's registered devices without bouncing to legacy.


@router.get("/passkeys")
def list_passkeys_route(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> dict:
    """List the authenticated user's registered passkeys.
    Returns only the metadata the SPA renders — never the raw
    credential_id or public_key (those stay server-side)."""
    sub = claims.get("sub")
    if sub is None:
        raise HTTPException(status_code=401, detail="JWT missing sub claim")
    from api.Modules.Auth.Models import Passkey
    rows = (
        db.query(Passkey)
          .filter(Passkey.user_id == int(sub))
          .order_by(Passkey.created_at.desc())
          .all()
    )
    return {
        "passkeys": [
            {
                "id":            p.id,
                "name":          p.name or "",
                "aaguid":        p.aaguid or "",
                "transports":    p.transports or "",
                "created_at":    p.created_at.isoformat() if p.created_at else "",
                "last_used_at":  p.last_used_at.isoformat() if p.last_used_at else "",
            }
            for p in rows
        ],
        "total": len(rows),
    }


@router.delete("/passkeys/{passkey_id}", status_code=204)
def delete_passkey_route(
    passkey_id: int,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> None:
    """Remove one of the authenticated user's passkeys. 404 if it
    doesn't belong to them — never confirms existence of a passkey
    the caller doesn't own."""
    sub = claims.get("sub")
    if sub is None:
        raise HTTPException(status_code=401, detail="JWT missing sub claim")
    from api.Modules.Auth.Models import Passkey
    p = (
        db.query(Passkey)
          .filter(
              Passkey.id == passkey_id,
              Passkey.user_id == int(sub),
          )
          .one_or_none()
    )
    if p is None:
        raise HTTPException(status_code=404, detail="Passkey not found")
    db.delete(p)
    db.commit()
    return None
