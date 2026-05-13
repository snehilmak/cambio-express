from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, abort, make_response, Response
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
from functools import wraps
from calendar import monthrange, month_name
import requests, base64, os, logging, re, secrets, string, hashlib, hmac, smtplib, json, csv, io, zipfile, sys
from email.message import EmailMessage

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
import click
import pyotp
import qrcode
import qrcode.image.svg
from slugify import slugify
# WebAuthn / passkeys. The library ships both verify_* helpers and the
# structs we need to build registration options. Lazy imports inside
# helper bodies would work too, but these are cheap and centralizing
# them here keeps the passkey routes lean.
from webauthn import (
    generate_registration_options, verify_registration_response,
    generate_authentication_options, verify_authentication_response,
    options_to_json, base64url_to_bytes,
)
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria, ResidentKeyRequirement,
    UserVerificationRequirement, PublicKeyCredentialDescriptor,
)
from sqlalchemy import case

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
#
# Flask's session cookie is signed with `app.secret_key`. If a
# prod deploy boots with the dev fallback value below, anyone
# who reads the value out of the public Git history can forge
# session cookies and impersonate any user — including
# superadmin. We REFUSE to start in that state.
#
# "Prod" is detected by APP_BASE_URL starting with `https://`
# (same gate the session-cookie hardening + SMTP / Stripe URL
# builders use). Local dev and CI run over plain HTTP and keep
# the dev fallback so the test suite can boot without ceremony.
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

# Seed-password safety warning. The init_db() seed step (way at
# the bottom of this file) hardcodes `super2025!` / `cambio2025!`
# for the first-boot users when SUPERADMIN_PASSWORD /
# ADMIN_PASSWORD aren't set. Once an operator changes the
# password in the UI those defaults become irrelevant, but a
# fresh-deploy admin reading this from the docs is the most
# obvious takeover path. Loud structured-log warning so
# Sentry / Render → Logs picks it up.
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

# Blueprints — sections that have been peeled off into
# ``blueprints/`` per BACKLOG D2. Registration happens here, right
# after the Flask app exists, so a Blueprint route lookup behaves
# identically to the original @app.route decorator.
from blueprints import spa_cutover as _bp_spa_cutover  # noqa: E402

# Public + PWA + kiosk surfaces (landing redirect, /sw.js, /offline,
# TV display + pair-code API) now run on Starlette via
# ``api.PublicRoutes.public_app`` — see ``asgi.py``'s dispatcher.
# The Flask side keeps the spa_cutover hook for legacy GET URL
# redirects (/dashboard, /transfers, …) until those routes also
# migrate.

# spa_cutover.register() installs the always-on before_request hook
# that 301s legacy GET URLs (/dashboard, /transfers, …) to /app/*.
_bp_spa_cutover.register(app)


# CSRF exemptions live below, after `csrf = CSRFProtect(app)` is
# created (see "CSRF protection" block).

# Cache-bust query string for the shared stylesheet (and any other static
# asset we want to force-refresh on deploy). Computed once at boot from
# the file's mtime so every new deploy yields a different `?v=...` and
# browsers that still have the previous app.css cached will re-fetch.
# Fallback to the Python start time if the file is missing for any reason.
_APP_CSS_PATH = os.path.join(os.path.dirname(__file__), "static", "app.css")
try:
    STATIC_VERSION = str(int(os.path.getmtime(_APP_CSS_PATH)))
except OSError:
    import time as _t
    STATIC_VERSION = str(int(_t.time()))
app.jinja_env.globals["STATIC_VERSION"] = STATIC_VERSION

def _country_flag_emoji(code):
    """ISO-2 country code → flag emoji. "MX" → "🇲🇽". Two regional-
    indicator code points concatenated. Returns "" for empty/invalid
    input so the template can still call it unconditionally.

    Kept for places that need a string (titles, aria-labels, alt
    attrs). For visual flag rendering use country_flag_html() —
    emoji flags don't render on Windows browsers (show as country-
    code letter pairs in tofu boxes), and the flag-icons SVG flags
    we wire up there cover that gap."""
    code = (code or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + (ord(c) - ord("A"))) for c in code)
app.jinja_env.globals["_country_flag_emoji"] = _country_flag_emoji

def country_flag_html(code, size="1em"):
    """ISO-2 → <span class="fi fi-xx" style="..."> markup that
    renders via the flag-icons CSS (CDN linked from base.html and
    tv_display_public.html). Returns "" on bad input so templates
    can call unconditionally.

    Why over emoji: emoji flags don't render on Windows browsers —
    operators on a Windows desktop see "MX" in a tofu box instead
    of 🇲🇽. flag-icons ships SVG flags that render uniformly
    everywhere. MIT-licensed (no nominative-use concerns)."""
    code = (code or "").strip().lower()
    if len(code) != 2 or not code.isalpha():
        return ""
    # Inline width/height so the flag matches the surrounding text
    # without requiring per-template CSS. Aspect ratio is 4:3
    # (flag-icons default).
    style = f"width:{size};height:{size};"
    from markupsafe import Markup
    return Markup(
        f'<span class="fi fi-{code}" style="{style}"></span>'
    )
app.jinja_env.globals["country_flag_html"] = country_flag_html

# Engine + session machinery live in api/Core/Database/session.py —
# single source of truth for both the legacy Flask routes and the
# FastAPI strangler-fig side. The engine builds itself from
# `settings.database_url` (env-driven, same DATABASE_URL the legacy
# Flask config used to read). The `db` shim further down rebinds
# `db.session` + `db.engine` to that shared engine, so legacy
# request handlers and FastAPI controllers hit one pool.

# Session-cookie hardening. The Flask `session` cookie carries the
# logged-in user id; an attacker who exfiltrates it gets full account
# access until logout. Three defenses against the common attack
# surfaces:
#
#   - HTTPOnly: no JavaScript can read `document.cookie` and ship
#     it off. Flask defaults this to True; we set it explicitly so
#     a future refactor that toggles cookie config doesn't silently
#     turn it off.
#   - SameSite=Lax: the browser will not attach the session cookie
#     to most cross-site requests (top-level GET navigations still
#     do, which preserves the "click a deeplink in email and stay
#     logged in" UX). Mitigates CSRF without breaking the SPA.
#   - Secure: only sent over HTTPS. Required in prod (TLS-terminated
#     at the Render edge). MUST stay False in dev / CI / sqlite
#     mode or sessions silently fail to set over HTTP, which makes
#     the test suite log everyone out between requests.
#
# Production is detected by APP_BASE_URL pointing at https:// — the
# render.yaml env block sets it, and the SMTP / Stripe URL builders
# already gate on the same value (search `APP_BASE_URL` for the
# other call sites).
_app_base_url = os.environ.get("APP_BASE_URL", "")
_is_https_prod = _app_base_url.startswith("https://")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = _is_https_prod
# Disallow the legacy default of an unbounded session — bound to the
# browser session by default so a forgotten signed-in laptop in a
# coffee shop stops being a key to the kingdom after a reboot.
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)

# ── SQLAlchemy `db` shim (Flask-SQLAlchemy retirement) ───────
#
# Flask-SQLAlchemy is gone. The `db` namespace below replicates just
# the slice the legacy Flask code relies on:
#
#   - ``db.Model``        — the shared declarative Base.
#   - ``db.session``      — thread-local scoped session (the same
#                           shape Flask-SQLAlchemy used to expose,
#                           with ``.add``, ``.commit``, ``.query``,
#                           ``.remove`` etc).
#   - ``db.engine``       — the singleton SQLAlchemy Engine, shared
#                           with FastAPI via ``api.Core.Database``.
#   - ``db.create_all`` / ``db.drop_all`` — used by the test
#                           conftest to spin up + tear down the
#                           in-memory schema.
#   - ``db.relationship`` / ``db.func`` / ``db.or_`` / column types
#                           (``db.Column``, ``db.Integer``, etc) —
#                           transparent re-exports from
#                           ``sqlalchemy``, so every existing model
#                           declaration ``class Foo(db.Model): id =
#                           db.Column(db.Integer, primary_key=True)``
#                           keeps working unchanged.
#
# Legacy ``Model.query`` keeps working too: ``Base.query`` is wired
# to the scoped session below. CLAUDE.md invariant #11 still says
# new code should use ``db.session.query(Model)`` (or
# ``db.session.get(Model, id)``); ``Model.query`` survives for the
# test suite + a handful of in-flight CLI code paths.
#
# A Flask ``teardown_appcontext`` hook calls ``_scoped_session.
# remove()`` after every request so the session is short-lived
# (matches Flask-SQLAlchemy's behaviour). FastAPI's controllers
# get their own session per request via ``Depends(get_db)`` —
# different machinery, same engine.
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
# Inject the legacy ``Model.query`` property onto every subclass of
# Base. Production code uses ``db.session.query(Model)`` (CLAUDE.md
# invariant #11), but the test suite + a handful of helpers still
# go through the shorthand — keep it alive rather than rewriting
# ~565 test-side call sites.
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
        # Re-export the rest of the sqlalchemy namespace — Column,
        # String, Integer, Float, DateTime, Date, Time, Boolean,
        # Text, ForeignKey, UniqueConstraint, Index, LargeBinary,
        # BigInteger, func, or_, and_, desc, asc, case … so legacy
        # ``db.Column(db.Integer, ...)`` declarations keep working.
        return getattr(_sa, name)


db = _DB()


@app.teardown_appcontext
def _remove_db_session(exc):  # noqa: ARG001 (Flask passes the exception)
    _scoped_session.remove()


stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")

# ── Rate limiting (BACKLOG D6 + "Before going live") ─────────
#
# Flask-Limiter on the high-value endpoints — login, signup,
# password reset, webhook ingest, anything an attacker would brute-
# force or flood. Default key function buckets by client IP; when
# the cookie session has resolved we'd ideally bucket by user_id,
# but IP keeps the limiter resilient against unauthenticated
# attacks where the username changes every request.
#
# Storage: in-memory by default (works fine for dev / CI and for
# single-worker prod). When RATELIMIT_STORAGE_URI is set (e.g.
# redis://...) the limiter shares state across workers — required
# in prod with gunicorn -w >1. The render.yaml prod manifest
# should set RATELIMIT_STORAGE_URI on launch.
#
# `enabled` falls back to False during tests so the suite doesn't
# get 429'd by the seeded admin issuing dozens of requests per
# minute. The `_LIMITER_ENABLED` flag lets a specific test opt back
# in via fixture (see tests/test_rate_limiting.py for the pattern).
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
    default_limits=[],  # opt-in per route; no blanket cap
    storage_uri=_RATELIMIT_STORAGE,
    strategy="fixed-window",
    enabled=_LIMITER_ENABLED,
    headers_enabled=True,  # echo X-RateLimit-* on every response
)


def _apply_rate_limits():
    """Wire up rate limits to specific Blueprint + app endpoints.

    Done after Blueprint registration (which already happened at
    module top) AND after the `limiter` exists — Flask-Limiter's
    decorator returns a wrapped view function that we store back
    in ``app.view_functions``, where Flask looks handlers up at
    request time. This avoids decorating Blueprint routes that
    have to be imported before the limiter exists.

    Read CLAUDE.md "Rate limiting" before tightening these — the
    same limits get tripped by integration tests and by webhook
    retry storms. Loosening is safer than the alternative.

    Tuning:
      - Auth burst limits target the unauthenticated path where an
        attacker can change the username on every request — 10/min
        stops most online brute force, 50/hour catches the slower
        password-spray variant.
      - Webhook limits are deliberately loose: Stripe retries on
        5xx + signature verification is the real defense; we just
        want a flood-protection ceiling so an attacker can't tarpit
        us with a million bogus signatures.
    """
    # POST-only so a logged-out user hitting the GET form
    # repeatedly doesn't burn the credit they need to actually
    # try a password.
    _auth_burst = limiter.limit(
        "10 per minute; 50 per hour",
        methods=["POST"],
    )
    _webhook_cap = limiter.limit("120 per minute")

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

    # Webhook ingest — Stripe + Resend. Both routes still live in
    # app.py (they're tied to model state mutations; not slated
    # for Blueprint extraction).
    for endpoint in ("stripe_webhook", "resend_webhook"):
        if endpoint in app.view_functions:
            app.view_functions[endpoint] = _webhook_cap(
                app.view_functions[endpoint],
            )


_apply_rate_limits()


# ── CSRF protection (Before-going-live) ──────────────────────
#
# Flask-WTF's CSRFProtect installs a before_request hook that
# rejects any POST/PUT/PATCH/DELETE not carrying a valid
# `csrf_token` form field (or `X-CSRFToken` header). The token is
# derived from the Flask session, so a foreign-origin form-POST
# can't forge it.
#
# Scope:
#   - Flask form routes: PROTECTED. Every <form method="POST">
#     in the legacy templates renders {{ csrf_token() }} so the
#     token rides along.
#   - FastAPI /api/v2/*: NOT protected by this — those use a
#     Bearer JWT in the Authorization header, which is not
#     auto-attached to cross-origin requests. CSRF is moot there.
#     Flask-WTF still never sees those requests (the
#     DispatcherMiddleware routes them straight into the FastAPI
#     ASGI app).
#   - Webhooks (`/webhooks/{stripe,resend}`): EXEMPTED via
#     `csrf.exempt(...)` after blueprint registration; external
#     callers can't carry our session-bound token. Signature
#     verification is the actual auth on those routes.
#   - WebAuthn passkey JSON routes: EXEMPTED. POST a JSON body
#     not a form; the session itself guards them.
#
# Kill-switch: `WTF_CSRF_ENABLED` config. The test conftest sets
# it to False so existing form-POST tests don't need to mint
# tokens. Production keeps it on.
from flask_wtf.csrf import CSRFProtect

