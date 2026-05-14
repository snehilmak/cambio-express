"""Test-only re-export module for the legacy ``app.py`` surface.

PR #550 (Flask-removal-5) deleted ``app.py``. Production no longer
needs the Flask app object — ``asgi.py`` owns the entrypoint and
runs FastAPI directly. ~130 test files still import ``db``,
``find_or_upsert_customer``, ``purge_expired_stores``, and the
model classes from ``app``; this module re-exports them so a sed
rewrite kept those imports working.

The historical ``flask_app`` / ``app_context()`` pattern was
swept in PR #553. Tests now use ``db_session()`` — a clearly-named
context manager that does the same thing the stub's
``app_context()`` did (yield, then drop the scoped session on
exit).

Nothing here belongs in production. Future work: rewrite the test
suite to call ``SessionLocal()`` directly and delete this module.
"""
from __future__ import annotations

import contextlib

from tests._db_shim import db


@contextlib.contextmanager
def db_session():
    """Scope a block of ORM work and drop the scoped session on
    exit so a subsequent read sees fresh DB state.

    Replaces the historical ``with flask_app.app_context():``
    idiom — same semantics, name that doesn't lie about Flask's
    involvement (which is none).
    """
    try:
        yield
    finally:
        db.session.remove()


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
