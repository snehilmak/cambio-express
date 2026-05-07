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
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

import jwt

from api.Core.Database import get_db
from api.Modules.Auth.Models import User
from api.Modules.Auth.Requests import (
    ChangePasswordRequest,
    LoginCrossStoreRequest,
    LoginRequest,
    LoginResponse,
)
from api.Modules.Auth.Services import (
    authenticate_password,
    authenticate_password_cross_store,
    change_password,
    decode_access_token,
)
from api.Modules.Auth.Services.jwt_issuer import (
    DEFAULT_ACCESS_TOKEN_TTL_SECONDS,
)
from api.Modules.Auth.Services.login import AuthenticationError


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


@router.post("/login", response_model=LoginResponse)
def login_route(
    body: LoginRequest, db: Session = Depends(get_db),
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
