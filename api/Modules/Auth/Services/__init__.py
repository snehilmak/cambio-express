"""Auth — Services. Composes Repository SQL with the JWT issuer +
password-flow business logic. The Controller layer (PR 20+) wires
these to HTTP routes.
"""
from api.Modules.Auth.Services.jwt_issuer import (
    JWTIssuer,
    decode_access_token,
    issue_access_token,
)
from api.Modules.Auth.Services.login import (
    LoginResult,
    authenticate_password,
    permissions_for,
    verify_password_cross_store,
)

__all__ = [
    "JWTIssuer",
    "LoginResult",
    "authenticate_password",
    "decode_access_token",
    "issue_access_token",
    "permissions_for",
    "verify_password_cross_store",
]
