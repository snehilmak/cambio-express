"""Shared SQLAlchemy session lifecycle for FastAPI modules.

During the strangler-fig migration, the new FastAPI modules and the
legacy Flask app run in the same Python process and read/write the
same Postgres database. To keep everyone honest, both apps share a
single SQLAlchemy `Engine`:

  - Flask creates the engine first (via Flask-SQLAlchemy on app
    init).
  - FastAPI reuses that engine here. New `Session` instances are
    minted from it for FastAPI requests, scoped per-request via the
    `get_db()` dependency.

After the cleanup PR removes Flask, this module owns the engine
outright and `app.py` no longer exists.
"""
from .session import Base, SessionLocal, engine, get_db

__all__ = ["Base", "SessionLocal", "engine", "get_db"]
