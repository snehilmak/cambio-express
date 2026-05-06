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
from api.Modules.Auth.Services.signup import (
    DEFAULT_GRACE_DAYS,
    DEFAULT_TRIAL_DAYS,
    SignupConflictError,
    SignupResult,
    create_store_and_admin,
)

__all__ = [
    "DEFAULT_GRACE_DAYS",
    "DEFAULT_TRIAL_DAYS",
    "IssuedToken",
    "JWTIssuer",
    "LoginResult",
    "SignupConflictError",
    "SignupResult",
    "authenticate_password",
    "consume_password_reset_token",
    "create_store_and_admin",
    "decode_access_token",
    "hash_token",
    "issue_access_token",
    "issue_password_reset_token",
    "permissions_for",
    "verify_password_cross_store",
    "verify_password_reset_token",
]