# Reads from env so the conftest can flip the kill-switch with a
# single `os.environ` write — `app.config["WTF_CSRF_ENABLED"]` is
# what Flask-WTF actually checks, so we mirror the env value
# there.
_CSRF_ENABLED = os.environ.get("WTF_CSRF_ENABLED", "True") not in (
    "0", "false", "False",
)
app.config["WTF_CSRF_ENABLED"] = _CSRF_ENABLED
app.config["WTF_CSRF_TIME_LIMIT"] = 60 * 60 * 24 * 7  # 7 days
app.config["WTF_CSRF_SSL_STRICT"] = _is_https_prod

csrf = CSRFProtect(app)


def _csrf_exempt_endpoints():
    """Remove specific endpoints from CSRF enforcement.

    Webhooks were retired from Flask in the Later-phase cleanup
    (moved to ``api.Modules.Webhooks``). The legacy passkey JSON
    endpoints in ``blueprints/auth.py`` + ``blueprints/account.py``
    were also retired with the cookie-session auth path.

    This shim is kept so future Flask form-POST endpoints (if any)
    can register here without re-introducing the wiring. As of
    chunk 3 + Later phase 1 there are no Flask endpoints left that
    need CSRF exemption.
    """
    # Intentionally empty — see docstring.
    return


# Note: _csrf_exempt_endpoints() is only CALLED at the bottom of
# this module (after the FastAPI mount block) — after every
# @app.route decoration in this file has registered its view
# function. Calling here would miss the in-app webhook endpoints
# (stripe_webhook, resend_webhook) which are defined further
# down. Look for the matching invocation at the bottom of app.py.


# ── Models live in api/Modules/<domain>/Models ──────────────────
#
# The canonical SQLAlchemy class definitions all moved out of
# ``app.py`` into per-domain Models packages under ``api/Modules/``.
# This block re-exports each name so every legacy ``from app
# import Store, User, …`` call site (blueprints, services, tests)
# keeps working unchanged. After Flask itself is deleted (Step 8
# end-state), these re-exports go away with the rest of ``app.py``;
# every consumer will import from its module's Models package
# directly.
#
# Domain → package map (also visible in the imports below):
#
#   Announcements → api.Modules.Announcements.Models
#   Audit         → api.Modules.Audit.Models
#   Auth          → api.Modules.Auth.Models
#   BankSync      → api.Modules.BankSync.Models
#   Batches       → api.Modules.Batches.Models
#   Billing       → api.Modules.Billing.Models
#   Customers     → api.Modules.Customers.Models
#   DailyBook     → api.Modules.DailyBook.Models
#   Monthly       → api.Modules.Monthly.Models
#   ReturnChecks  → api.Modules.ReturnChecks.Models
#   Tenancy       → api.Modules.Tenancy.Models
#   Transfers     → api.Modules.Transfers.Models
#   TVDisplay     → api.Modules.TVDisplay.Models  (extracted in PR #495)
#   Webhooks      → api.Modules.Webhooks.Models
from api.Modules.Announcements.Models import (  # noqa: E402
    Announcement, PushSubscription,
)
from api.Modules.Audit.Models import (  # noqa: E402
    OperatorAuditLog, SuperadminAuditLog, TransferAudit,
)
from api.Modules.Auth.Models import (  # noqa: E402
    LoginEvent, Passkey, PasswordResetToken, RecoveryCode,
)
from api.Modules.BankSync.Models import (  # noqa: E402
    BankRule, BankTransaction, StripeBankAccount,
)
from api.Modules.Batches.Models import ACHBatch  # noqa: E402
from api.Modules.Billing.Models import (  # noqa: E402
    DiscountCode, FeatureFlag, ReferralCode, ReferralRedemption,
    StoreFeatureOverride,
)
from api.Modules.Customers.Models import Customer  # noqa: E402
from api.Modules.DailyBook.Models import (  # noqa: E402
    CheckDeposit, DailyDrop, DailyLineItem, DailyReport,
    MoneyTransferSummary,
)
from api.Modules.Monthly.Models import MonthlyFinancial  # noqa: E402
from api.Modules.ReturnChecks.Models import (  # noqa: E402
    RETURN_CHECK_BOOKED, RETURN_CHECK_STATUSES,
    ReturnCheck, ReturnCheckPayment,
)
from api.Modules.Tenancy.Models import (  # noqa: E402
    OwnerConnectCode, Store, StoreEmployee, StoreOwnerLink, User,
)
from api.Modules.Transfers.Models import Transfer  # noqa: E402
from api.Modules.TVDisplay.Models import (  # noqa: E402
    TVBankCatalog, TVCatalogLogo, TVCompanyCatalog, TVDisplay,
    TVDisplayCountry, TVDisplayPayoutBank, TVDisplayRate,
    TVPairing, TVPendingPair,
)
from api.Modules.Webhooks.Models import EmailEvent, WebhookEvent  # noqa: E402


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

def store_addon_keys(store):
    """Return the set of add-on keys currently active for a store.
    Single source of truth lives in
    `api.Modules.Billing.Services.store_addon_keys` (PR 48); this
    Flask-scope wrapper exists for legacy callers."""
    from api.Modules.Billing.Services import (
        store_addon_keys as _svc_store_addon_keys,
    )
    return _svc_store_addon_keys(store)

def store_has_paid_plan(store):
    """Single source of truth lives in
    `api.Modules.Billing.Services.store_has_paid_plan` (PR 48)."""
    from api.Modules.Billing.Services import (
        store_has_paid_plan as _svc_store_has_paid_plan,
    )
    return _svc_store_has_paid_plan(store)

# ── Cancellation & data retention ────────────────────────────
DATA_RETENTION_DAYS = 180  # 6 months

def data_retention_days_left(store):
    """Days until cancelled-store data is purged. Returns None if not scheduled.
    Single source of truth lives in
    `api.Modules.Billing.Services.data_retention_days_left` (PR 48)."""
    from api.Modules.Billing.Services import (
        data_retention_days_left as _svc_data_retention_days_left,
    )
    return _svc_data_retention_days_left(store)

# ── Superadmin helpers ───────────────────────────────────────
def _compute_mrr(basic_monthly, basic_yearly, pro_monthly, pro_yearly):
    """Return MRR components and total from subscriber counts.
    Single source of truth lives in
    `api.Modules.Superadmin.Services.compute_mrr` (PR 75)."""
    from api.Modules.Superadmin.Services import compute_mrr
    return compute_mrr(basic_monthly, basic_yearly,
                       pro_monthly, pro_yearly)




def store_feature_enabled(store, flag_key):
    """Resolve a feature flag for a store: per-store override > global default > True.

    Single source of truth lives in
    `api.Modules.Billing.Services.store_feature_enabled` (PR 49).
    This Flask wrapper just hands the active session over so legacy
    callers don't have to thread `db.session` through the call sites.
    """
    from api.Modules.Billing.Services import (
        store_feature_enabled as _svc_store_feature_enabled,
    )
    return _svc_store_feature_enabled(db.session, store, flag_key)


def active_announcements():
    """Currently-visible announcements (active, within start/expiry window).

    Single source of truth lives in
    `api.Modules.Announcements.Services.active_announcements` (PR 55).
    """
    from api.Modules.Announcements.Services import active_announcements as _svc
    return _svc(db.session)


# ── Platform anomaly detector ──────────────────────────────────
# Surfaced on the superadmin overview tab. Returns a list of
# Platform anomaly rules + the entry point now live in
# `api.Modules.Superadmin.Services.anomalies` (PR 60). The
# threshold constants are re-exported here so legacy callers
# (any test that read them off the module, future rule tweaks)
# keep their existing import paths during the migration window.
from api.Modules.Superadmin.Services import (
    ANOMALY_OVERSHORT_HIGH_THRESHOLD as _ANOMALY_OVERSHORT_HIGH_THRESHOLD,
    ANOMALY_OVERSHORT_LOOKBACK_DAYS as _ANOMALY_OVERSHORT_LOOKBACK_DAYS,
    ANOMALY_OVERSHORT_MEDIUM_THRESHOLD as _ANOMALY_OVERSHORT_MEDIUM_THRESHOLD,
    ANOMALY_QUIET_LOOKBACK_ACTIVE_DAYS as _ANOMALY_QUIET_LOOKBACK_ACTIVE_DAYS,
    ANOMALY_QUIET_LOOKBACK_QUIET_DAYS as _ANOMALY_QUIET_LOOKBACK_QUIET_DAYS,
    ANOMALY_QUIET_MIN_PRIOR_TRANSFERS as _ANOMALY_QUIET_MIN_PRIOR_TRANSFERS,
)






# ── Legacy auth decorators — DEPRECATED stubs ────────────────
#
# The cookie-session login form was retired in chunk 3 (the SPA
# now owns auth via JWT). These decorator stubs survive only so
# the report-route registration block at the bottom of app.py
# keeps assembling the legacy `/reports/<slug>.csv` URL map —
# the CSV downloads still ship from Flask because browser
# `<a href>` downloads can't attach an `Authorization: Bearer`
# header.
#
# **Security note**: these stubs DO NOT enforce any auth check.
# Pilot users only; the CSV download URLs are effectively public
# right now. The "Later" phase of the architecture cleanup
# migrates each CSV export to `/api/v2/reports/<slug>.csv` with
# a JWT signed-URL token, after which these stubs (and the
# legacy `/reports/<slug>` URL surface) can be deleted entirely.
#
# Tracking: BACKLOG.md item D3-followup.


def admin_required(f):
    return f


def superadmin_required(f):
    return f


def owner_required(f):
    return f




# `current_user()` and `current_store()` are defined further up
# (cookie-session reads); they return None for SPA users since
# the SPA never writes to `session`.


# ── Trial Status ─────────────────────────────────────────────
def get_trial_status(store):
    """Return trial status string for the given store.

    Returns: "exempt" | "active" | "expiring_soon" | "grace" | "expired"

    Single source of truth lives in
    `api.Modules.Billing.Services.get_trial_status` (PR 47); this
    Flask-scope wrapper is here for the dozen+ legacy callers that
    use the bare `get_trial_status(store)` shape.
    """
    from api.Modules.Billing.Services import (
        get_trial_status as _svc_get_trial_status,
    )
    return _svc_get_trial_status(store)

@app.context_processor
def inject_trial_context():
    """Inject trial_status, trial_days_left, store, and announcements globally.

    Announcements are visible on every page for every role (including logged-out)
    so the superadmin can reach the whole audience with one message.
    """
    try:
        announcements = active_announcements()
    except Exception:
        # Defensive — context processor runs on every request; if the
        # announcement table can't be queried for any reason, treat as
        # "no banner" so the page still renders.
        announcements = []
    user = current_user()
    if not user:
        return {"trial_status": "exempt", "trial_days_left": 0, "store": None,
                "announcements": announcements}
    if user.role in ("superadmin", "owner"):
        return {"trial_status": "exempt", "trial_days_left": 0, "store": None,
                "announcements": announcements}
    store = current_store()
    status = get_trial_status(store)
    days_left = 0
    if store and store.trial_ends_at:
        delta = store.trial_ends_at - datetime.utcnow()
        days_left = max(0, delta.days)
    # The topbar crown reads `my_referral_code` directly — only filled in
    # for admins on a paid plan so the button hides itself for trials and
    # employees without any template-level conditional.
    my_referral_code = ""
    if (user.role == "admin"
        and store is not None
        and store.plan in ("basic", "pro")):
        try:
            rc = db.session.query(ReferralCode).filter_by(owner_store_id=store.id).first()
            if rc is None:
                rc = ensure_referral_code(store)
                db.session.commit()
            my_referral_code = rc.code if rc else ""
        except Exception as e:
            app.logger.warning(f"referral code lookup failed: {e}")
    return {"trial_status": status, "trial_days_left": days_left, "store": store,
            "announcements": announcements, "my_referral_code": my_referral_code}


@app.context_processor
def inject_impersonation_context():
    """Surfaces the impersonation banner's state. Kept as a small separate
    processor so other surfaces (trial, referrals, announcements) don't
    care about it. Returns is_impersonating=False + empty name by default
    so templates can unconditionally render `{% if is_impersonating %}`."""
    if "impersonator_user_id" not in session:
        return {"is_impersonating": False, "impersonated_store_name": ""}
    sid = session.get("store_id")
    store = db.session.get(Store, sid) if sid else None
    return {
        "is_impersonating": True,
        "impersonated_store_name": store.name if store else "(unknown store)",
    }


@app.context_processor
def inject_active_addons():
    """Expose the current store's active add-ons to every template
    so the sidebar / topbar can conditionally show feature links
    (e.g. "TV Display" only when `tv_display` is on)."""
    store = current_store()
    return {"active_addons": store_addon_keys(store)}

@app.context_processor
def inject_theme():
    """Expose the active UI theme to every template.

    Logged-in users get whatever they've saved on their profile
    (defaults to 'dark' for new accounts and any legacy row that
    pre-dates the column). Logged-out pages always render dark — the
    theme preference is per-user, so it has no meaning before login,
    and dark is the historical default + landing-page hero design.

    `theme` should be wired into the base templates via
    `<html data-theme="{{ theme }}">` so design tokens flip in unison.
    """
    user = current_user()
    if user is None:
        return {"theme": "dark"}
    pref = getattr(user, "theme_preference", None)
    if pref not in ("dark", "light"):
        return {"theme": "dark"}
    return {"theme": pref}

# ── Stripe Financial Connections ─────────────────────────────
# Bank-sync path. SimpleFIN was the original integration; it was
# removed in 2026 once Stripe FC was proven in production, including
# the `simplefin_config` table (see `_drop_legacy_tables()`).
# Hard cap on linked bank accounts per store. Two is enough for the
# typical MSB workflow (e.g., a checking account + an MSB-restricted
# account at the same credit union). Disconnecting frees the slot.
# Cost-control on Stripe Transaction.list (billed per call).
# Manual syncs are capped at MAX_BANK_SYNCS_PER_DAY and must be
# BANK_SYNC_COOLDOWN_MINUTES apart. Initial-connect auto-sync does not
# count against the cap.
# How many days back to pull on initial connect. Per-product
# decision: yesterday + today only — minimal cost, still catches
# any same-day deposits that haven't been entered into the daily
# book. The constant now lives in
# api.Modules.BankSync.Services.sync (PR 72); re-exported here
# so legacy callers keep their import shape during migration.
from api.Modules.BankSync.Services import INITIAL_SYNC_DAYS_BACK












