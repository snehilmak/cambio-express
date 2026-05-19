"""SQLAlchemy engine + session factory.

Single source of truth for the engine: built once from
`settings.database_url`. Both the legacy Flask side (via the shim
in `app.py`) and the FastAPI side bind to this same engine, so
in-memory SQLite tests see one consistent connection pool and
every code path mutates the same data.
"""
from typing import Any, Generator

from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from api.Core.Config import settings


_engine: Engine | None = None


def _build_engine_from_settings() -> Engine:
    """Construct the SQLAlchemy engine from settings.

    SQLite ``:memory:`` gets StaticPool so a single connection is
    shared across threads — the test conftest seeds rows on one
    thread and reads them back on the Flask / FastAPI request
    thread. Postgres in prod gets ``pool_pre_ping`` so stale
    connections in the pool are detected before the query fires
    against a dead socket.
    """
    from sqlalchemy import create_engine

    connect_args: dict[str, Any] = {}
    engine_kwargs: dict[str, Any] = {"future": True}

    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    if ":memory:" in settings.database_url:
        from sqlalchemy.pool import StaticPool
        engine_kwargs["poolclass"] = StaticPool
    else:
        engine_kwargs["pool_pre_ping"] = True

    return create_engine(
        settings.database_url,
        connect_args=connect_args,
        **engine_kwargs,
    )


def _get_engine() -> Engine:
    """Return the shared SQLAlchemy engine, building it on first call."""
    global _engine
    if _engine is None:
        _engine = _build_engine_from_settings()
    return _engine


# Public engine accessor (re-evaluates lazily on each access).
class _EngineProxy:
    """Tiny proxy so `engine` looks like a module-level value but
    defers resolution until first attribute access."""

    def __getattr__(self, name: str) -> Any:
        return getattr(_get_engine(), name)

    def __repr__(self) -> str:
        return repr(_get_engine())


engine = _EngineProxy()


# Session factory — each call to SessionLocal() yields a fresh session.
_session_factory: sessionmaker[Session] | None = None


def SessionLocal() -> Session:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=_get_engine(),
            future=True,
        )
    return _session_factory()


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 declarative base.  Switching from the
    1.x ``declarative_base()`` callable gives every ``class
    Foo(Base)`` proper typing (the callable returns ``Any``,
    which trips mypy's ``cannot subclass Any`` on every model).
    Runtime behavior is identical."""
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI request-scoped dependency.

    Opens a new session, yields it for the request body, closes
    when the request finishes. No commit-on-success here — services
    are responsible for their own transaction semantics.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
