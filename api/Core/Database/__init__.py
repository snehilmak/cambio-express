"""Shared SQLAlchemy session lifecycle for FastAPI modules.

The ``Engine`` is created on first import; ``Session`` instances
are minted from it per-request via the ``get_db()`` FastAPI
dependency. ``Base`` is the declarative base every model in
``api/Modules/*/Models`` inherits from.
"""
from .session import Base, SessionLocal, engine, get_db

__all__ = ["Base", "SessionLocal", "engine", "get_db"]