# ── Bank reconcile + rules ──────────────────────────────────
# Categories that can appear on a BankTransaction.category_slug. The
# canonical set is _LINE_ITEM_KINDS (which auto-creates a DailyLineItem
# on the transaction's date) plus these non-posting tags for cases
# where the transaction is reconciled but shouldn't double-count in
# the daily book — internal transfers between own accounts, MT ACH
# withdrawals that already match an ACHBatch, or "ignore" for noise.
# Static bank category dict + the label / validation / grouping
# helpers now live in api.Modules.BankSync.Services.categories
# (PR 69). The constant is re-exported here so existing call sites
# that import it by name (rules engine, categorize service, the
# operator categorisation form) keep their shape during the
# migration window.
from api.Modules.BankSync.Services import (
    BANK_CATEGORIES_NON_POSTING,
)

# Built-in (platform-managed) rules that fire after user-defined rules
# don't match. Used for transaction descriptions that are STANDARD across
# all customers of a given bank — e.g. Nizari Progressive's RDC fee
# always appears as "REMOTE DEPOSIT FEE" on the MSB ••0230 account.
# Operators don't need to set up their own rule for these, and they
# can't be edited via /bank/rules.
#
# Each entry: (description_substring, account_last4_or_None, target_kind).
# An empty `account_last4` matches any account.
# Built-in bank rules + the bank-charge slug predicate live in
# api.Modules.BankSync.Services.builtin_rules (PR 58). The legacy
# names below are kept as thin re-exports so existing call sites
# (categorization sweep, rule-conflict UI) keep their shape during
# the strangler-fig migration window.
from api.Modules.BankSync.Services import (
    BUILTIN_BANK_RULES as _BUILTIN_BANK_RULES,
    is_bank_charge_slug as _is_bank_charge_slug,
    match_builtin_bank_rule as _match_builtin_bank_rule,
)

# Registry: bank-transaction category_slug → MonthlyFinancial column.
# Reserved for future non-bank-charge auto-feeds (e.g. credit-card
# fees, money-order rent). Currently empty: bank-charge slugs are
# dynamic per-account (bank_charge_<last4>) and roll up to
# bank_charges_total via the prefix-match in _bank_charges_for_month
# — they don't need explicit registry entries.








def _is_daily_book_kind(slug):
    """True iff `slug` is a registered DailyBook line-item kind.
    Single source of truth lives in
    `api.Modules.BankSync.Services.is_daily_book_kind` (PR 69).
    """
    from api.Modules.BankSync.Services import is_daily_book_kind
    return is_daily_book_kind(slug)








def sync_bank_transactions(store, since=None, until=None):
    """Pull transactions from every enabled FC account on the store.
    Single source of truth lives in
    `api.Modules.BankSync.Services.sync_bank_transactions` (PR 72).

    Returns `(new_rows, total_seen, last_error)`.
    """
    from api.Modules.BankSync.Services import sync_bank_transactions
    return sync_bank_transactions(db.session, store, since, until)






# SPA cutover before_request hook moved to blueprints/spa_cutover.py
# (D2). SIGNUP_CLOSED stays here because the signup routes below
# (/signup, /signup/owner) check it directly.

# Self-service signup gate. With SIGNUP_CLOSED=1 the /signup and
# /signup/owner pages render a "Signups closed" notice instead of
# the form, the FastAPI signup endpoints return 503, and the
# marketing landing's "Get Started" CTA is suppressed. Existing
# customers still log in normally — only NEW account creation is
# blocked. Flip via Render env var; default is "0" so dev + tests
# work unchanged. CLAUDE.md note: re-enable once pilot review is
# complete and we're ready to take real customers.
SIGNUP_CLOSED = os.environ.get("SIGNUP_CLOSED", "0") == "1"


# PWA routes (/sw.js, /offline) moved to blueprints/pwa.py (D2).

# ── Push notifications ───────────────────────────────────────
# Operators generate a VAPID keypair once (see docs/push-keys.md)
# and set the three env vars below. When they're not set, push
# endpoints return 501 and the opt-in UI stays hidden.
#
# Delivery + the env-var read live in
# api.Modules.Notifications.Services.push (PR 67); the legacy
# names below are re-exports so existing call sites keep their
# shape during the strangler-fig migration window.
from api.Modules.Notifications.Services import push as _push_svc

VAPID_PUBLIC_KEY  = _push_svc.VAPID_PUBLIC_KEY
VAPID_PRIVATE_KEY = _push_svc.VAPID_PRIVATE_KEY
VAPID_SUBJECT     = _push_svc.VAPID_SUBJECT





# /api/push/{public-key,subscribe,unsubscribe,test} moved to
# blueprints/push.py (D2). The shims above (VAPID_*, push_enabled,
# send_push) stay here because legacy callers — including
# tests/Modules/Notifications/test_push_service.py — still
# import them from `app`.

# ── Referrals ────────────────────────────────────────────────
from api.Modules.Billing.Services import (
    REFERRAL_REFEREE_CENTS,
    REFERRAL_SELF_CENTS,
)



def ensure_referral_code(store):
    """Return the store's ReferralCode, creating it on demand.

    Delegates to `api.Modules.Billing.Services.ensure_referral_code`
    (PR 50). Admins only see the crown once they're on a paid plan,
    so call sites should already have checked
    `store.plan in {basic, pro}`.
    """
    from api.Modules.Billing.Services import (
        ensure_referral_code as _svc_ensure_referral_code,
    )
    return _svc_ensure_referral_code(db.session, store)

def lookup_referral_code(raw):
    """Return the active ReferralCode matching the raw input, or None.

    Delegates to `api.Modules.Billing.Services.lookup_referral_code`
    (PR 50). Accepts either the code string or a URL — URL extraction
    happens at the form-parse boundary.
    """
    from api.Modules.Billing.Services import (
        lookup_referral_code as _svc_lookup_referral_code,
    )
    return _svc_lookup_referral_code(db.session, raw)


# ── Login ────────────────────────────────────────────────────
# Installed PWAs open at `start_url` (currently "/") and hide the address
# bar, so a logged-out employee launching the app has no way to reach
# their store-specific login page `/login/<slug>`. We persist the last
# store slug they signed in to in a long-lived cookie and use it to
# bounce `/` and `/login` to `/login/<slug>` automatically. The generic
# `/login` page also exposes a small "enter your store code" escape
# hatch for the first-install / cleared-cookie case.
LAST_STORE_SLUG_COOKIE = "ds_last_store"
LAST_STORE_SLUG_MAX_AGE = 60 * 60 * 24 * 365  # 1 year

def _set_last_store_slug_cookie(resp, slug):
    resp.set_cookie(LAST_STORE_SLUG_COOKIE, slug,
                    max_age=LAST_STORE_SLUG_MAX_AGE,
                    samesite="Lax", httponly=True,
                    secure=request.is_secure)
    return resp


# `/` (landing) and `/privacy` moved to blueprints/landing.py
# (D2 phase 8). The cookie helpers above (_active_store_from_cookie,
# _set_last_store_slug_cookie, LAST_STORE_SLUG_COOKIE) stay here
# because the legacy /login routes still write the cookie.

# ── 2FA (TOTP) helpers ───────────────────────────────────────
# Mandatory for superadmin; other roles opt out entirely today.
# The login flow is:
#   1) POST /login → creds valid → session["pending_auth_user_id"] = uid
#   2) redirect to /login/2fa (if enrolled) or /login/2fa/enroll (if not)
#   3) successful TOTP / recovery code → _finalize_2fa_login() promotes
#      pending_auth_user_id → real user_id session.
# Nothing outside this block should set user_id on its own for a
# 2FA-required role.

# Single source of truth for TOTP / recovery-code helpers lives in
# api.Modules.Auth.Services.totp (PR 41). The Flask-scope wrappers
# below forward to the Service so legacy callers keep their existing
# call shape during the migration window.
from api.Modules.Auth.Services import RECOVERY_CODES_PER_USER  # noqa: E402











# ── Passkeys (WebAuthn) ──────────────────────────────────────
#
# A passkey is phishing-resistant MFA by construction — the credential
# is device-bound, user-presence-proven, and the RP ID prevents replay
# on a look-alike domain. So a successful passkey login is treated as
# MFA-sufficient for every role including superadmin (see the carve-out
# in CLAUDE.md invariant #13). Password login still gates superadmin
# through TOTP; passkey is the parallel path.








# Loose email regex — RFC 5322 is famously underspecified, so we just
# require "something@something.something" to catch obvious typos. Final
# validity is whether mail actually delivers.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Phone: keep generous. Strip whitespace + hyphens + parens; require
# 7–20 digits with an optional leading +. We don't normalize beyond
# that — region codes vary too much for a one-size validator.
_PHONE_DIGITS_RE = re.compile(r"^\+?\d{7,20}$")


# Curated timezone list — Americas + the handful of Asia/Europe zones
# our owner-operators have actually asked for. Adding a zone is one
# line; we deliberately don't expose the full ~600 IANA list because
# that's a UX trap for non-technical cashiers. The empty string means
# "fall back to UTC / store default".



# /login + /login/2fa/* + /login/<slug> + /employee-login moved to
# blueprints/auth.py (D2 phase 25).

# ── Passkey authentication (WebAuthn) ────────────────────────
#
# Three POST pairs:
#   /account/passkeys/register/begin + /finish   — enroll a new passkey
#   /login/passkey/begin + /finish               — sign in with a passkey
#   /account/passkeys/<id>/delete                — remove an enrolled passkey
# Registration is login-gated + role-gated (_passkey_eligible); sign-in is
# anonymous because it IS the login. Challenges round-trip through the
# session (single-use — popped on finish) so the browser can't replay a
# previous attestation / assertion on a later request.

# /account/passkeys/register/{begin,finish} moved to
# blueprints/auth.py (D2 phase 25).

# /account/passkeys/<id>/delete moved to blueprints/account.py (D2 phase 21).

# ── Shared account settings ──────────────────────────────────
#
# /account/security is the per-user "personal security" page reachable
# from every role (admin, owner, employee, superadmin). It hosts the
# things a user manages about THEIR OWN login: display name, password,
# passkeys. Anything store-scoped (companies, team, billing) lives on
# the role-specific settings hubs (admin_settings, owner_dashboard,
# superadmin_controls).
#
# A single POST handler dispatches by an `_action` field so the same
# URL can serve every form on the page — keeps the redirect target
# stable for the PRG pattern.

# /account/security, /account/profile, /admin/settings/security,
# /account/referrals moved to blueprints/account.py (D2 phase 10).


# /account/theme moved to blueprints/account.py (D2 phase 21).

# /account/notifications moved to blueprints/account.py (D2 phase 21).

# /login/passkey/{begin,finish} moved to blueprints/auth.py (D2 phase 25).

# ── Password reset ───────────────────────────────────────────


# Last SMTP attempt state. Updated by _send_email() on every call so the
# superadmin Overview can surface the most recent delivery outcome
# without a live probe on every page load (which would itself be noise
# in SMTP logs + a latency hit). Keys: status ∈ {"unconfigured",
# "sent", "failed", "unknown"}, error (str, "" on success), when
# (datetime or None), last_to (obscured — we show only the domain
# part so the page doesn't leak user email addresses), last_subject.
# Transactional email send + SMTP health probe now live in
# api.Modules.Notifications.Services.smtp (PR 82). The legacy
# names below are thin re-exports / wrappers so existing call
# sites (password reset, trial reminders, announcement broadcast,
# superadmin Overview health card, the test-email button) keep
# their import shape during the migration window.
from api.Modules.Notifications.Services import smtp as _smtp_svc

# Live module-level alias for the health-card state. Uses
# `_smtp_svc.last_attempt` directly so reads always see the
# Service's canonical dict — direct mutation isn't supported.
_last_smtp_attempt = _smtp_svc.last_attempt


# ── Email template rendering ────────────────────────────────
#
# Canonical home: ``api.Modules.Notifications.Services.templates``.
# Re-export here for the legacy in-file callers (``send_trial_reminders``,
# ``send_locked_day_digest``, ``broadcast_announcement``) until they
# migrate into Services themselves.
from api.Modules.Notifications.Services.templates import (  # noqa: E402
    render_email_template,
)



def _send_email(to_addr, subject, body, html=None):
    """Send a transactional email. Single source of truth lives
    in `api.Modules.Notifications.Services.send_email` (PR 82)."""
    return _smtp_svc.send_email(db.session, to_addr, subject, body, html)


def smtp_health_check():
    """Return a dict describing email-delivery state. Single
    source of truth lives in
    `api.Modules.Notifications.Services.smtp_health_check`
    (PR 82)."""
    return _smtp_svc.health_check(db.session)

# /forgot-password, /reset-password/<token>, /signup, /signup/owner,
# /logout moved to blueprints/auth_redirects.py (D2 phase 7).

# ── Owner-side helpers ──────────────────────────────────────────
#
# Owners read across many stores at once and want the same depth of BI
# the superadmin has, scoped to their umbrella. The helpers below carry
# the heavy lifting; the routes below just wire them to templates.
#
# Period selector vocabulary (today / month / year) matches the existing
# UI; "previous-period" windows are the same length, ending the day
# before the current window — that's what the delta badges compare to.

# Owner-side period math, store-id resolution, and KPI rollups
# now live in api.Modules.Owners.Services.dashboard (PR 61). The
# legacy names below are thin re-exports / wrappers so existing
# callers (the dashboard, locations, and CSV-export routes) keep
# their shape during the migration window.
from api.Modules.Owners.Services import (
    OWNER_TRANSFER_EXCLUDED as _OWNER_TRANSFER_EXCLUDED,
    owner_kpis as _svc_owner_kpis,
    owner_period_window as _svc_owner_period_window,
    owner_store_ids as _svc_owner_store_ids,
)




