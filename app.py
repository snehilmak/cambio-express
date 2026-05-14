import logging, os, smtplib, sys

import stripe
from flask import Flask, session

# When run via `python app.py` the module is __main__; submodules
# that ``from app import …`` would re-execute it as a fresh `app`
# module. Aliasing prevents the circular re-entry.
if __name__ == "__main__" and "app" not in sys.modules:
    sys.modules["app"] = sys.modules[__name__]

logging.basicConfig(level=logging.INFO)

# Observability + Flask app
from api.Core.Observability import (  # noqa: E402
    init_logging, init_sentry, install_request_id,
)
init_logging()
init_sentry()

app = Flask(__name__)
install_request_id(app)

from api.Flask.Config import (  # noqa: E402
    install_csrf as _install_csrf,
    install_secret_key as _install_secret_key,
    install_session as _install_session,
    warn_default_seed_passwords as _warn_seed_pw,
)
_install_secret_key(app)
_warn_seed_pw(app)

# spa_cutover registers the before_request hook that 301s legacy
# GET URLs (/dashboard, /transfers, …) to /app/*.
from blueprints import spa_cutover as _bp_spa_cutover  # noqa: E402
_bp_spa_cutover.register(app)


from api.Flask.Templating import (  # noqa: E402
    country_flag_html, install as _install_templating,
)
STATIC_VERSION = _install_templating(app)

_is_https_prod = _install_session(app)

from api.Flask.Database import install as _install_db  # noqa: E402
db = _install_db(app)


stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")

# ── Rate limiting (CLAUDE.md invariant #15) ─────────────────
from api.Flask.RateLimit import install as _install_rate_limiter
limiter = _install_rate_limiter(app)

# ── CSRF protection (CLAUDE.md invariant #16) ───────────────
csrf = _install_csrf(app, is_https_prod=_is_https_prod)


# ── Models live in api/Modules/<domain>/Models ──────────────────
# Re-exported here so legacy ``from app import Store, User, …``
# call sites keep working. New code imports from the per-domain
# Models package directly.
from api.Flask.Models import *  # noqa: E402, F401, F403
from api.Modules.Tenancy.Models import Store, User  # noqa: E402 (named for current_user/current_store)


# Cookie-session helpers (None for SPA users; they auth via JWT).
def current_user():  return db.session.get(User,  session["user_id"])  if "user_id"  in session else None
def current_store(): return db.session.get(Store, session["store_id"]) if session.get("store_id") else None

# ── Add-ons catalog ──────────────────────────────────────────
ADDONS_CATALOG = {
    "tv_display": {
        "name": "TV Display & Live Rates",
        "price_cents": 500,
        "price_label": "$5 / month",
        "tagline": "Show your money transfer rates on the TV behind your counter.",
        "description": (
            "A live rate board for your shop — manage country sections, payout "
            "banks, and the MT companies you offer in one place; the TV refreshes "
            "automatically when you change a rate. Each store gets a tokenized "
            "URL you point any TV browser, Chromecast, smart-TV, or our upcoming "
            "Google TV / Fire TV apps at."
        ),
        "status": "active",
    },
}

# Add-on / plan / retention helpers re-exported for legacy callers
# (context processors, tests) that ``from app import …``.
from api.Modules.Billing.Services import (  # noqa: E402
    data_retention_days_left,
    store_addon_keys,
    store_has_paid_plan,
)

DATA_RETENTION_DAYS = 180  # 6 months

from api.Flask.ContextProcessors import register as _register_context_processors  # noqa: E402
_register_context_processors(app, db, current_user, current_store)


# Self-service signup gate.
SIGNUP_CLOSED = os.environ.get("SIGNUP_CLOSED", "0") == "1"

# Cookie name used by PublicRoutes' /login/<slug> bounce path.
LAST_STORE_SLUG_COOKIE = "ds_last_store"

# Push notification VAPID config (re-exported for tests).
from api.Modules.Notifications.Services import push as _push_svc  # noqa: E402
VAPID_PUBLIC_KEY  = _push_svc.VAPID_PUBLIC_KEY
VAPID_PRIVATE_KEY = _push_svc.VAPID_PRIVATE_KEY
VAPID_SUBJECT     = _push_svc.VAPID_SUBJECT


# Email sending shim — Auth's password-reset path + tests still import it.
from api.Modules.Notifications.Services import smtp as _smtp_svc  # noqa: E402


def _send_email(to_addr, subject, body, html=None):
    return _smtp_svc.send_email(db.session, to_addr, subject, body, html)


def smtp_health_check():
    return _smtp_svc.health_check(db.session)


# Legacy re-exports for tests.
from api.Modules.Transfers.Services import (  # noqa: E402
    TRANSFER_AUDIT_FIELDS as _TRANSFER_AUDIT_FIELDS,
)
from api.Modules.DailyBook.Services import (  # noqa: E402
    LINE_ITEM_KINDS as _LINE_ITEM_KINDS,
    kind_or_404 as _line_item_kind_or_404,
)
from api.Modules.Billing.Services import (  # noqa: E402
    STORE_FK_OVERRIDES as _STORE_FK_OVERRIDES,
    STORE_OWNED_MODELS as _STORE_OWNED_MODELS,
)


def purge_expired_stores():
    """Daily cron entrypoint (CLAUDE.md invariant #4 = 180 days)."""
    from api.Modules.Billing.Services import purge_expired_stores as _svc
    from api.Core.Database import SessionLocal
    with SessionLocal() as s:
        return _svc(s)


def find_or_upsert_customer(store_id, full_name, phone_country, phone_number,
                             address="", dob=None, customer_id=None):
    """Find-or-create a Customer row scoped to the owner umbrella
    (CLAUDE.md invariant #5). Last write wins on PII fields."""
    from api.Modules.Customers.Services import upsert as _customers_upsert
    return _customers_upsert(
        db.session, store_id, full_name, phone_country, phone_number,
        address=address, dob=dob, customer_id=customer_id,
    )


# Wire the rest of the app: CLI commands, report routes, error
# handlers, schema init, FastAPI mount.
from api.Modules.Reports.Routes import register as _register_report_routes  # noqa: E402
_register_report_routes(app, db, current_user)

from api.Flask.Cli import register as _register_cli_commands  # noqa: E402
_register_cli_commands(app, db)

from blueprints import errors as _bp_errors  # noqa: E402
_bp_errors.register(app, current_user)

from api.Flask.Init import init_db as _init_db, mount_fastapi as _mount_fastapi  # noqa: E402


def init_db():
    """Boot-time DB init. Idempotent on every boot."""
    _init_db(app, db)


# DINEROBOOK_SKIP_INIT_DB is set by alembic/env.py (imports app
# only to harvest db.metadata).
if not os.environ.get("DINEROBOOK_SKIP_INIT_DB"):
    init_db()

# Mount /api/v2 + /app onto Flask's wsgi_app for test_client.
# Production routes via asgi.py and bypasses this entirely.
_mount_fastapi(app)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 DineroBook → http://0.0.0.0:{port}  (uvicorn/ASGI)")
    uvicorn.run(
        "asgi:asgi_app",
        host="0.0.0.0",
        port=port,
        reload=bool(os.environ.get("DEV_RELOAD")),
        log_level="info",
    )
