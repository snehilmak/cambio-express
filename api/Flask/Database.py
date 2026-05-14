"""Flask-SQLAlchemy `db` shim. CLAUDE.md invariant #11.

Drop-in replacement for the slice of Flask-SQLAlchemy the legacy
Flask code relies on (``db.Model``, ``db.session``, ``db.engine``,
``db.create_all`` / ``drop_all``, ``db.relationship``, transparent
re-exports of ``Column``, ``Integer``, ``func`` etc).

Legacy ``Model.query`` keeps working via the scoped-session query
property — CLAUDE.md invariant #11 says new code uses
``db.session.query(Model)``.
"""
from __future__ import annotations

import sqlalchemy as _sa
from sqlalchemy.orm import (
    relationship as _sa_relationship,
    scoped_session as _scoped_session_cls,
    sessionmaker as _sessionmaker,
)

from api.Core.Database import Base
from api.Core.Database.session import _get_engine


_engine = _get_engine()
_Session = _sessionmaker(
    autocommit=False, autoflush=False, bind=_engine, future=True,
)
_scoped_session = _scoped_session_cls(_Session)
Base.query = _scoped_session.query_property()


class _DB:
    """Drop-in replacement for the Flask-SQLAlchemy ``db`` object."""

    Model = Base
    metadata = Base.metadata
    engine = _engine
    session = _scoped_session
    relationship = staticmethod(_sa_relationship)

    @staticmethod
    def create_all():
        Base.metadata.create_all(bind=_engine)

    @staticmethod
    def drop_all():
        Base.metadata.drop_all(bind=_engine)

    def __getattr__(self, name):
        return getattr(_sa, name)


db = _DB()


def install(app) -> _DB:
    """Wire the teardown hook + return the ``db`` shim."""
    @app.teardown_appcontext
    def _remove_db_session(exc):  # noqa: ARG001
        _scoped_session.remove()
    return db
