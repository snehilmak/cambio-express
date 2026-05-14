from flask import Flask, request, session, Response
from datetime import timedelta
import logging, os, smtplib, sys

# When run via `python app.py` the running module is `__main__`, not
# `app`. Submodules in api/Modules/*/Models/__init__.py do
# `from app import ...` (re-export shim during the strangler-fig
# migration window). Without this aliasing, that import re-executes
# this file as a fresh `app` module and re-enters the Service chain
# circularly. Aliasing `__main__` to `app` makes those re-exports
# resolve against the partial-but-progressing module instead.
if __name__ == "__main__" and "app" not in sys.modules:
    sys.modules["app"] = sys.modules[__name__]
import stripe
# WebAuthn / passkeys. The library ships both verify_* helpers and the
# structs we need to build registration options. Lazy imports inside
# helper bodies would work too, but these are cheap and centralizing
# them here keeps the passkey routes lean.

logging.basicConfig(level=logging.INFO)

# ── Observability bootstrap ──────────────────────────────────────
# Initialise structured logging + Sentry before the Flask app exists
# so the very first Flask import-time log line is already structured
# and any boot-time exception is captured. Both calls are idempotent
# and no-op without configuration (Sentry needs SENTRY_DSN; structlog
# uses the LOG_FORMAT env var, defaulting to console output for dev).
from api.Core.Observability import (  # noqa: E402
    init_logging, init_sentry, install_request_id,
)

init_logging()
init_sentry()

app = Flask(__name__)
install_request_id(app)

# ── SECRET_KEY safety gate ────────────────────────────────────
# Refuse to boot in prod with the public dev-fallback secret —
# session cookies signed with it would be forgeable by anyone
# reading the repo. "Prod" = APP_BASE_URL starts with https://.
_SECRET_KEY_DEV_FALLBACK = "dinerobook-dev-secret-change-in-prod"
_secret_key_env = os.environ.get("SECRET_KEY", "")
app.secret_key = _secret_key_env or _SECRET_KEY_DEV_FALLBACK

if (
    os.environ.get("APP_BASE_URL", "").startswith("https://")
    and app.secret_key == _SECRET_KEY_DEV_FALLBACK
):
    raise RuntimeError(
        "Refusing to boot in prod with the dev-fallback SECRET_KEY. "
        "Set the SECRET_KEY env var in Render → Environment to a "
        "random value (e.g. `python -c 'import secrets; "
        "print(secrets.token_urlsafe(48))'`) and re-deploy. "
        "See docs/architecture/secrets-audit.md for the audit "
        "context."
    )

# Seed-password safety warning — the init_db() seed step uses
# public defaults (super2025! / cambio2025!) if the env vars
# aren't set. Loud structured-log warning so Render Logs picks
# it up. Set both env vars in prod.
_seed_pw_missing = []
if (
    os.environ.get("APP_BASE_URL", "").startswith("https://")
):
    if not os.environ.get("SUPERADMIN_PASSWORD"):
        _seed_pw_missing.append("SUPERADMIN_PASSWORD")
    if not os.environ.get("ADMIN_PASSWORD"):
        _seed_pw_missing.append("ADMIN_PASSWORD")
    if _seed_pw_missing:
        app.logger.critical(
            "Seed password fallback is active in prod for: "
            "%s. The default values (super2025! / cambio2025!) "
            "are public in the repo. Either set the env vars OR "
            "change the password in the UI immediately on first "
            "login. See docs/architecture/secrets-audit.md.",
            ", ".join(_seed_pw_missing),
        )

# spa_cutover registers the before_request hook that 301s legacy
# GET URLs (/dashboard, /transfers, …) to /app/*.
from blueprints import spa_cutover as _bp_spa_cutover  # noqa: E402

_bp_spa_cutover.register(app)


# Cache-bust query string for the shared stylesheet on deploy.
_APP_CSS_PATH = os.path.join(os.path.dirname(__file__), "static", "app.css")
try:
    STATIC_VERSION = str(int(os.path.getmtime(_APP_CSS_PATH)))
