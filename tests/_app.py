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

PR #554 consolidated the previously-separate ``tests/_db_shim.py``
and ``tests/_models.py`` here so the test-only compatibility shim
is one self-contained file. Nothing here belongs in production.
Future work: rewrite the test suite to call ``SessionLocal()``
directly and delete this module.
"""
from __future__ import annotations

import contextlib

import sqlalchemy as _sa
from sqlalchemy.orm import (
    relationship as _sa_relationship,
    scoped_session as _scoped_session_cls,
    sessionmaker as _sessionmaker,
)

from api.Core.Database import Base
from api.Core.Database.session import _get_engine


# ── ``db`` shim — Flask-SQLAlchemy-shaped facade ────────────────
#
# Never required Flask despite its historical name; the original
# ``api/Flask/Database.py`` was framework-free except for a
# ``teardown_appcontext`` hook that ``db_session`` below replicates.
#
# Public surface (matches what ~130 tests already use):
#   - ``db.Model`` — SQLAlchemy declarative ``Base``.
#   - ``db.session`` — thread-local scoped session.
#   - ``db.engine`` — the same engine FastAPI uses.
#   - ``db.create_all`` / ``db.drop_all`` — schema reset between tests.
#   - ``db.relationship`` — re-export for legacy model files.
#   - ``db.<sqlalchemy-name>`` — transparent ``Column``, ``Integer``,
#     ``func``, etc.

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


# ── Scope helper ────────────────────────────────────────────────


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


# ── Operator helpers (from the legacy ``app.py``) ───────────────


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


# ── Aggregate model re-exports ──────────────────────────────────
#
# Legacy callers ``from tests._app import Store, User, …`` keep
# working. New code imports from ``api.Modules.<domain>.Models``
# directly.
from api.Modules.Announcements.Models import (  # noqa: E402, F401
    Announcement, PushSubscription,
)
from api.Modules.Audit.Models import (  # noqa: E402, F401
    OperatorAuditLog, SuperadminAuditLog, TransferAudit,
)
from api.Modules.Auth.Models import (  # noqa: E402, F401
    LoginEvent, Passkey, PasswordResetToken, RecoveryCode,
)
from api.Modules.BankSync.Models import (  # noqa: E402, F401
    BankRule, BankTransaction, StripeBankAccount,
)
from api.Modules.Batches.Models import ACHBatch  # noqa: E402, F401
from api.Modules.Billing.Models import (  # noqa: E402, F401
    DiscountCode, FeatureFlag, ReferralCode, ReferralRedemption,
    StoreFeatureOverride,
)
from api.Modules.Customers.Models import Customer  # noqa: E402, F401
from api.Modules.DailyBook.Models import (  # noqa: E402, F401
    CheckDeposit, DailyDrop, DailyLineItem, DailyReport,
    MoneyTransferSummary,
)
from api.Modules.Monthly.Models import MonthlyFinancial  # noqa: E402, F401
from api.Modules.ReturnChecks.Models import (  # noqa: E402, F401
    RETURN_CHECK_BOOKED, RETURN_CHECK_STATUSES,
    ReturnCheck, ReturnCheckPayment,
)
from api.Modules.Tenancy.Models import (  # noqa: E402, F401
    OwnerConnectCode, Store, StoreEmployee, StoreOwnerLink, User,
)
from api.Modules.Transfers.Models import Transfer  # noqa: E402, F401
from api.Modules.TVDisplay.Models import (  # noqa: E402, F401
    TVBankCatalog, TVCatalogLogo, TVCompanyCatalog, TVDisplay,
    TVDisplayCountry, TVDisplayPayoutBank, TVDisplayRate,
    TVPairing, TVPendingPair,
)
from api.Modules.Webhooks.Models import (  # noqa: E402, F401
    EmailEvent, WebhookEvent,
)
