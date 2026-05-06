"""SQLAlchemy engine + session factory.

The engine is **lazily resolved** via `_get_engine()` so the legacy
Flask app can initialize it first. Two ways the engine gets set:

1. The legacy Flask app is imported (typical case in this repo).
   Flask-SQLAlchemy creates the engine; this module reuses it.
2. The FastAPI app is run standalone (post-cleanup, after Flask is
   removed). We create the engine ourselves from settings.

Either way, `SessionLocal()` returns a brand-new SQLAlchemy `Session`
bound to the same engine, which is what FastAPI's request-scoped
dependency injection wants.
"""
from typing import Generator

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from api.Core.Config import settings


# Lazily-built engine. None until first `_get_engine()` call.
_engine: Engine | None = None


def _build_engine_from_settings() -> Engine:
    """Standalone engine — used when Flask isn't there to provide one.
    Postgres in prod, SQLite for tests."""
    from sqlalchemy import create_engine

    connect_args: dict = {}
    if settings.database_url.startswith("sqlite"):
        # SQLite in tests typically uses :memory: — needs check_same_thread
        # off so multiple threads (Flask request thread + FastAPI request
        # thread + test driver thread) can share the in-memory DB.
        connect_args["check_same_thread"] = False
    return create_engine(
        settings.database_url,
        future=True,
        connect_args=connect_args,
    )


def _get_engine() -> Engine:
    """Return the shared SQLAlchemy engine, building it on first call.

    Tries to reuse the legacy Flask-SQLAlchemy engine first so both
    apps end up bound to the same connection pool / DB session.
    Falls back to a fresh engine built from `settings.database_url`
    when Flask isn't available (e.g. running FastAPI standalone in
    a future post-cleanup test).
    """
    global _engine
    if _engine is not None:
        return _engine

    # Path 1 — strangler-fig phase: legacy Flask owns the engine.
    try:
        from app import db as legacy_db  # noqa: WPS433 (intentional legacy hop)
        from app import app as legacy_flask_app
        with legacy_flask_app.app_context():
            _engine = legacy_db.engine
            return _engine
    except Exception:
        # Either app.py is gone (post-cleanup) or it failed to import
        # in this context — fall through to standalone path.
        pass

    # Path 2 — standalone: build our own engine.
    _engine = _build_engine_from_settings()
    return _engine


# Public engine accessor (re-evaluates lazily on each access).
class _EngineProxy:
    """Tiny proxy so `engine` looks like a module-level value but
    defers resolution until first attribute access. Avoids forcing
    the legacy Flask import at module-import time, which would break
    test collection if the Flask app fails to construct."""

    def __getattr__(self, name):
        return getattr(_get_engine(), name)

    def __repr__(self):
        return repr(_get_engine())


engine = _EngineProxy()


# Session factory — each call to SessionLocal() yields a fresh session.
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=_get_engine,  # callable that returns the Engine when needed
    future=True,
)


# Declarative base for new models defined in api/Modules/<X>/Models/.
# Legacy models in app.py keep using their own Flask-SQLAlchemy `db.Model`.
# This is intentional during the migration — model migration happens
# slice-by-slice, alongside the routes that own them.
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI request-scoped dependency.

    Usage in a controller:

        @router.get("/whatever")
        def whatever(db: Session = Depends(get_db)):
            ...

    Opens a new session, yields it for the request body, closes
    when the request finishes. No commit-on-success here — services
    are responsible for their own transaction semantics.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