except OSError:
    import time as _t
    STATIC_VERSION = str(int(_t.time()))
app.jinja_env.globals["STATIC_VERSION"] = STATIC_VERSION

def _country_flag_emoji(code):
    """ISO-2 → flag emoji. Use country_flag_html() for visual
    rendering — emoji flags show as tofu on Windows."""
    code = (code or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + (ord(c) - ord("A"))) for c in code)
app.jinja_env.globals["_country_flag_emoji"] = _country_flag_emoji

def country_flag_html(code, size="1em"):
    """ISO-2 → flag-icons SVG <span>. MIT-licensed; renders
    uniformly across browsers (unlike emoji flags on Windows)."""
    code = (code or "").strip().lower()
    if len(code) != 2 or not code.isalpha():
        return ""
    style = f"width:{size};height:{size};"
    from markupsafe import Markup
    return Markup(
        f'<span class="fi fi-{code}" style="{style}"></span>'
    )
app.jinja_env.globals["country_flag_html"] = country_flag_html

# Session-cookie hardening. HTTPOnly + SameSite=Lax + Secure (prod
# only — must stay False in dev/CI/sqlite mode or sessions silently
# fail to set over HTTP). Prod = APP_BASE_URL starts with https://.
_app_base_url = os.environ.get("APP_BASE_URL", "")
_is_https_prod = _app_base_url.startswith("https://")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = _is_https_prod
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)

# ── SQLAlchemy `db` shim (Flask-SQLAlchemy retirement) ───────
# Drop-in replacement for the slice of Flask-SQLAlchemy the
# legacy Flask code relies on (``db.Model``, ``db.session``,
# ``db.engine``, ``db.create_all``/``drop_all``, ``db.relationship``,
# transparent re-exports of ``Column``, ``Integer``, ``func`` etc).
# Legacy ``Model.query`` keeps working via the scoped-session
# query property below — CLAUDE.md invariant #11 still says new
# code uses ``db.session.query(Model)``.
import sqlalchemy as _sa  # noqa: E402
from sqlalchemy.orm import (  # noqa: E402
    relationship as _sa_relationship,
    scoped_session as _scoped_session_cls,
    sessionmaker as _sessionmaker,
)

from api.Core.Database import Base  # noqa: E402
from api.Core.Database.session import _get_engine  # noqa: E402

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


@app.teardown_appcontext
def _remove_db_session(exc):  # noqa: ARG001 (Flask passes the exception)
    _scoped_session.remove()


stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")

# ── Rate limiting (BACKLOG D6 + "Before going live") ─────────
# Flask-Limiter on auth + webhook endpoints. Default key is client
# IP. Storage is in-memory by default; prod sets
# RATELIMIT_STORAGE_URI=redis://... in render.yaml so the bucket
# spans workers. Tests set RATELIMIT_ENABLED=0 so they don't get
# 429'd by the seeded admin.
_RATELIMIT_STORAGE = os.environ.get(
    "RATELIMIT_STORAGE_URI", "memory://",
)
_LIMITER_ENABLED = (
    os.environ.get("RATELIMIT_ENABLED", "1") not in ("0", "false", "False")
)

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=[],
    storage_uri=_RATELIMIT_STORAGE,
    strategy="fixed-window",
    enabled=_LIMITER_ENABLED,
    headers_enabled=True,
)


def _apply_rate_limits():
    """Apply rate limits to Blueprint + app endpoints AFTER
    Blueprint registration. See CLAUDE.md "Rate limiting" before
    tightening — integration tests + webhook retry storms share
    these buckets. Loosening is safer than the alternative."""
    # POST-only so a logged-out user hitting the GET form
    # repeatedly doesn't burn the credit they need to actually
    # try a password.
    _auth_burst = limiter.limit(
        "10 per minute; 50 per hour",
        methods=["POST"],
    )

    # Flask Blueprint endpoints — login state machine + 2FA +
    # passkey. The full set lives in blueprints/auth.py.
    for endpoint in (
        "auth.login",
        "auth.login_store",
        "auth.employee_login_redirect",
        "auth.login_totp",
        "auth.login_totp_recover",
        "auth.login_totp_enroll",
        "auth.passkey_login_begin",
        "auth.passkey_login_finish",
        "auth.passkey_register_begin",
        "auth.passkey_register_finish",
    ):
        if endpoint in app.view_functions:
            app.view_functions[endpoint] = _auth_burst(
                app.view_functions[endpoint],
            )


