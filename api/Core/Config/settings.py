"""Application settings — single Pydantic model, env-driven.

The legacy Flask app reads env vars ad-hoc throughout `app.py`. The
new FastAPI app reads them all here, in one place, with type
validation. As modules migrate, each new piece of business logic
should pull config from `settings`, not from `os.environ`.

The strangler-fig migration uses the same env vars Flask uses, so
both apps see identical config in dev / staging / prod (no parallel
secret rotation needed during the rewrite).
"""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration for the API.

    Env-name conventions follow the existing Flask app for transitive
    compatibility — DATABASE_URL, SECRET_KEY, STRIPE_SECRET_KEY etc.
    """

    # ── Database ───────────────────────────────────────────────
    database_url: str = Field(
        default="sqlite:///:memory:",
        description=(
            "SQLAlchemy URL. Postgres in prod (per ADR), SQLite for "
            "tests (matches the existing test conftest)."
        ),
    )

    # ── Web framework ──────────────────────────────────────────
    secret_key: str = Field(
        default="dev-secret-key-do-not-use-in-prod",
        description="Used for Flask session cookies. Falls back as JWT "
        "secret when AUTH_JWT_SECRET is unset.",
    )

    # ── Auth (JWT issuance) ────────────────────────────────────
    auth_jwt_secret: str = Field(
        default="",
        description=(
            "HS256 signing secret for the FastAPI JWT issuer. Empty "
            "falls back to SECRET_KEY for dev convenience; production "
            "should set this explicitly so JWT secret rotation is "
            "independent of the Flask cookie secret."
        ),
    )

    # ── Stripe (carried over from the Flask config) ────────────
    stripe_secret_key: str = Field(default="")
    stripe_basic_price_id: str = Field(default="")
    stripe_pro_price_id: str = Field(default="")
    stripe_webhook_secret: str = Field(default="")

    # ── Tenancy ────────────────────────────────────────────────
    # The new backend is single-tenant per the ADR. This flag stays
    # at False going forward; multi-tenant code paths get dropped at
    # cleanup PR. Keeping the toggle until then so legacy fixtures
    # continue to work during the strangler-fig migration.
    multi_tenant: bool = Field(
        default=False,
        description=(
            "Single-tenant per deployment per ADR §3. Multi-tenant "
            "scaffolding survives in app.py (Flask) until cleanup."
        ),
    )

    # ── Server ─────────────────────────────────────────────────
    api_prefix: str = Field(
        default="/api/v2",
        description=(
            "All FastAPI routes mount under this prefix. Lets the "
            "Flask monolith continue to own / and the rest of the "
            "URL space until module migration completes."
        ),
    )

    # ── Observability ──────────────────────────────────────────
    sentry_dsn: str = Field(
        default="",
        description=(
            "Sentry project DSN. Empty (default) disables Sentry "
            "entirely — the SDK is installed but never initialised, "
            "so CI and local dev pay nothing. Set in production to "
            "start capturing unhandled exceptions, performance "
            "traces, and Flask/FastAPI/SQLAlchemy breadcrumbs."
        ),
    )
    environment: str = Field(
        default="development",
        description=(
            "Free-form environment tag attached to every Sentry "
            "event + structured-log entry: `development`, "
            "`staging`, `production`. Render sets this via the "
            "ENVIRONMENT env var."
        ),
    )
    log_format: str = Field(
        default="console",
        description=(
            "Output format for the structured logger: `json` for "
            "production (one log line = one JSON object, ready for "
            "log aggregation) or `console` for human-readable dev "
            "output. Defaults to console so a developer running "
            "`python app.py` gets readable output without config."
        ),
    )
    sentry_traces_sample_rate: float = Field(
        default=0.0,
        description=(
            "Fraction of requests captured as Sentry performance "
            "traces (0.0–1.0). Default 0 — error capture only. Set "
            "to 0.05 in prod to capture 5%% of traffic without "
            "blowing the Sentry quota."
        ),
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """FastAPI dependency-injection-friendly accessor.

    Use this when injecting via `Depends(get_settings)` so tests can
    override it cleanly.
    """
    return Settings()


# Module-level singleton for direct imports.
settings = get_settings()
