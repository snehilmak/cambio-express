"""Test-only ``db`` shim — a Flask-SQLAlchemy-shaped facade over
the production SQLAlchemy engine.

Never required Flask despite its historical name; the original
``api/Flask/Database.py`` was framework-free except for a
``teardown_appcontext`` hook that tests/_app.py now replicates in
its ``app_context()`` stub. Moved to ``tests/`` in PR #550 so the
``api/`` tree contains zero Flask-flavoured code.

Public surface (matches what ~130 tests already use):
  - ``db.Model`` — SQLAlchemy declarative ``Base``.
  - ``db.session`` — thread-local scoped session.
  - ``db.engine`` — the same engine FastAPI uses.
  - ``db.create_all`` / ``db.drop_all`` — schema reset between tests.
  - ``db.relationship`` — re-export for legacy model files.
  - ``db.<sqlalchemy-name>`` — transparent ``Column``, ``Integer``,
    ``func``, etc.

``Model.query.filter_by(...)`` keeps working via the scoped-session
``query_property``. CLAUDE.md invariant #11 says new code uses
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
