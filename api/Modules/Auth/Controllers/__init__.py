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
from api.Modules.Auth.Requests import LoginRequest, LoginResponse
from api.Modules.Auth.Services import (
    authenticate_password,
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