def _owner_store_ids(user):
    """Delegate to api.Modules.Owners.Services.owner_store_ids."""
    return _svc_owner_store_ids(db.session, user)








# Owner routes (/owner/dashboard, /owner/pl-rollup, /owner/locations,
# /owner/store/<id>, /owner/connect, /owner/connect/generate,
# /owner/connect/<id>/revoke, /owner/unlink/<id>) moved to
# blueprints/owner.py (D2). The endpoint names changed from
# `owner_*` to `owner.owner_*` — callers updated in the same PR.

# /subscribe, /subscribe/checkout, /subscribe/success moved to
# blueprints/billing.py (D2 phase 9).

# /account/referrals moved to blueprints/account.py (D2 phase 10).

# Subscription management routes (/admin/subscription[/billing-portal
# /cancel/addons/<key>]) moved to blueprints/subscription.py (D2).
# store_has_addon() stays here because many other parts of app.py
# import it for the addon-gate predicate.

def store_has_addon(store, addon_key):
    """Single predicate every gated route uses, so future Stripe-driven
    `customer.subscription.updated` syncs flip every gated surface in
    one shot.

    Delegates to `api.Modules.Billing.Services.store_has_addon` (PR 49).
    """
    from api.Modules.Billing.Services import (
        store_has_addon as _svc_store_has_addon,
    )
    return _svc_store_has_addon(store, addon_key)

# ── TV Display add-on ────────────────────────────────────────
#
# Routes split into three audiences:
#
#   - /tv-display/*                      — store admins + employees
#                                          (feature is gated by the
#                                          tv_display add-on; both
#                                          roles can edit rates)
#   - /tv/<token>                        — public, fullscreen, no auth
#                                          (the URL the TV browser /
#                                          Chromecast / Fire TV app
#                                          points at)
#   - /superadmin/stores/<id>/addons/*   — superadmin override switches
#                                          (declared with the rest of
#                                          the per-store actions)


def _ensure_tv_display(store):
    """Get-or-create the store's TVDisplay row + initial token."""
    d = db.session.query(TVDisplay).filter_by(store_id=store.id).first()
    if d is None:
        d = TVDisplay(store_id=store.id,
                       public_token=secrets.token_urlsafe(24))
        db.session.add(d); db.session.commit()
    return d

# /tv-display moved to blueprints/tv.py (D2).

# ── Pair-code system for the Fire TV / Google TV companion app ─
#
# Inverted (TV-initiated) flow — matches every other TV pairing UX
# (Netflix, YouTube, Disney+, Apple TV apps):
#
#   1. Fire TV opens the app → app POSTs /api/tv-pair/init.
#   2. Server creates a TVPendingPair row with a fresh 6-char code
#      and a stable device_token. Returns both to the Fire TV.
#   3. Fire TV displays the code (with "go to dinerobook.com/...")
#      and starts polling /api/tv-pair/status with its device_token
#      every 2 seconds.
#   4. Operator on /tv-display types the code into the claim panel.
#      Server validates → revokes any prior active TVPairing on
#      their display → creates a fresh TVPairing reusing the
#      device_token from the pending row → marks the pending row
#      claimed.
#   5. Fire TV's next /status poll returns "claimed" + the
#      per-device URL. App transitions to the rate board.
#
# Why this flow over operator-initiated:
#   - Operator types on a real keyboard (phone/computer browser),
#     not a Fire TV remote. ~3s vs ~15s.
#   - Each Fire TV self-identifies on launch — visually obvious
#     "this device wants to pair." Less ambiguous than "code
#     belongs to the store."
#   - Better failure feedback (errors render in the admin browser
#     with full HTML, not a tiny Fire TV toast).
#   - Matches every other TV pairing flow customers have used.
#
# Single-Fire-TV-per-subscription enforcement is identical to the
# old flow: a successful claim revokes any prior active TVPairing
# on the same display. Pairing a new Fire TV immediately retires
# the old one (the old TV's WebView 404s on its next 30s refresh
# and routes back to the pairing screen).
#
# Anyone can install the companion app (it lives on the Amazon
# Appstore unrestricted) but the claim endpoint refuses to bind a
# code unless the admin's store currently has the tv_display addon
# active. Stripe is the gatekeeper, not Amazon.
#
# Ambiguous chars excluded: O / 0 / I / 1 / L / B / 8.
_PAIR_CODE_ALPHABET = "ACDEFGHJKMNPQRTUVWXYZ234579"
_PAIR_CODE_LIFETIME = timedelta(minutes=10)

def _generate_pair_code():
    """6-char code. Not cryptographic — combined with the 10-min
    expiry and addon gating, brute-force is impractical (27**6 ~
    387M, /status is 404-everything for unknown tokens)."""
    return "".join(secrets.choice(_PAIR_CODE_ALPHABET) for _ in range(6))

def _generate_device_token():
    """32-byte URL-safe random. Same shape as public_token. Loops on
    the (vanishingly rare) collision against either pending or
    paired tables."""
    for _ in range(8):
        t = secrets.token_urlsafe(24)
        if (not db.session.query(TVPairing).filter_by(device_token=t).first()
                and not db.session.query(TVPendingPair).filter_by(device_token=t).first()):
            return t
    # All 8 collided — implausible but raise rather than silently
    # reuse a token.
    raise RuntimeError("Could not mint a unique device_token")

# /api/tv-pair/{init,status} moved to blueprints/tv_pair.py (D2 phase 19).

# /tv-display/countries/<id> (GET, POST) moved to
# blueprints/admin_extras.py (D2 phase 28).


# ── TV Display: public surfaces moved to api/PublicRoutes.py ─
#
# The public TV rate board (/tv/<token> + /tv/device/<dt>), the
# catalog logo serve (/tv/logo/<type>/<slug>), and the pair-code
# JSON API all live on Starlette now. The data-building helper that
# this file used to ship (_render_tv_board) is now
# api.Modules.TVDisplay.Services.build_tv_board_context — pure, no
# Flask render_template / url_for ties.

# ── Report Center ────────────────────────────────────────────
# Categorised list of reports surfaced in /reports (admin) and
# /owner/reports. Each report either deep-links to an existing route
# (`endpoint`) or is rendered as "Coming soon" (endpoint=None) — the
# scaffold ships with the full taxonomy now and reports get wired
# incrementally without further sidebar/template changes. Owner-
# visible reports get `owner_endpoint` as the umbrella variant; if
# omitted the report is hidden from owners.
#
# Data tables + resolver moved to
# ``api.Modules.Reports.Services.categories`` — re-export the
# legacy ``_X`` names so any test / blueprint still doing
# ``from app import _REPORT_CATEGORIES`` keeps working.
from api.Modules.Reports.Services.categories import (  # noqa: E402
    REPORT_CATEGORIES as _REPORT_CATEGORIES,
    SUPERADMIN_REPORT_CATEGORIES as _SUPERADMIN_REPORT_CATEGORIES,
    resolved_categories as _resolved_report_categories,
    url_from_endpoint as _url_from_endpoint,
)


# /reports + /owner/reports moved to blueprints/spa_redirects.py
# (D2 phase 11).


# ── Reports: shared period helpers ───────────────────────────
# Report pages use a consistent ?from=YYYY-MM-DD&to=YYYY-MM-DD
# query convention with current-month default. Shared here so each
# report doesn't reimplement parsing + defaults.
def _report_period(args):
    today = date.today()
    default_from = date(today.year, today.month, 1)
    raw_from = (args.get("from") or "").strip()
    raw_to   = (args.get("to") or "").strip()
    try:
        d_from = datetime.strptime(raw_from, "%Y-%m-%d").date() if raw_from else default_from
    except ValueError:
        d_from = default_from
    try:
        d_to = datetime.strptime(raw_to, "%Y-%m-%d").date() if raw_to else today
    except ValueError:
        d_to = today
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    label = f"{d_from.strftime('%b %d, %Y')} – {d_to.strftime('%b %d, %Y')}"
    return d_from, d_to, label


def _report_scope_ids():
    """Return the list of store_ids the current request should query.
    Admin → just their store; owner → every linked store. Centralising
    this lets the same data helpers back both /reports/<slug> (admin)
    and /owner/reports/<slug> (owner) — only the scope changes."""
    role = session.get("role")
    if role == "owner":
        u = current_user()
        return _owner_store_ids(u) if u else []
    sid = session.get("store_id")
    return [sid] if sid else []


# Calendar-date → naive datetime boundary helpers now live in
# api.Modules.Reports.Services.date_helpers (PR 83). Re-exports
# below preserve the legacy import shape during the migration
# window.
from api.Modules.Reports.Services import (
    day_end as _day_end,
    day_start as _day_start,
)



def _run_report_csv(data_fn, *, scope, columns, row_fn,
                     totals_row_fn=None, fname_prefix,
                     extra_args=None):
    """Shared core for `_export_report_csv` (admin/owner) and
    `_export_superadmin_report_csv` (platform-wide). `scope` flips
    the data-fn signature only — everything else is identical."""
    extra_args = extra_args or {}
    d_from, d_to, _ = _report_period(request.args)
    if scope == "platform":
        rows, totals = data_fn(d_from, d_to, **extra_args)
    else:
        rows, totals = data_fn(_report_scope_ids(), d_from, d_to,
                                **extra_args)
    buf = io.StringIO(); w = csv.writer(buf)
    cols = columns(totals) if callable(columns) else columns
    w.writerow(cols)
    for r in rows:
        w.writerow(row_fn(r))
    if totals_row_fn is not None:
        result = totals_row_fn(totals)
        # Accept either a single row (list of cells) or multiple
        # totals rows (list of lists). Detect by inspecting the
        # first element.
        totals_rows = (result if result and isinstance(result[0], (list, tuple))
                       else [result])
        if totals_rows:
            w.writerow([])
            for trow in totals_rows:
                w.writerow(trow)
    return _csv_response(buf,
        f"{fname_prefix}_{d_from.isoformat()}_{d_to.isoformat()}.csv")


def _export_report_csv(data_fn, *, columns, row_fn,
                        totals_row_fn=None, fname_prefix,
                        extra_args=None):
    """Admin / owner CSV — store-scoped data fn. Thin wrapper around
    `_run_report_csv`."""
    return _run_report_csv(data_fn, scope="store",
        columns=columns, row_fn=row_fn, totals_row_fn=totals_row_fn,
        fname_prefix=fname_prefix, extra_args=extra_args)



def _make_report_routes(slug, *, data_fn, csv_columns, csv_row_fn,
                         csv_totals_fn=None, csv_fname_prefix=None,
                         extra_args_fn=None):
    """Register admin (``/reports/<slug>.csv``) + owner
    (``/owner/reports/<slug>.csv``) CSV download routes for a
    single report. Endpoints follow the convention
    ``report_<slug_underscored>_csv`` (admin) /
    ``owner_report_<slug_underscored>_csv`` (owner).

    The HTML drilldown lives on the React SPA — the
    ``spa_cutover`` ``before_request`` hook 301s every legacy GET
    of ``/reports/<slug>`` or ``/owner/reports/<slug>`` to the SPA
    URL before any Flask handler runs, so this function doesn't
    register HTML routes at all.

    ``extra_args_fn()`` is called per-request for reports that
    take extra query params (e.g. ``high-value-transfers`` reads
    ``?threshold=``).
    """
    fname_prefix = csv_fname_prefix or slug
    extra_args_fn = extra_args_fn or (lambda: {})
    underscored = slug.replace("-", "_")

    def _csv():
        return _export_report_csv(data_fn,
            columns=csv_columns, row_fn=csv_row_fn,
            totals_row_fn=csv_totals_fn,
            fname_prefix=fname_prefix,
            extra_args=extra_args_fn(),
        )

    app.add_url_rule(f"/reports/{slug}.csv",
                     endpoint=f"report_{underscored}_csv",
                     view_func=admin_required(_csv), methods=["GET"])
    app.add_url_rule(f"/owner/reports/{slug}.csv",
                     endpoint=f"owner_report_{underscored}_csv",
                     view_func=owner_required(_csv), methods=["GET"])






# Adapter for the seven Reports services that used to be wrapped by
# `_*_data` shims in this file. The shims existed during PRs 2-4 of
# the strangler-fig migration so legacy callers (`_make_report_routes`
# below) could keep their `(store_ids, d_from, d_to)` signature
# while the business logic moved into `api.Modules.Reports.Services`.
# Now that the services are stable and unit-tested (and exposed via
# the FastAPI router at /api/v2/reports/*), the shims add no value —
# call sites use this adapter inline.
def _service_fn(service):
    """Wraps a Reports service (which takes the SQLAlchemy Session as
    its first argument) in the legacy `data_fn(store_ids, d_from, d_to,
    **kwargs)` signature `_make_report_routes` expects. The Flask
    route binds to `db.session`; the FastAPI route binds to its own
    request-scoped session via `Depends(get_db)`."""
    def _inner(store_ids, d_from, d_to, **kwargs):
        return service(db.session, store_ids, d_from, d_to, **kwargs)
    return _inner

# Eager-imports for the Reports services backing the CSV routes
# below — each one used to have an ``_X_data`` Flask-bound shim
# but ``_service_fn`` handles the session-binding for all of them.
from api.Modules.Reports.Services import (  # noqa: E402
    ach_volume, bank_charges_by_account, bank_rule_audit,
    bank_txn_breakdown, cancelled_transfers, check_deposits,
    daily_drops, employee_activity, fees_vs_tax,
    high_value_transfers, period_comparison, period_pl,
    returned_check_status,
)

from api.Modules.Reports.Services import new_vs_returning  # noqa: E402


# Adapter for the 20 superadmin Reports services. Same shape as
# ``_service_fn`` above, but the platform-scoped Reports.Service
# signature is ``service(db, d_from, d_to, **kwargs)`` (no
# ``store_ids``), so the adapter binds ``db.session`` and forwards
# the period + extras. Used by ``_make_superadmin_report_routes``
# call sites below.
from api.Modules.Superadmin.Services import (  # noqa: E402
    active_stores_by_plan, bank_sync_adoption, churn_cohort,
    conversion_rate, dau_mau, failed_payments, login_activity,
    mrr_arr, owner_adoption, passkey_adoption, password_resets,
    payouts, refunds, retention_queue, signup_funnel,
    suspended_stores, time_to_convert, trial_expiry_timing,
    tv_display_adoption, webhook_health,
)


