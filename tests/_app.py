"""Test-only re-export module for the legacy ``app.py`` surface.

PR #550 (Flask-removal-5) deleted ``app.py``. Production no longer
needs the Flask app object — ``asgi.py`` owns the entrypoint and
runs FastAPI directly. But ~130 test files import ``db``,
``flask_app``, ``find_or_upsert_customer``, and
``purge_expired_stores`` from ``app``. Rather than mechanically
rewrite every site, this module re-exports those names from their
new homes.

The ``flask_app`` here is a tiny stub: it answers ``.app_context()``
as a no-op context manager and exposes a writable ``.config`` dict
for the half-dozen tests that flip ``TESTING`` or read keys back.
The ``db`` shim is the existing framework-agnostic scoped-session
binding from ``api.Flask.Database`` — it never required Flask, just
historical convention.

Nothing here belongs in production. Future work: rewrite the test
suite to call ``SessionLocal()`` directly and delete this module.
"""
from __future__ import annotations

import contextlib
import logging

from tests._db_shim import db
from tests._app import db


class _FlaskAppStub:
    """Drop-in stand-in for ``flask_app`` used by ~130 tests.

    The only things tests historically did with this object are
    ``flask_app.app_context()`` (to scope ``db.session`` access)
    and ``flask_app.config[...]`` (boring config flags). The new
    ``app_context()`` removes the scoped session on exit so the
    next read inside a fresh ``with`` block doesn't return a
    stale, cached row — mirroring the ``teardown_appcontext`` hook
    Flask-SQLAlchemy used to register on the real app.
    """

    config: dict = {}
    root_path: str = ""
    logger: logging.Logger = logging.getLogger("dinerobook")

    @contextlib.contextmanager
    def app_context(self):
        try:
            yield
        finally:
            # Drop the thread-local scoped session so the next
            # ``with`` block re-reads from the DB. Without this,
            # tests that PATCH then re-read get the cached row.
            db.session.remove()


flask_app = _FlaskAppStub()
flask_app.config["TESTING"] = True

# Alias for the historical ``from app import app as flask_app``
# pattern. The sed in PR #550 rewrote ``from app import`` → ``from
# tests._app import`` but kept the trailing ``as flask_app``
# rename, so the symbol the import wants is ``app``.
app = flask_app


def find_or_upsert_customer(
    store_id, full_name, phone_country, phone_number,
    address="", dob=None, customer_id=None,
):
    """Find-or-create a Customer row scoped to the owner umbrella
    (CLAUDE.md invariant #5). Last write wins on PII fields."""
    from api.Modules.Customers.Services import upsert as _upsert
    return _upsert(
        db.session, store_id, full_name, phone_country, phone_number,
        address=address, dob=dob, customer_id=customer_id,
    )


def purge_expired_stores():
    """Daily cron entrypoint (CLAUDE.md invariant #4 = 180 days)."""
    from api.Core.Database import SessionLocal
    from api.Modules.Billing.Services import purge_expired_stores as _svc
    with SessionLocal() as s:
        return _svc(s)


# Re-export the model classes for any test still doing
# ``from tests._app import Store, User``. New code imports from
# ``api.Modules.<domain>.Models`` directly.
from tests._models import *  # noqa: E402, F401, F403
