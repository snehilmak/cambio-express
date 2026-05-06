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
from api.Modules.Auth.Services.password_change import (
    MIN_PASSWORD_LENGTH,
    admin_set_password,
    change_password,
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
from api.Modules.Auth.Services.totp import (
    RECOVERY_CODES_PER_USER,
    TOTP_VALID_WINDOW,
    consume_recovery_code,
    format_recovery_code,
    generate_recovery_codes,
    hash_recovery_code,
    is_enrolled,
    needs_totp,
    verify_totp_token,
)

__all__ = [
    "DEFAULT_GRACE_DAYS",
    "DEFAULT_TRIAL_DAYS",
    "IssuedToken",
    "JWTIssuer",
    "LoginResult",
    "MIN_PASSWORD_LENGTH",
    "RECOVERY_CODES_PER_USER",
    "SignupConflictError",
    "SignupResult",
    "TOTP_VALID_WINDOW",
    "admin_set_password",
    "authenticate_password",
    "change_password",
    "consume_password_reset_token",
    "consume_recovery_code",
    "create_store_and_admin",
    "decode_access_token",
    "format_recovery_code",
    "generate_recovery_codes",
    "hash_recovery_code",
    "hash_token",
    "is_enrolled",
    "issue_access_token",
    "issue_password_reset_token",
    "needs_totp",
    "permissions_for",
    "verify_password_cross_store",
    "verify_password_reset_token",
    "verify_totp_token",
]