_apply_rate_limits()


# ── CSRF protection ──────────────────────────────────────────
# CLAUDE.md invariant #16. CSRFProtect rejects POST/PUT/PATCH/DELETE
# without a valid csrf_token. FastAPI /api/v2/* uses Bearer JWT (CSRF
# is moot — not attached cross-origin). WTF_CSRF_ENABLED=0 kill-switch
# is used by the test conftest.
from flask_wtf.csrf import CSRFProtect

_CSRF_ENABLED = os.environ.get("WTF_CSRF_ENABLED", "True") not in (
    "0", "false", "False",
)
app.config["WTF_CSRF_ENABLED"] = _CSRF_ENABLED
app.config["WTF_CSRF_TIME_LIMIT"] = 60 * 60 * 24 * 7
app.config["WTF_CSRF_SSL_STRICT"] = _is_https_prod

csrf = CSRFProtect(app)


# ── Models live in api/Modules/<domain>/Models ──────────────────
# Re-exported here so legacy ``from app import Store, User, …``
# call sites keep working. New code imports from the per-domain
# Models package directly.
from api.Flask.Models import *  # noqa: E402, F401, F403
from api.Modules.Tenancy.Models import Store, User  # noqa: E402 (named for current_user/current_store)


# ── Auth ─────────────────────────────────────────────────────
def current_user():  return db.session.get(User,  session["user_id"])  if "user_id"  in session else None
def current_store(): return db.session.get(Store, session["store_id"]) if session.get("store_id") else None

# Routes a trial-expired store can still reach (so the operator can
# pay or sign out without bouncing). Matched against
# `request.endpoint` so Blueprint-namespaced endpoints work too.

# ── Add-ons catalog ──────────────────────────────────────────
# Each add-on has a stable key used in the Store.addons CSV column.
# Add-ons require an active paid subscription (basic or pro) before they
# can be activated. status="coming_soon" disables activation in the UI
# and on the server until the underlying integration ships.
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

# Add-on / plan / retention helpers live in
# ``api.Modules.Billing.Services``. Re-exported here for legacy
# callers (admin referrals service, context processors, tests)
# that ``from app import …``.
from api.Modules.Billing.Services import (
    data_retention_days_left,
    store_addon_keys,
    store_has_paid_plan,
)

# ── Cancellation & data retention ────────────────────────────
DATA_RETENTION_DAYS = 180  # 6 months

from api.Flask.ContextProcessors import register as _register_context_processors  # noqa: E402
_register_context_processors(app, db, current_user, current_store)


# Self-service signup gate. With SIGNUP_CLOSED=1 the /signup
# pages render a "Signups closed" notice; the FastAPI signup
# endpoints return 503; and the marketing landing's "Get Started"
# CTA is suppressed. Existing customers still log in.
SIGNUP_CLOSED = os.environ.get("SIGNUP_CLOSED", "0") == "1"


# ── Push notifications ───────────────────────────────────────
# VAPID_* re-exported for tests/Modules/Notifications/test_push_service.
from api.Modules.Notifications.Services import push as _push_svc

VAPID_PUBLIC_KEY  = _push_svc.VAPID_PUBLIC_KEY
VAPID_PRIVATE_KEY = _push_svc.VAPID_PRIVATE_KEY
VAPID_SUBJECT     = _push_svc.VAPID_SUBJECT


# Cookie name used by PublicRoutes' /login/<slug> bounce path.
LAST_STORE_SLUG_COOKIE = "ds_last_store"


