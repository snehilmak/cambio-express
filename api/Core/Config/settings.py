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
        description="Used for JWT signing and session cookies.",
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
