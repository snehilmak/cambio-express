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
from api.Modules.Auth.Services.password_reset import (
    IssuedToken,
    consume_password_reset_token,
    hash_token,
    issue_password_reset_token,
    verify_password_reset_token,
)

__all__ = [
    "IssuedToken",
    "JWTIssuer",
    "LoginResult",
    "authenticate_password",
    "consume_password_reset_token",
    "decode_access_token",
    "hash_token",
    "issue_access_token",
    "issue_password_reset_token",
    "permissions_for",
    "verify_password_cross_store",
    "verify_password_reset_token",
]
