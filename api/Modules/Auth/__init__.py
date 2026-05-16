"""Auth module.

Owns login, logout, signup, password reset, 2FA (TOTP), passkeys,
recovery codes, and the JWT issuance endpoint the React SPA calls.

Layered architecture:
    Controller → Service → Repository → Model

Per ADR: JWT-claims auth model — full permission set embedded as
claims, 30-min access token TTL, refresh token + jti blacklist.
"""