# ── Email sending shim ───────────────────────────────────────
# Used by Auth's password-reset path and a couple of tests.
from api.Modules.Notifications.Services import smtp as _smtp_svc


def _send_email(to_addr, subject, body, html=None):
    return _smtp_svc.send_email(db.session, to_addr, subject, body, html)


def smtp_health_check():
    """Return a dict describing email-delivery state. Single
    source of truth lives in
    `api.Modules.Notifications.Services.smtp_health_check`
    (PR 82)."""
    return _smtp_svc.health_check(db.session)

# ── Owner-side helpers ──────────────────────────────────────────
from api.Modules.Owners.Services import owner_store_ids as _svc_owner_store_ids




# ── Report Center ────────────────────────────────────────────
from api.Modules.Reports.Services.categories import resolved_categories as _resolved_report_categories


from api.Modules.Reports.Routes import register as _register_report_routes
_register_report_routes(app, db, current_user)


# ── Customers (per-store directory) ──────────────────────────
# PHONE_COUNTRY_CODES re-exported for the transfer-form context.
from api.Modules.Customers.Services import PHONE_COUNTRY_CODES

def find_or_upsert_customer(store_id, full_name, phone_country, phone_number,
                             address="", dob=None, customer_id=None):
    """Find-or-create a Customer row scoped to the owner umbrella
    (see CLAUDE.md invariant #5). Last write wins on PII fields."""
    from api.Modules.Customers.Services import upsert as _customers_upsert
    return _customers_upsert(
        db.session, store_id, full_name, phone_country, phone_number,
        address=address, dob=dob, customer_id=customer_id,
    )

# Legacy re-exports for tests / app.py-internal use.
from api.Modules.Transfers.Services import (
    TRANSFER_AUDIT_FIELDS as _TRANSFER_AUDIT_FIELDS,
)
from api.Modules.DailyBook.Services import (
    LINE_ITEM_KINDS as _LINE_ITEM_KINDS,
    kind_or_404 as _line_item_kind_or_404,
)


# ── Resend webhook (delivery events) ─────────────────────────
# Svix-signed webhook (svix-id/svix-timestamp/svix-signature headers,
# HMAC-SHA256 over "{id}.{timestamp}.{body}" with whsec_... secret).
# On hard-bounce + complained we stamp User.email_bounced_at so
# _send_email skips the address; complained also turns off every
# notify_* toggle.

# ── Operator CLI commands ────────────────────────────────────
# Re-exports for legacy callers; canonical home is
# api.Modules.Billing.Services.retention.
from api.Modules.Billing.Services import (
    STORE_FK_OVERRIDES as _STORE_FK_OVERRIDES,
    STORE_OWNED_MODELS as _STORE_OWNED_MODELS,
)


def purge_expired_stores():
    """Hard-delete inactive stores past their retention window
    (CLAUDE.md invariant #4 = 180 days). Used by the daily cron."""
    from api.Modules.Billing.Services import purge_expired_stores as _svc
    from api.Core.Database import SessionLocal
    with SessionLocal() as s:
        return _svc(s)


from api.Flask.Cli import register as _register_cli_commands  # noqa: E402
_register_cli_commands(app, db)


from blueprints import errors as _bp_errors  # noqa: E402
_bp_errors.register(app, current_user)


from api.Flask.Init import init_db as _init_db, mount_fastapi as _mount_fastapi  # noqa: E402

def init_db():
    """Boot-time DB init. Idempotent on every boot."""
    _init_db(app, db)

# DINEROBOOK_SKIP_INIT_DB is set by alembic/env.py (it imports app
# only to harvest db.metadata).
if not os.environ.get("DINEROBOOK_SKIP_INIT_DB"):
    init_db()

# Mount /api/v2 (FastAPI) + /app (Starlette SPA) onto Flask's
# wsgi_app so the test_client can reach them. Production routes
# via asgi.py and bypasses this entirely.
_mount_fastapi(app)


if __name__=="__main__":
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
