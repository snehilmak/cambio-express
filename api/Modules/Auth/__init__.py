"""Auth module — module 5 of 6 in the strangler-fig migration.

Owns login, logout, signup, password reset, 2FA (TOTP), passkeys,
recovery codes, and the JWT issuance endpoint that the React frontend
will call once the backend cuts over.

Layered architecture:
    Controller → Service → Repository → Model

This PR (PR 18) ships the Models + User Repository scaffolding.
Subsequent PRs add the password-flow Service, the JWT issuer, the
TOTP / passkey services, and finally the Flask flip.

Per ADR: JWT-claims auth model — full permission set embedded as
claims, 30-min access token TTL, refresh token + jti blacklist.
"""
