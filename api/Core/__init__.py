"""Cross-cutting infrastructure used by every module.

Anything in here is allowed to be imported by any module's layer.
Modules must NOT import from each other's internals — only Core
and their own files.

Subpackages:
    Config/     — settings via Pydantic BaseSettings (env vars)
    Database/   — SQLAlchemy engine + session lifecycle
    Providers/  — adapters for external services (Stripe, Resend,
                  S3, etc.). Each provider exposes a small interface
                  so services depend on the interface, not the SDK.
"""