def _sa_service_fn(service):
    """Bind ``db.session`` + forward the period to a Reports.Service
    so the result fits the ``(d_from, d_to, **kwargs)`` data_fn
    signature ``_make_superadmin_report_routes`` expects."""
    def _inner(d_from, d_to, **kwargs):
        return service(db.session, d_from, d_to, **kwargs)
    return _inner





def _csv_response(buf, fname):
    """Wrap a StringIO buffer as a downloadable text/csv response.
    Pulled out so each report's CSV route stops repeating the
    Content-Disposition incantation."""
    return Response(buf.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ── Returned Check Status ────────────────────────────────────


# ── Bank Transactions Breakdown ──────────────────────────────


# ── Daily Drops ──────────────────────────────────────────────


# ── Check Deposits ───────────────────────────────────────────


# ── High-Value Transfers ─────────────────────────────────────


def _parse_threshold(args, default=3000):
    try:
        v = float(args.get("threshold") or default)
    except (ValueError, TypeError):
        v = default
    return max(0.0, v)


# ── Employee Activity ────────────────────────────────────────


# ── Bank-Rule Audit Log ──────────────────────────────────────


# ── Cancelled Transfers ──────────────────────────────────────


# ── Period P&L ───────────────────────────────────────────────
# Daily-book lines that flow into the P&L. The (label, attr,
# section) tuples drive the line-item rendering + CSV.
# Daily-book P&L line constants now live in
# api.Modules.Reports.Services.period_comparison (PR 86).
# Re-exported here so existing call sites (period P&L, period
# comparison, monthly P&L feed) keep their import shape.
from api.Modules.Reports.Services import (
    PL_EXPENSE_LINES as _PL_EXPENSE_LINES,
    PL_INCOME_LINES as _PL_INCOME_LINES,
)




# ── ACH Volume ───────────────────────────────────────────────


# ── Bank Charges by Account ──────────────────────────────────


# ── Period Comparison ────────────────────────────────────────


# ── Fees vs. Federal Tax ─────────────────────────────────────


# ── Period-comparison KPIs (multi-statement; can't be a lambda) ──


# ── Report-route registry ───────────────────────────────────
# Each call registers admin (`/reports/<slug>`) + owner
# (`/owner/reports/<slug>`) HTML and CSV routes via
# `_make_report_routes`. Per-report config is the kpis_fn closure +
# CSV column / row / totals lambdas. New reports go here — no
# per-route boilerplate, no per-route owner wiring (the auto-mirror
# below covers it).
from api.Modules.Reports.Services import (  # noqa: E402
    by_destination_country as _svc_by_destination_country,
    cashier_productivity as _svc_cashier_productivity,
    sales_by_company as _svc_sales_by_company,
    sales_by_employee as _svc_sales_by_employee,
    sales_by_service as _svc_sales_by_service,
    top_customers as _svc_top_customers,
    top_recipients as _svc_top_recipients,
)

_make_report_routes(
    'sales-by-company',
    data_fn=_service_fn(_svc_sales_by_company),
    csv_columns=['Company', 'Count', 'Total Sent', 'Total Fees', 'Federal Tax', 'Avg Transfer'],
    csv_row_fn=lambda r: [r['company'], r['count'], f"{r['sent']:.2f}", f"{r['fees']:.2f}", f"{r['tax']:.2f}", f"{r['avg']:.2f}"],
    csv_totals_fn=lambda t: ['TOTAL', t['count'], f"{t['sent']:.2f}", f"{t['fees']:.2f}", f"{t['tax']:.2f}", ''],
)

_make_report_routes(
    'sales-by-service-type',
    data_fn=_service_fn(_svc_sales_by_service),
    csv_columns=['Service Type', 'Count', 'Total Sent', 'Total Fees', 'Federal Tax', 'Avg Transfer'],
    csv_row_fn=lambda r: [r['service_type'], r['count'], f"{r['sent']:.2f}", f"{r['fees']:.2f}", f"{r['tax']:.2f}", f"{r['avg']:.2f}"],
    csv_totals_fn=lambda t: ['TOTAL', t['count'], f"{t['sent']:.2f}", f"{t['fees']:.2f}", f"{t['tax']:.2f}", ''],
)

_make_report_routes(
    'sales-by-employee',
    data_fn=_service_fn(_svc_sales_by_employee),
    csv_columns=['Employee', 'Username', 'Count', 'Total Sent', 'Total Fees', 'Federal Tax', 'Avg Transfer'],
    csv_row_fn=lambda r: [r['employee'], r['username'], r['count'], f"{r['sent']:.2f}", f"{r['fees']:.2f}", f"{r['tax']:.2f}", f"{r['avg']:.2f}"],
    csv_totals_fn=lambda t: ['TOTAL', '', t['count'], f"{t['sent']:.2f}", f"{t['fees']:.2f}", f"{t['tax']:.2f}", ''],
)

_make_report_routes(
    'cashier-productivity',
    data_fn=_service_fn(_svc_cashier_productivity),
    csv_columns=['Cashier', 'Active', 'Count', 'Total Sent', 'Total Fees', 'Federal Tax', 'Avg Transfer'],
    csv_row_fn=lambda r: [r['cashier'], 'yes' if r['is_active'] else 'no', r['count'], f"{r['sent']:.2f}", f"{r['fees']:.2f}", f"{r['tax']:.2f}", f"{r['avg']:.2f}"],
    csv_totals_fn=lambda t: ['TOTAL', '', t['count'], f"{t['sent']:.2f}", f"{t['fees']:.2f}", f"{t['tax']:.2f}", ''],
)

_make_report_routes(
    'top-customers',
    data_fn=_service_fn(_svc_top_customers),
    csv_columns=['Customer', 'Phone', 'Count', 'Total Sent', 'Total Fees', 'Federal Tax', 'Avg Transfer'],
    csv_row_fn=lambda r: [r['customer'], r['phone'], r['count'], f"{r['sent']:.2f}", f"{r['fees']:.2f}", f"{r['tax']:.2f}", f"{r['avg']:.2f}"],
)

_make_report_routes(
    'top-senders',
    data_fn=_service_fn(lambda db_session, store_ids, d_from, d_to, **_: _svc_top_customers(db_session, store_ids, d_from, d_to, sort_by='count')),
    csv_columns=['Customer', 'Phone', 'Count', 'Total Sent', 'Total Fees', 'Federal Tax', 'Avg Transfer'],
    csv_row_fn=lambda r: [r['customer'], r['phone'], r['count'], f"{r['sent']:.2f}", f"{r['fees']:.2f}", f"{r['tax']:.2f}", f"{r['avg']:.2f}"],
)

_make_report_routes(
    'top-recipients',
    data_fn=_service_fn(_svc_top_recipients),
    csv_columns=['Recipient', 'Count', 'Total Sent', 'Total Fees', 'Federal Tax', 'Avg Transfer'],
    csv_row_fn=lambda r: [r['recipient'], r['count'], f"{r['sent']:.2f}", f"{r['fees']:.2f}", f"{r['tax']:.2f}", f"{r['avg']:.2f}"],
)

_make_report_routes(
    'by-destination-country',
    data_fn=_service_fn(_svc_by_destination_country),
    csv_columns=['Country', 'Count', 'Total Sent', 'Total Fees', 'Federal Tax', 'Avg Transfer'],
    csv_row_fn=lambda r: [r['country'], r['count'], f"{r['sent']:.2f}", f"{r['fees']:.2f}", f"{r['tax']:.2f}", f"{r['avg']:.2f}"],
    csv_totals_fn=lambda t: ['TOTAL', t['count'], f"{t['sent']:.2f}", f"{t['fees']:.2f}", f"{t['tax']:.2f}", ''],
)

_make_report_routes(
    'new-vs-returning',
    data_fn=_service_fn(new_vs_returning),
    csv_columns=['Bucket', 'Customers', 'Transfers', 'Total Sent'],
    csv_row_fn=lambda r: [r['bucket'], r['customers'], r['txns'], f"{r['sent']:.2f}"],
    csv_totals_fn=lambda t: ['TOTAL', t['customers'], t['txns'], f"{t['sent']:.2f}"],
)

_make_report_routes(
    'returned-check-status',
    data_fn=_service_fn(returned_check_status),
    csv_columns=['Status', 'Count', 'Amount', 'Recovered'],
    csv_row_fn=lambda r: [r['status'], r['count'], f"{r['amount']:.2f}", f"{r['recovered']:.2f}"],
    csv_totals_fn=lambda t: [['TOTAL', t['count'], f"{t['amount']:.2f}", f"{t['recovered']:.2f}"], ['NET G/L', '', '', f"{t['net_gl']:.2f}"]],
    csv_fname_prefix='returned-checks',
)

_make_report_routes(
    'bank-transactions-breakdown',
    data_fn=_service_fn(bank_txn_breakdown),
    csv_columns=['Category', 'Count', 'Signed Amount', 'Absolute Amount'],
    csv_row_fn=lambda r: [r['label'], r['count'], f"{r['signed']:.2f}", f"{r['amount']:.2f}"],
    csv_fname_prefix='bank-txn-breakdown',
)

_make_report_routes(
    'daily-drops',
    data_fn=_service_fn(daily_drops),
    csv_columns=['Date', 'Drop Count', 'Total Dropped'],
    csv_row_fn=lambda r: [r['date'].isoformat(), r['count'], f"{r['amount']:.2f}"],
    csv_totals_fn=lambda t: ['TOTAL', t['count'], f"{t['amount']:.2f}"],
)

_make_report_routes(
    'check-deposits',
    data_fn=_service_fn(check_deposits),
    csv_columns=['Date', 'Deposit Count', 'Total Deposited'],
    csv_row_fn=lambda r: [r['date'].isoformat(), r['count'], f"{r['amount']:.2f}"],
    csv_totals_fn=lambda t: ['TOTAL', t['count'], f"{t['amount']:.2f}"],
)

_make_report_routes(
    'high-value-transfers',
    data_fn=_service_fn(high_value_transfers),
    csv_columns=['Date', 'Sender', 'Recipient', 'Country', 'Company', 'Send Amount', 'Fee', 'Federal Tax', 'Confirm #'],
    csv_row_fn=lambda r: [r['send_date'].isoformat(), r['sender_name'], r['recipient_name'], r['country'], r['company'], f"{r['amount']:.2f}", f"{r['fee']:.2f}", f"{r['tax']:.2f}", r['confirm']],
    extra_args_fn=lambda: {'threshold': _parse_threshold(request.args)},
)

_make_report_routes(
    'employee-activity',
    data_fn=_service_fn(employee_activity),
    csv_columns=['Employee', 'Username', 'Active Transfers', 'Total Sent', 'Cancelled / Rejected', 'Last Activity'],
    csv_row_fn=lambda r: [r['employee'], r['username'], r['count'], f"{r['sent']:.2f}", r['cancels'], r['last_activity'].isoformat() if r['last_activity'] else ''],
)

_make_report_routes(
    'bank-rule-audit',
    data_fn=_service_fn(bank_rule_audit),
    csv_columns=['Rule', 'Match', 'Target', 'Matched Count', 'Total Amount'],
    csv_row_fn=lambda r: [r['label'], r['match'], r['target'], r['count'], f"{r['amount']:.2f}"],
)

_make_report_routes(
    'cancelled-transfers',
    data_fn=_service_fn(cancelled_transfers),
    csv_columns=['Date', 'Sender', 'Recipient', 'Country', 'Company', 'Status', 'Send Amount', 'Notes', 'Confirm #'],
    csv_row_fn=lambda r: [r['send_date'].isoformat(), r['sender_name'], r['recipient_name'], r['country'], r['company'], r['status'], f"{r['amount']:.2f}", r['status_notes'], r['confirm']],
)

_make_report_routes(
    'period-pl',
    data_fn=_service_fn(period_pl),
    csv_columns=['Section', 'Line', 'Amount'],
    csv_row_fn=lambda r: [r['section'], r['label'], f"{r['amount']:.2f}"],
    csv_totals_fn=lambda t: [['', 'Total Income', f"{t['income']:.2f}"], ['', 'Total Expenses', f"{t['expenses']:.2f}"], ['', 'Net', f"{t['net']:.2f}"]],
)

_make_report_routes(
    'ach-volume',
    data_fn=_service_fn(ach_volume),
    csv_columns=['Company', 'Batch Count', 'Total ACH', 'Avg / Batch'],
    csv_row_fn=lambda r: [r['company'], r['count'], f"{r['amount']:.2f}", f"{r['avg']:.2f}"],
    csv_totals_fn=lambda t: ['TOTAL', t['count'], f"{t['amount']:.2f}", ''],
)

_make_report_routes(
    'bank-charges-by-account',
    data_fn=_service_fn(bank_charges_by_account),
    csv_columns=['Account', 'Last 4', 'Charge Count', 'Total Charges', 'Avg / Charge'],
    csv_row_fn=lambda r: [r['account'], r['last4'], r['count'], f"{r['amount']:.2f}", f"{r['avg']:.2f}"],
)

def _parse_compare_dates(args):
    """Pull the optional `compare_from` / `compare_to` query params
    for the Period Comparison report. Returns a dict with both keys
    set to either parsed dates or None — both must be present for
    the data fn to honour the custom window."""
    def _parse(name):
        raw = (args.get(name) or "").strip()
        if not raw:
            return None
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            return None
    return {"compare_from": _parse("compare_from"),
            "compare_to":   _parse("compare_to")}


_make_report_routes(
    'period-comparison',
    data_fn=_service_fn(period_comparison),
    csv_columns=lambda t: ['Metric', t['current_label'], t['prior_label'], 'Delta', '% Change'],
    csv_row_fn=lambda r: [r['label'], f"{r['current']:.2f}" if r['is_money'] else f"{int(r['current'])}", f"{r['prior']:.2f}" if r['is_money'] else f"{int(r['prior'])}", f"{r['delta']:.2f}" if r['is_money'] else f"{int(r['delta'])}", f"{r['pct']:+.1f}%"],
    extra_args_fn=lambda: _parse_compare_dates(request.args),
)

_make_report_routes(
    'fees-vs-tax',
    data_fn=_service_fn(fees_vs_tax),
    csv_columns=['Line', 'Amount'],
    csv_row_fn=lambda r: [r['label'], f"{r['amount']:.2f}"],
    csv_totals_fn=lambda t: ['Tax / Fee Ratio', f"{t['ratio']:.2f}"],
)


# Owner mirror routes — every /reports/<slug>(.csv)? admin route gets a
# matching /owner/reports/<slug>(.csv)? endpoint that calls the SAME
# handler. Scope (single store vs. owner umbrella) is decided inside
# the handler via _report_scope_ids() reading session role; the back-
# link target + CSV-export endpoint flip the same way via
# _is_owner_request(). This way new reports get owner support for free
# — add an admin route, the mirror appears automatically.
def _register_owner_report_mirrors():
    for rule in list(app.url_map.iter_rules()):
        if not rule.rule.startswith("/reports/"):
            continue
        ep = rule.endpoint
        if not ep.startswith("report_"):
            continue
        owner_ep = "owner_" + ep
        if owner_ep in app.view_functions:
            continue
        wrapped = app.view_functions[ep]
        # admin_required uses functools.wraps, so __wrapped__ is the
        # original undecorated handler.
        original = getattr(wrapped, "__wrapped__", wrapped)
        owner_handler = owner_required(original)
        owner_path = "/owner" + rule.rule
        app.add_url_rule(owner_path, endpoint=owner_ep,
                         view_func=owner_handler,
                         methods=list(rule.methods - {"HEAD", "OPTIONS"}))


_register_owner_report_mirrors()


# Superadmin Report Center — platform-level metrics and audit views.
# Read-only by design; mutate-on-the-platform routes stay in
# /superadmin/controls.


# /superadmin/reports + /superadmin/reports/audit-log moved to
# blueprints/superadmin_redirects.py (D2 phase 12).


# ── Superadmin reports: shared route helpers ─────────────────
# Same shape as the admin/owner _make_report_routes helper but
# scoped to /superadmin/reports/<slug>(.csv)? and gated with
# @superadmin_required. Data functions don't take store_ids —
# superadmin reports always query platform-wide.


def _export_superadmin_report_csv(data_fn, *, columns, row_fn,
                                    totals_row_fn=None, fname_prefix,
                                    extra_args=None):
    """Superadmin CSV — thin wrapper around `_run_report_csv`."""
    return _run_report_csv(data_fn, scope="platform",
        columns=columns, row_fn=row_fn, totals_row_fn=totals_row_fn,
        fname_prefix=fname_prefix, extra_args=extra_args)


def _make_superadmin_report_routes(slug, *, data_fn,
                                     csv_columns, csv_row_fn,
                                     csv_totals_fn=None,
                                     csv_fname_prefix=None,
                                     extra_args_fn=None):
    """Register the ``/superadmin/reports/<slug>.csv`` route for a
    superadmin report. Same idea as ``_make_report_routes`` but
    superadmin-only — no owner mirror.

    Every superadmin BI drilldown migrated to the SPA in one batch
    via ``/api/v2/superadmin/reports/<slug>``. The HTML GET 301s
    via ``spa_cutover``'s before_request hook, so no Flask handler
    for the HTML path is registered here.
    """
    fname_prefix = csv_fname_prefix or slug
    extra_args_fn = extra_args_fn or (lambda: {})
    underscored = slug.replace("-", "_")

    def _csv():
        return _export_superadmin_report_csv(data_fn,
            columns=csv_columns, row_fn=csv_row_fn,
            totals_row_fn=csv_totals_fn,
            fname_prefix=fname_prefix,
            extra_args=extra_args_fn(),
        )

    app.add_url_rule(f"/superadmin/reports/{slug}.csv",
                     endpoint=f"superadmin_report_{underscored}_csv",
                     view_func=superadmin_required(_csv),
                     methods=["GET"])


# ── Superadmin report data functions ─────────────────────────












































# ── Superadmin reports: registry of routes ───────────────────
_make_superadmin_report_routes(
    'active-stores-by-plan',
    data_fn=_sa_service_fn(active_stores_by_plan),
    csv_columns=['Plan', 'Stores'],
    csv_row_fn=lambda r: [r['plan'], r['count']],
    csv_totals_fn=lambda t: ['TOTAL', t['count']],
    csv_fname_prefix='active-stores-by-plan',
)

_make_superadmin_report_routes(
    'signup-funnel',
    data_fn=_sa_service_fn(signup_funnel),
    csv_columns=['Plan', 'Signups'],
    csv_row_fn=lambda r: [r['plan'], r['count']],
    csv_totals_fn=lambda t: ['TOTAL', t['count']],
)

_make_superadmin_report_routes(
    'login-activity',
    data_fn=_sa_service_fn(login_activity),
    csv_columns=['Role', 'Active Users'],
    csv_row_fn=lambda r: [r['role'], r['count']],
    csv_totals_fn=lambda t: ['TOTAL', t['count']],
)

_make_superadmin_report_routes(
    'mrr-arr',
    data_fn=_sa_service_fn(mrr_arr),
    csv_columns=['Plan', 'Cycle', 'Stores', 'MRR', 'ARR'],
    csv_row_fn=lambda r: [r['plan'], r['cycle'], r['stores'], f"{r['mrr']:.2f}", f"{r['arr']:.2f}"],
    csv_totals_fn=lambda t: ['TOTAL', '', t['stores'], f"{t['mrr']:.2f}", f"{t['arr']:.2f}"],
)

_make_superadmin_report_routes(
    'churn-cohort',
    data_fn=_sa_service_fn(churn_cohort),
    csv_columns=['Cohort', 'Cancelled', 'Still Active', 'Churn %'],
    csv_row_fn=lambda r: [r['cohort'], r['cancelled'], r['active'], f"{r['churn_pct']:.1f}%"],
)

_make_superadmin_report_routes(
    'conversion-rate',
    data_fn=_sa_service_fn(conversion_rate),
    csv_columns=['Status', 'Stores'],
    csv_row_fn=lambda r: [r['label'], r['count']],
    csv_totals_fn=lambda t: ['TOTAL', t['total']],
)

_make_superadmin_report_routes(
    'time-to-convert',
    data_fn=_sa_service_fn(time_to_convert),
    csv_columns=['Slug', 'Name', 'Plan', 'Signed Up', 'Days Active'],
    csv_row_fn=lambda r: [r['slug'], r['name'], r['plan'], r['signed_up'].isoformat(), r['days']],
)

_make_superadmin_report_routes(
    'trial-expiry-timing',
    data_fn=_sa_service_fn(trial_expiry_timing),
    csv_columns=['Bucket', 'Stores'],
    csv_row_fn=lambda r: [r['bucket'], r['count']],
)

_make_superadmin_report_routes(
    'bank-sync-adoption',
    data_fn=_sa_service_fn(bank_sync_adoption),
    csv_columns=['Plan', 'Connected', 'Total', 'Adoption %'],
    csv_row_fn=lambda r: [r['plan'], r['connected'], r['total'], f"{r['rate_pct']:.1f}%"],
)

_make_superadmin_report_routes(
    'tv-display-adoption',
    data_fn=_sa_service_fn(tv_display_adoption),
    csv_columns=['Slug', 'Name', 'Plan'],
    csv_row_fn=lambda r: [r['slug'], r['name'], r['plan']],
)

_make_superadmin_report_routes(
    'owner-adoption',
    data_fn=_sa_service_fn(owner_adoption),
    csv_columns=['Owner', 'Email', 'Linked Stores'],
    csv_row_fn=lambda r: [r['owner'], r['email'], r['stores']],
)

_make_superadmin_report_routes(
    'passkey-adoption',
    data_fn=_sa_service_fn(passkey_adoption),
    csv_columns=['Role', 'Users with Passkey'],
    csv_row_fn=lambda r: [r['role'], r['count']],
)

_make_superadmin_report_routes(
    'password-resets',
    data_fn=_sa_service_fn(password_resets),
    csv_columns=['Created', 'Username', 'Role', 'Status'],
    csv_row_fn=lambda r: [r['created_at'].isoformat() if r['created_at'] else '', r['username'], r['role'], r['status']],
)

_make_superadmin_report_routes(
    'suspended-stores',
    data_fn=_sa_service_fn(suspended_stores),
    csv_columns=['Slug', 'Name', 'Plan', 'Reason'],
    csv_row_fn=lambda r: [r['slug'], r['name'], r['plan'], r['reason']],
)

_make_superadmin_report_routes(
    'retention-queue',
    data_fn=_sa_service_fn(retention_queue),
    csv_columns=['Slug', 'Name', 'Plan', 'Purge Date', 'Days Left'],
    csv_row_fn=lambda r: [r['slug'], r['name'], r['plan'], r['until'].isoformat() if r['until'] else '', r['days_left']],
)

_make_superadmin_report_routes(
    'refunds',
    data_fn=_sa_service_fn(refunds),
    csv_columns=['Reason', 'Count', 'Amount'],
    csv_row_fn=lambda r: [r['reason'], r['count'], f"{r['amount']:.2f}"],
    csv_totals_fn=lambda t: ['TOTAL', t['count'], f"{t['amount']:.2f}"],
)

_make_superadmin_report_routes(
    'failed-payments',
    data_fn=_sa_service_fn(failed_payments),
    csv_columns=['Reason', 'Count', 'Amount'],
    csv_row_fn=lambda r: [r['reason'], r['count'], f"{r['amount']:.2f}"],
    csv_totals_fn=lambda t: ['TOTAL', t['count'], f"{t['amount']:.2f}"],
)

_make_superadmin_report_routes(
    'payouts',
    data_fn=_sa_service_fn(payouts),
    csv_columns=['Payout ID', 'Amount', 'Status', 'Method', 'Arrival'],
    csv_row_fn=lambda r: [r['id'], f"{r['amount']:.2f}", r['status'], r['method'], r['arrival'].isoformat() if r['arrival'] else ''],
    csv_totals_fn=lambda t: ['TOTAL', f"{t['amount']:.2f}", '', '', ''],
)

_make_superadmin_report_routes(
    'dau-mau',
    data_fn=_sa_service_fn(dau_mau),
    csv_columns=['Date', 'Active Users'],
    csv_row_fn=lambda r: [str(r['day']), r['users']],
    csv_totals_fn=lambda t: ['TOTAL (MAU)', t['mau']],
)

_make_superadmin_report_routes(
    'webhook-health',
    data_fn=_sa_service_fn(webhook_health),
    csv_columns=['Status', 'Count'],
    csv_row_fn=lambda r: [r['status'], r['count']],
    csv_totals_fn=lambda t: ['TOTAL', t['count']],
)


# /dashboard moved to blueprints/spa_redirects.py (D2 phase 11).

# ── Customers (per-store directory) ──────────────────────────
# Ordered roughly by likelihood for a US-based remittance storefront; the
# picker displays these in order so the common choices stay on top.
# Phone-country-code reference list for the customer + transfer
# forms now lives in
# `api.Modules.Customers.Services.phone_codes` (PR 79). Re-exported
# here so legacy callers (the transfer-form context, autocomplete
# response shape) keep their existing import shape.
from api.Modules.Customers.Services import PHONE_COUNTRY_CODES

def sibling_store_ids(store_id):
    """Owner-umbrella resolution. Single source of truth lives in
    `api.Modules.Customers.Repositories`; this Flask-scoped helper
    just delegates so legacy callers (transfer routes, recent-recipients,
    superadmin reports) keep their existing call shape during the
    migration window."""
    from api.Modules.Customers.Repositories import sibling_store_ids as _impl
    return _impl(db.session, store_id)

def find_or_upsert_customer(store_id, full_name, phone_country, phone_number,
                             address="", dob=None, customer_id=None):
    """Return the Customer row for this sender, creating / updating as needed.

    Lookup priority:
      1. explicit customer_id — only accepted if the target Customer lives
         in one of the current store's sibling stores (owner umbrella);
      2. (phone_country, phone_number) across the owner umbrella — a match
         in any sibling store is reused so repeat senders get one record
         per person per owner, not per store;
      3. otherwise create a new record pinned to the current store_id.

    Any non-empty argument overwrites the stored value — last write wins,
    so the customer record always tracks the latest info a cashier saw
    anywhere in the owner's portfolio.
    """
    from api.Modules.Customers.Services import upsert as _customers_upsert
    return _customers_upsert(
        db.session, store_id, full_name, phone_country, phone_number,
        address=address, dob=dob, customer_id=customer_id,
    )

# /api/customers/search + /api/customers/<int:cid>/recent-recipients
# moved to blueprints/customers_api.py (D2 phase 13).

# ── Transfers ────────────────────────────────────────────────
# Sort-column whitelist moved to api.Modules.Transfers.Repositories.transfers
# (PR 13). The Flask /transfers route delegates filter parsing + sort
# resolution + pagination to the Service layer.


# /transfers moved to blueprints/transfers_redirects.py (D2 phase 14).






# Fields whose changes are interesting to surface in the audit log summary.
# Sender PII edits are included (addr/phone/dob) since the customer directory
# propagates them across sibling stores and admins want to see who edited.
# Transfer audit-log helpers + the audited-fields registry now
# live in api.Modules.Transfers.Services.audit (PR 77). The
# legacy name is re-exported so any tooling that imported
# `_TRANSFER_AUDIT_FIELDS` directly keeps working during the
# strangler-fig migration window.
from api.Modules.Transfers.Services import (
    TRANSFER_AUDIT_FIELDS as _TRANSFER_AUDIT_FIELDS,
)

# Service types other than Money Transfer don't carry the 1% federal tax —
# bill payments, top-ups, and recharges aren't ACH-withdrawal flows where
# tax would be remitted. The transfer form's dropdown options must match
# this set exactly. Server-side check is the gate; the JS preview just
# mirrors the same rule for live feedback.
# Service type / tax constants + helpers now live in
# api.Modules.Transfers.Services.tax (PR 76). The legacy names
# below are re-exports / wrappers so existing call sites
# (new_transfer, edit_transfer, _transfer_form_ctx, the JS
# preview's hidden-form keys, the dropdown population) keep
# their shape during the strangler-fig migration window.
from api.Modules.Transfers.Services import (
    DOMESTIC_COUNTRIES as _DOMESTIC_COUNTRIES,
    SERVICE_TYPES,
    TAX_EXEMPT_SERVICES as _TAX_EXEMPT_SERVICES,
    TRANSFER_COUNTRIES,
)











# /transfers/new + /transfers/<int>/edit + /transfers/<int>/delete
# moved to blueprints/transfers_redirects.py (D2 phase 14).


# ── Daily Book ───────────────────────────────────────────────
# Companies a new store can pick from on the settings page. The daily book
# and transfer form both pull per-store from Store.companies (resolved via
# store_mt_companies), so this is only the catalog — not a hardcoded list.
# Money-transfer company list resolution now lives in
# api.Modules.Transfers.Services.companies (PR 80). Re-exports
# below preserve the legacy import shape during the migration
# window.
from api.Modules.Transfers.Services import (
    DEFAULT_MT_COMPANIES,
    store_mt_companies,
)

# /daily moved to blueprints/bookkeeping_redirects.py (D2 phase 15).









# Generic line-item kinds that sum into a single DailyReport field.
# Each entry: (daily_report_field, singular_label, plural_label_for_count).
# Adding a new kind is: one line here + one disclosure widget on the
# daily-report template + removing the field from _DAILY_REPORT_FIELDS.
# Daily-book line-item kind registry now lives in
# api.Modules.DailyBook.Services.kinds (PR 68). The legacy names
# below are re-exports / wrappers so existing call sites
# (daily-report routes, _bank_category_label, monthly P&L feed)
# keep their shape during the strangler-fig migration window.
from api.Modules.DailyBook.Services import (
    LINE_ITEM_KINDS as _LINE_ITEM_KINDS,
    kind_or_404 as _line_item_kind_or_404,
)


# Fields on DailyReport the main form still edits. Derived fields
# (outside_cash_drops, checks_deposit, and every DailyReport field
# in _LINE_ITEM_KINDS) are intentionally omitted — each is recomputed
# from its own line-item rows.

# /daily/<ds> (GET, POST) moved to
# blueprints/bookkeeping_mutations.py (D2 phase 26).




# /daily/<ds>/line-items/<kind>/{new,/<id>/delete},
# /daily/<ds>/{lock,unlock} moved to
# blueprints/bookkeeping_mutations.py (D2 phase 26).


# ── Monthly P&L ──────────────────────────────────────────────
# /monthly + /monthly/<y>/<m> + /monthly/new moved to
# blueprints/bookkeeping_redirects.py (D2 phase 15).


# ── Return Checks ────────────────────────────────────────────
#
# Replaces the legacy "Return Check (G/L)" hand-edited line on the
# monthly P&L. Cashiers now log every bounced check here and mark each
# one recovered / loss / fraud — the P&L pulls the netted G/L for the
# month automatically (locked field, like check_cashing_fees).
#
# Pending balance and aging come straight off the same table, so the
# admin list page + owner dashboard share queries.







def _bank_charges_for_month(store_id, year, month, category_slug=None,
                             *, prefix=None):
    """Sum the absolute amount of BankTransactions tagged for the given
    month. Single source of truth lives in
    `api.Modules.BankSync.Services.bank_charges_for_month` (PR 57).
    """
    from api.Modules.BankSync.Services import bank_charges_for_month as _svc
    return _svc(db.session, store_id, year, month, category_slug,
                prefix=prefix)


def _return_check_monthly_pl(store_id, year, month):
    """Signed value for the monthly P&L's Return Check (G/L) line,
    using EXPENSE convention. Single source of truth lives in
    `api.Modules.Owners.Services.return_check_monthly_pl` (PR 62).
    """
    from api.Modules.Owners.Services import return_check_monthly_pl
    return return_check_monthly_pl(db.session, store_id, year, month)




# ── ACH Batches ──────────────────────────────────────────────


# /batches[/new|/<bid>/edit] moved to
# blueprints/bookkeeping_redirects.py (D2 phase 15).


# /batches/<bid>/transfers moved to
# blueprints/bookkeeping_redirects.py (D2 phase 15).

# ── Bank (Stripe Financial Connections) ─────────────────────────
# /bank moved to blueprints/bank_redirects.py (D2 phase 16).

# /bank/stripe/{connect,return,refresh,sync-transactions,nickname/<id>,disconnect/<id>},
# /bank/transactions/<id>/{categorize,uncategorize,move-date},
# /bank/rules/{new,<id>/edit,<id>/toggle,<id>/delete} moved to
# blueprints/bank_mutations.py (D2 phase 27).

# ── Admin Users ──────────────────────────────────────────────
# /admin/users[/new|/<uid>/edit] + /admin/audit-log moved to
# blueprints/admin_redirects.py (D2 phase 17).

# /admin/settings (GET, POST) moved to
# blueprints/admin_settings_form.py (D2 phase 29).

# /admin/settings/{roster/add, roster/<id>/toggle, roster/<id>/rename,
# team/<uid>, owner/redeem} moved to
# blueprints/admin_settings_mutations.py (D2 phase 24).


# ── Superadmin ───────────────────────────────────────────────
# /superadmin/stores + /superadmin/stores/new moved to
# blueprints/superadmin_redirects.py (D2 phase 18).

# /superadmin/impersonate/<store_id> moved to
# blueprints/superadmin_extras.py (D2 phase 28).


# /superadmin/stop-impersonation moved to
# blueprints/superadmin_extras.py (D2 phase 28).


# ── Superadmin control panel ─────────────────────────────────

# /superadmin/controls moved to blueprints/superadmin_redirects.py (D2 phase 18).

# /superadmin/send-test-email moved to
# blueprints/superadmin_extras.py (D2 phase 28).


# ── Per-store actions (superadmin) ───────────────────────────





# /superadmin/stores/<int:store_id>/{extend-trial,comp-plan,toggle-active,
# extend-retention,revert-to-trial,addons/<key>/toggle} moved to
# blueprints/superadmin_store_mutations.py (D2 phase 22).

# ── TV catalog admin (superadmin) ────────────────────────────
#
# Curate the dropdown options operators see in the country editor:
# add new MT companies / banks, rename existing ones (display_name
# only — slugs are immutable), upload nominative-use logos, and
# soft-deactivate retired entries. Companies are global; banks are
# scoped to a country (ISO-2).


# /superadmin/tv-catalog/<type>/<slug>/logo moved to
# blueprints/superadmin_extras.py (D2 phase 28).


# /superadmin/tv-catalog/<type>/<slug>/edit moved to
# blueprints/superadmin_extras.py (D2 phase 28).





# /superadmin/tv-catalog/new moved to
# blueprints/superadmin_extras.py (D2 phase 28).


# ── Discount codes (superadmin) ──────────────────────────────

# /superadmin/discounts/{new,<id>/toggle} +
# /superadmin/features/{new,<key>/toggle-global,
# <key>/stores/<store_id>} +
# /superadmin/announcements/{new,<id>/toggle,<id>/delete}
# moved to blueprints/superadmin_misc_mutations.py (D2 phase 23).

# /superadmin/controls/audit.csv moved to
# blueprints/superadmin_extras.py (D2 phase 28).


# ── Stripe webhook ───────────────────────────────────────────
# ── Resend webhook (delivery events) ─────────────────────────
#
# Resend posts events to this endpoint as each message moves through
# its lifecycle: sent → delivered → (opened → clicked) OR (bounced |
# complained | delivery_delayed). We persist everything and react to
# two events that matter for sending hygiene:
#   - email.bounced with bounce.type=hard → stamp User.email_bounced_at
#     so future _send_email calls skip the address.
#   - email.complained → same stamp, plus flip every notify_* toggle
#     to False. A spam-report is the strongest "stop emailing me" signal
#     a user can send short of unsubscribing.
#
# Resend signs webhook requests using Svix-style headers
# (svix-id, svix-timestamp, svix-signature). Secret is a whsec_...
# string set via RESEND_WEBHOOK_SECRET. We verify with HMAC-SHA256
# over `{id}.{timestamp}.{raw_body}` and reject mismatches with 400.

_RESEND_REPLAY_WINDOW_SECONDS = 5 * 60  # 5 minutes

def _verify_resend_signature(secret, svix_id, svix_timestamp, svix_signature,
                              raw_body):
    """Return True if `raw_body` carries a valid Svix signature under
    `secret`. `secret` is the whsec_... string Resend gave us.

    The signed value is `{id}.{timestamp}.{body}`. The sig header can
    contain multiple space-separated `v1,{base64}` entries (older keys
    after rotation); we accept any match.
    """
    if not (secret and svix_id and svix_timestamp and svix_signature):
        return False
    # Replay-window check — reject messages older than the window. Prevents
    # an attacker who captured a valid webhook from replaying it later.
    try:
        ts_int = int(svix_timestamp)
        now_int = int(datetime.utcnow().timestamp())
        if abs(now_int - ts_int) > _RESEND_REPLAY_WINDOW_SECONDS:
            return False
    except ValueError:
        return False
    # secret looks like "whsec_BASE64". Strip the prefix and decode.
    if not secret.startswith("whsec_"):
        return False
    try:
        secret_bytes = base64.b64decode(secret[len("whsec_"):])
    except Exception:
        return False
    signed_payload = f"{svix_id}.{svix_timestamp}.".encode() + raw_body
    expected = hmac.new(secret_bytes, signed_payload, hashlib.sha256).digest()
    expected_b64 = base64.b64encode(expected).decode()
    # Header may carry multiple versions: "v1,sig1 v1,sig2"
    for sig in svix_signature.split():
        if "," not in sig:
            continue
        version, value = sig.split(",", 1)
        if version != "v1":
            continue
        if hmac.compare_digest(value, expected_b64):
            return True
    return False

def _apply_resend_side_effects(event_type, to_addr, bounce_type):
    """For a bounce/complaint event, stamp the matching User row. For
    a complaint, also flip every notify_* toggle off — the user is
    actively telling receivers this was spam."""
    if not to_addr:
        return
    users = (db.session.query(User)
             .filter(db.func.lower(User.email) == to_addr.lower())
             .all())
    if not users:
        return
    now = datetime.utcnow()
    for u in users:
        if event_type == "email.bounced" and bounce_type == "hard":
            u.email_bounced_at = now
        elif event_type == "email.complained":
            u.email_bounced_at = now
            u.notify_trial_reminders = False
            u.notify_announcement_email = False
            u.notify_locked_day_digest = False
            # Future notify_* columns should be flipped here too.

# ── Data retention purge ─────────────────────────────────────
# Per-store model registry + retention-purge implementation now
# live in api.Modules.Billing.Services.retention (PR 64). The
# legacy names below are re-exported / wrapped so any operator
# tool that imported them by name keeps working during the
# strangler-fig migration window.
from api.Modules.Billing.Services import (
    STORE_FK_OVERRIDES as _STORE_FK_OVERRIDES,
    STORE_OWNED_MODELS as _STORE_OWNED_MODELS,
)


def purge_expired_stores():
    """Hard-delete inactive stores whose retention window has elapsed.

    Single source of truth lives in
    `api.Modules.Billing.Services.purge_expired_stores`. Per
    CLAUDE.md invariant #4 the retention window is 180 days; this
    CLI walks every store past that window.

    Uses plain SQLAlchemy via ``SessionLocal()`` so the function
    runs cleanly outside any Flask request context (CLI + tests
    both call it directly). The Service commits internally; the
    outer ``with`` block closes the session on exit.
    """
    from api.Modules.Billing.Services import purge_expired_stores as _svc
    from api.Core.Database import SessionLocal
    with SessionLocal() as s:
        return _svc(s)

@app.cli.command("purge-expired-stores")
def purge_expired_stores_cmd():
    """Delete inactive stores past their retention deadline. Run daily."""
    n = purge_expired_stores()
    print(f"Purged {n} expired store(s).")

# ── Trial-reminder emails ───────────────────────────────────
#
# send_trial_reminders() is the only notification sender v1 ships
# beyond the password-reset one at /forgot-password. It runs daily
# via `flask send-trial-reminders` (hook to cron alongside
# purge-expired-stores). Logic:
#
#   - Find every store in "expiring_soon" status (trial ends within
#     3 days — see get_trial_status).
#   - Skip stores already stamped trial_reminder_sent_at.
#   - For each, find admin/owner users who (a) have `email` set,
#     (b) have `notify_trial_reminders` True. Send them an email
#     with the trial end date + a subscribe CTA.
#   - Stamp trial_reminder_sent_at on the store so we don't resend
#     tomorrow. Cleared on resubscribe by the Stripe webhook so a
#     second trial (post-reactivation) gets its own fresh reminder.

# Trial-reminder eligibility queries + subject/body templates now
# live in api.Modules.Notifications.Services.trial_reminders
# (PR 65). The Flask-bound rendering + delivery (render_template,
# _send_email, request-context fabrication for cron) stay here.
from api.Modules.Notifications.Services import (
    TRIAL_REMINDER_BODY as _TRIAL_REMINDER_BODY,
    TRIAL_REMINDER_SUBJECT as _TRIAL_REMINDER_SUBJECT,
    eligible_recipients as _trial_reminder_recipients_svc,
    stores_due_for_reminder as _stores_due_for_reminder,
)


def send_trial_reminders(now=None, base_url=None):
    """Back-compat wrapper. Canonical source of truth:
    ``api.Modules.Notifications.Services.trial_reminders.run``.

    Opens its own ``SessionLocal`` because callers (the Flask CLI +
    legacy ad-hoc invocations) don't carry a session in. Returns
    the count of emails sent — same contract as before.
    """
    from api.Core.Database import SessionLocal
    from api.Modules.Notifications.Services.trial_reminders import (
        run as _svc_run,
    )

    with SessionLocal() as s:
        return _svc_run(s, now=now, base_url=base_url)


@app.cli.command("send-trial-reminders")
def send_trial_reminders_cmd():
    """Email admins/owners of stores in expiring_soon. Run daily."""
    n = send_trial_reminders()
    print(f"Sent {n} trial reminder email(s).")


# ── Locked-day digest email ──────────────────────────────────
#
# `send_locked_day_digest(report)` is the fan-out. Called from the
# FastAPI lock endpoint immediately after a successful lock + audit
# write. We do NOT stamp a "digest_sent" flag — re-locking after an
# unlock + edit cycle is a legitimate trigger (a corrected close-out)
# and the audit already records the state transition.
#
# Recipients + static body live in
# api.Modules.Notifications.Services.locked_day_digest. Email
# delivery + Flask render glue stay here so the Service stays pure.

def send_locked_day_digest(report, base_url: str | None = None) -> int:
    """Back-compat wrapper. Canonical source of truth:
    ``api.Modules.Notifications.Services.locked_day_digest.run``.

    Called from the FastAPI lock endpoint with the current
    ``db.session`` — passes through to the Service ``run()``.
    """
    from api.Modules.Notifications.Services.locked_day_digest import (
        run as _svc_run,
    )
    return _svc_run(db.session, report, base_url=base_url)

# ── Announcement broadcast email ─────────────────────────────
#
# `broadcast_announcement(announcement_id)` is the sender. Called:
#   1) Inline from POST /superadmin/announcements/new when the
#      superadmin tickcd the broadcast checkbox.
#   2) Ad-hoc via `flask broadcast-announcement <id>` — lets us
#      resend if the first run partially failed, since the sender is
#      idempotent on broadcast_sent_at.
#
# Recipient filter:
#   - User.is_active = True
#   - User.email != ''
#   - User.notify_announcement_email = True (opt-in; default False)
#   - User.email_bounced_at IS NULL (suppression, from PR A)
# Each send goes through _send_email() which also runs the suppression
# check — belt-and-suspenders so a race (bounce arrives mid-broadcast)
# still protects the sender.

def broadcast_announcement(announcement_id, base_url=None):
    """Back-compat wrapper. Canonical source of truth:
    ``api.Modules.Notifications.Services.broadcasts.run``.

    Opens its own ``SessionLocal`` because callers (the Flask CLI +
    a few legacy in-app callers) don't carry a session in. Returns
    the count of emails attempted — same contract as before.
    """
    from api.Core.Database import SessionLocal
    from api.Modules.Notifications.Services.broadcasts import run as _svc_run

    with SessionLocal() as s:
        return _svc_run(s, announcement_id, base_url=base_url)

@app.cli.command("broadcast-announcement")
@click.argument("announcement_id", type=int)
def broadcast_announcement_cmd(announcement_id):
    """Resend an announcement email (no-op if already broadcast)."""
    n = broadcast_announcement(announcement_id)
    print(f"Broadcast announcement {announcement_id}: {n} email(s) sent.")

@app.cli.command("reset-superadmin")
@click.argument("username", required=False)
@click.option("--reset-2fa", is_flag=True,
              help="Also wipe TOTP secret + recovery codes, forcing fresh enrollment.")
def reset_superadmin_cmd(username, reset_2fa):
    """Reset a superadmin's password (and optionally their 2FA). Run from
    the Render shell. Prompts for the new password; doesn't touch
    non-superadmin accounts. This is the recovery path for a locked-out
    superadmin, since /forgot-password intentionally skips the role."""
    q = db.session.query(User).filter_by(role="superadmin")
    if username:
        q = q.filter_by(username=username.strip())
    sa = q.first()
    if not sa:
        click.echo("No superadmin found" +
                   (f" with username={username!r}." if username else "."))
        return
    click.echo(f"Resetting password for superadmin: {sa.username}")
    pw = click.prompt("New password", hide_input=True, confirmation_prompt=True)
    if len(pw) < 8:
        click.echo("Password must be at least 8 characters. Aborting.")
        return
    sa.set_password(pw)
    if reset_2fa:
        sa.totp_secret = None
        sa.totp_enrolled_at = None
        db.session.query(RecoveryCode).filter_by(user_id=sa.id).delete()
        click.echo("2FA wiped — re-enrollment will be forced on next login.")
    db.session.commit()
    click.echo("Done.")

# ── Amazon Appstore reviewer seed ────────────────────────────
#
# The DineroBook TV Fire TV app gates pairing on the tv_display
# add-on. Amazon's reviewers don't have a paid subscription, so
# without a comped account they'd hit the addon gate and fail
# review with "couldn't pair." This CLI provisions (or refreshes)
# a single sandbox store and employee user with the addon comped
# and a few sample rates pre-seeded, so the reviewer:
#   1. Logs in at /login/amazon-reviewer with the printed creds.
#   2. Lands on /dashboard, navigates to TV Display in the sidebar.
#   3. Clicks "Generate code" on /tv-display.
#   4. Pairs the test Fire TV — sees a populated rate board.
#
# Idempotent: re-running rotates the password, refreshes plan +
# addons, and tops off any missing sample data. Safe to schedule
# via cron if you ever want pre-review password rotation.

# seed-amazon-reviewer body moved to scripts/seed_amazon_reviewer.py.
# The Flask CLI command here is a thin back-compat shim — operators
# running ``flask seed-amazon-reviewer`` get the same behaviour as
# ``python -m scripts.seed_amazon_reviewer``.
@app.cli.command("seed-amazon-reviewer")
@click.option("--password", default=None,
              help="Override the auto-generated password (>= 12 chars). "
                   "Omit to generate a fresh URL-safe random.")
@click.option("--keep-data", is_flag=True,
              help="Don't reseed sample countries/banks/rates if any "
                   "already exist — useful for in-place password rotation.")
def seed_amazon_reviewer_cmd(password, keep_data):
    """Delegate to the standalone script's main()."""
    from scripts.seed_amazon_reviewer import main as _main
    argv: list[str] = []
    if password is not None:
        argv += ["--password", password]
    if keep_data:
        argv.append("--keep-data")
    rc = _main(argv)
    if rc != 0:
        raise click.Abort()

# 404 + 500 error handlers moved to blueprints/errors.py (D2).
from blueprints import errors as _bp_errors  # noqa: E402
_bp_errors.register(app, current_user)


# Bootstrap helpers (indexes safety-net, legacy table drops, feature-flag
# seed, one-shot legacy data migrations, Alembic upgrade) live in
# ``api.Core.Bootstrap``. The shims below preserve the legacy
# ``from app import _X`` import paths used by a handful of tests.
from api.Core.Bootstrap import (  # noqa: E402
    ADDED_INDEXES as _ADDED_INDEXES,
    DEFAULT_FEATURE_FLAGS as _DEFAULT_FEATURE_FLAGS,
    DROPPED_TABLES as _DROPPED_TABLES,
)


def _ensure_added_indexes():
    from api.Core.Bootstrap import ensure_added_indexes
    ensure_added_indexes(db.engine, app.logger)












def init_db():
    from api.Core.Bootstrap import (
        apply_schema as _bs_apply_schema,
        drop_legacy_tables as _bs_drop_legacy,
        ensure_added_indexes as _bs_ensure_indexes,
        migrate_legacy_line_item_tables as _bs_migrate_line_items,
        rename_maxi_transfer_to_maxi as _bs_rename_maxi,
        seed_feature_flags as _bs_seed_flags,
    )
    with app.app_context():
        # Alembic builds + upgrades the schema. No db.create_all,
        # no _ADDED_COLUMNS — every schema change is a revision.
        _bs_apply_schema(db.engine, app.logger)
        _bs_ensure_indexes(db.engine, app.logger)
        _bs_drop_legacy(db.engine, app.logger)
        _bs_rename_maxi(db.session, app.logger)
        # One-time copy of legacy DailyDrop + CheckDeposit rows into
        # the generic DailyLineItem table. Idempotent — safe on every
        # boot, no-op once the data has been migrated.
        try:
            _bs_migrate_line_items(db.session)
        except Exception as e:
            app.logger.warning(f"Legacy line-item migration skipped: {e}")
        _bs_seed_flags(db.session)
        # TV-display catalog seed (curated company/bank pickers,
        # drop-in logo import, country-code backfill) lives in
        # ``api.Modules.TVDisplay.Services.seed`` now. The Service is
        # fully session-driven; pass ``db.session`` + the Flask app
        # root path so the disk-scan finds ``static/seed-logos/``.
        try:
            from api.Modules.TVDisplay.Services.seed import run as _seed_tv
            n_imported = _seed_tv(db.session, app.root_path)
            if n_imported:
                app.logger.info(f"Imported {n_imported} TV logos from static/seed-logos/.")
        except Exception as e:
            app.logger.warning(f"TV catalog seed skipped: {e}")
        if not db.session.query(User).filter_by(username="superadmin",store_id=None).first():
            sa=User(username="superadmin",full_name="Platform Owner",role="superadmin",store_id=None)
            sa.set_password(os.environ.get("SUPERADMIN_PASSWORD","super2025!")); db.session.add(sa); db.session.commit()
            print("✅ Superadmin: superadmin / super2025!")
        # No demo store on fresh boot — this is a live SaaS, the operator
        # creates their own stores. The superadmin seed above is the only
        # row a fresh DB needs. (2FA is mandatory and enforced at login.)

# Skip the boot-time DB init when invoked from Alembic — env.py
# imports `app` purely to harvest `db.metadata`, and running
# init_db() would populate the same DB Alembic is about to diff
# against (yielding an empty migration). The env var is unset
# everywhere else.
if not os.environ.get("DINEROBOOK_SKIP_INIT_DB"):
    init_db()

# ── FastAPI + SPA strangler-fig dispatcher ──────────────────────
#
# SPA shell + Vite-built assets live in ``frontend/dist/`` and are
# served by the Starlette app in ``api/spa.py`` — mounted below
# at ``/app`` via DispatcherMiddleware so Flask's pytest
# ``test_client`` reaches them. Production routing in ``asgi.py``
# forwards the same paths to ``spa_app`` natively (no WSGI hop).
#
# The new modular FastAPI backend (under api/) is being built
# alongside this Flask monolith per docs/architecture/MIGRATION_ADR.md.
# Routes under /api/v2/* are forwarded into the FastAPI app via
# Werkzeug's DispatcherMiddleware. Flask continues to handle /
# and the rest of the URL space unchanged.
#
# Wrapped in try/except so a broken FastAPI import doesn't break
# the Flask app — during early-stage migration, half the FastAPI
# routers may not exist yet.
#
# **Why this block still exists** even though production runs from
# `asgi.py` (uvicorn) and never traverses the inner a2wsgi bridge:
# the pytest suite uses Flask's `test_client()` and hits /api/v2/*
# URLs through this dispatcher. Tests are short-lived single-call
# requests, so the leaked-task pathology that crashed gunicorn
# workers in May 2026 doesn't manifest. Once every test moves to
# the ASGI client (httpx + ASGITransport on `asgi:asgi_app`), this
# block + the a2wsgi dependency can be deleted.
try:
    from api.main import api_app as _fastapi_app
    from api.spa import spa_app as _spa_app
    from a2wsgi import ASGIMiddleware
    from werkzeug.middleware.dispatcher import DispatcherMiddleware
    # /api/v2 → FastAPI; /app → Starlette SPA serving (frontend/dist).
    # Production routing in asgi.py bypasses this dispatcher entirely
    # for both paths — this mount only exists so Flask's test_client
    # can reach them in pytest. conftest.py swaps both ASGIMiddleware
    # wrappers for TestClient-backed bridges to avoid the a2wsgi
    # leaked-task pathology under coverage.
    app.wsgi_app = DispatcherMiddleware(
        app.wsgi_app,
        {
            "/api/v2": ASGIMiddleware(_fastapi_app),
            "/app":    ASGIMiddleware(_spa_app),
        },
    )
    app.logger.info(
        "FastAPI mounted at /api/v2 + SPA at /app (strangler-fig)"
    )
except Exception as _fastapi_err:
    # Don't break Flask boot if the new backend fails to import.
    # Log it loudly so it doesn't go unnoticed in dev.
    app.logger.warning(f"FastAPI mount skipped: {_fastapi_err}")


# Run CSRF exemption registration AFTER every @app.route + every
# Blueprint route + the FastAPI mount have settled. By this point
# `app.view_functions` is complete and the exempts can find every
# endpoint name they target. See `_csrf_exempt_endpoints` at the
# top of the file for the function body.
_csrf_exempt_endpoints()


if __name__=="__main__":
    # Dev server — uvicorn pointing at `asgi:asgi_app`, the same
    # entrypoint production uses (`render.yaml` startCommand:
    # `gunicorn asgi:asgi_app -k uvicorn.workers.UvicornWorker`).
    # This means dev /api/v2/* requests go through the native
    # ASGI path, NOT the in-app a2wsgi.ASGIMiddleware bridge.
    # Prod-parity is the point: any latency / lifecycle / cookie
    # surprise the cashier hits in prod shows up in dev too.
    #
    # Module-level imports above mounted the dispatcher onto
    # `app.wsgi_app` for the test suite's benefit — uvicorn ignores
    # it because we point it at `asgi:asgi_app`, not `app:app`.
    import uvicorn
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 DineroBook → http://0.0.0.0:{port}  (uvicorn/ASGI)")
    uvicorn.run(
        "asgi:asgi_app",
        host="0.0.0.0",
        port=port,
        # reload=False matches prod; flip via env if a contributor
        # wants hot-reload on file edits. The Vite dev server at
        # :5173 owns SPA hot-reload already so most edits don't
        # need a Python reload.
        reload=bool(os.environ.get("DEV_RELOAD")),
        log_level="info",
    )
