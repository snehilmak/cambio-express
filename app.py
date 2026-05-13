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
_TRIAL_EXEMPT = {
    # Subscribe flow
    "billing.subscribe",
    "billing.subscribe_checkout",
    "billing.subscribe_success",
    # Sign-out path
    "auth_redirects.logout",
    # Owner umbrella (per-store gate happens on the inner pages)
    "owner.owner_dashboard",
    "owner.owner_locations",
    "owner.owner_store_detail",
    "owner.owner_connect",
    "owner.owner_connect_generate",
    "owner.owner_connect_revoke",
    "owner.owner_unlink_store",
    # Manage-subscription surface
    "subscription.admin_subscription",
    "subscription.admin_subscription_billing_portal",
    "subscription.admin_subscription_toggle_addon",
    "subscription.admin_subscription_cancel",
    # Theme toggle (cosmetic, fine to reach even when expired)
    "account.account_theme",
}

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

def record_audit(action, target_type="", target_id="", details=""):
    """Append a row to the superadmin audit log.

    Safe to call from any request — reads the current user from
    session so it can stamp admin_name even if the User row is
    later deleted. Single source of truth lives in
    `api.Modules.Audit.Services.record_superadmin_action` (PR 52).
    """
    from api.Modules.Audit.Services import record_superadmin_action
    u = current_user()
    if not u:
        return
    return record_superadmin_action(
        db.session,
        admin_id=u.id,
        admin_name=u.full_name or u.username or "",
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
    )


def record_op_audit(action, target_type, target_id, *, label="", summary=""):
    """Append a row to the per-store operator audit log.

    Captures user identity + role from session so the audit row
    stays useful even after the User row is deleted. Single source
    of truth lives in
    `api.Modules.Audit.Services.record_operator_action` (PR 52).

    Target types: see the canonical list in
    `api.Modules.Audit.Services.recorder.record_operator_action`'s
    docstring. As of 2026-05 the set is 'transfer', 'daily_report',
    'batch', 'return_check', 'roster_member', 'user', 'owner_link'.

    Actions: 'create', 'update', 'delete', 'lock', 'unlock',
    'reactivate', 'deactivate', 'rename', 'mark_loss', 'mark_fraud',
    'reopen', 'payment', 'delete_payment', 'reset_password',
    'connect'.
    """
    from api.Modules.Audit.Services import record_operator_action
    sid = session.get("store_id")
    if not sid:
        return
    u = current_user()
    if not u:
        return
    return record_operator_action(
        db.session,
        store_id=sid,
        user_id=u.id,
        user_name=u.full_name or u.username or "",
        user_role=u.role or "",
        target_type=target_type,
        target_id=target_id,
        target_label=label,
        action=action,
        summary=summary,
    )

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

def stripe_health_check():
    """Return a dict describing the Stripe integration state.

    Single source of truth lives in
    `api.Modules.Billing.Services.check_stripe_integration` (PR 53).
    Used by the superadmin Overview tab to surface env-var
    presence, account reachability, per-price validation, key-mode
    pairing, and Financial Connections availability.
    """
    from api.Modules.Billing.Services import check_stripe_integration
    return check_stripe_integration()

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


def _compute_platform_anomalies():
    """Aggregate every anomaly rule into a single ranked list.

    Single source of truth lives in
    `api.Modules.Superadmin.Services.compute_platform_anomalies`
    (PR 60). The Service hands back the same dict shape the
    superadmin Overview tab expects, so templates render
    bit-for-bit identical badges.
    """
    from api.Modules.Superadmin.Services import compute_platform_anomalies
    return compute_platform_anomalies(db.session)


def _superadmin_dashboard_context():
    """Platform-wide BI metrics for the superadmin Dashboard.
    Single source of truth lives in
    `api.Modules.Superadmin.Services.superadmin_dashboard_context`
    (PR 75). Returns the kwargs dict
    `dashboard_superadmin.html` expects.
    """
    from api.Modules.Superadmin.Services import (
        superadmin_dashboard_context,
    )
    return superadmin_dashboard_context(db.session)


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
def login_required(f):
    return f


def admin_required(f):
    return f


def superadmin_required(f):
    return f


def owner_required(f):
    return f


def pro_required(f):
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
BANK_BALANCE_STALE_SECONDS = 600  # 10 minutes
# Hard cap on linked bank accounts per store. Two is enough for the
# typical MSB workflow (e.g., a checking account + an MSB-restricted
# account at the same credit union). Disconnecting frees the slot.
MAX_BANK_ACCOUNTS_PER_STORE = 2
# Cost-control on Stripe Transaction.list (billed per call).
# Manual syncs are capped at MAX_BANK_SYNCS_PER_DAY and must be
# BANK_SYNC_COOLDOWN_MINUTES apart. Initial-connect auto-sync does not
# count against the cap.
BANK_SYNC_COOLDOWN_MINUTES = 15
MAX_BANK_SYNCS_PER_DAY = 5
# How many days back to pull on initial connect. Per-product
# decision: yesterday + today only — minimal cost, still catches
# any same-day deposits that haven't been entered into the daily
# book. The constant now lives in
# api.Modules.BankSync.Services.sync (PR 72); re-exported here
# so legacy callers keep their import shape during migration.
from api.Modules.BankSync.Services import INITIAL_SYNC_DAYS_BACK

def stripe_is_configured():
    """We can only start an FC session if Stripe is wired up.

    Single source of truth lives in
    `api.Modules.Billing.Services.stripe_is_configured` (PR 54).
    """
    from api.Modules.Billing.Services import stripe_is_configured as _svc
    return _svc()

def stripe_publishable_key():
    """The pk_test_/pk_live_ key the browser uses to load Stripe.js.

    Single source of truth lives in
    `api.Modules.Billing.Services.stripe_publishable_key` (PR 54).
    """
    from api.Modules.Billing.Services import stripe_publishable_key as _svc
    return _svc()

def stripe_mode():
    """'live' / 'test' / '' depending on STRIPE_SECRET_KEY.

    Single source of truth lives in
    `api.Modules.Billing.Services.stripe_mode` (PR 54).
    """
    from api.Modules.Billing.Services import stripe_mode as _svc
    return _svc()

def _stripe_price_ids():
    """Resolve {plan_key: price_id} for all four plan tiers. Single
    source of truth lives in
    `api.Modules.Billing.Services.resolve_price_ids` (PR 43); this
    Flask-scope wrapper exists so the legacy callers (subscribe page,
    webhook handler, health check) keep their existing call shape."""
    from api.Modules.Billing.Services import resolve_price_ids
    return resolve_price_ids()

def ensure_stripe_customer(store):
    """Return a Stripe customer id for this store, creating one if needed.

    Single source of truth lives in
    `api.Modules.Billing.Services.ensure_stripe_customer` (PR 56).
    Self-heals when the cached id was created in a different
    Stripe mode (e.g. test → live migration).
    """
    from api.Modules.Billing.Services import ensure_stripe_customer as _svc
    return _svc(db.session, store)

def _upsert_fc_account(store_id, api_obj):
    """Persist (or refresh) a FinancialConnectionsAccount into our
    cache. Single source of truth lives in
    `api.Modules.BankSync.Services.upsert_fc_account` (PR 73).
    """
    from api.Modules.BankSync.Services import upsert_fc_account
    return upsert_fc_account(db.session, store_id, api_obj)


def refresh_bank_balances(store):
    """Pull fresh balances for every enabled account on the store.
    Single source of truth lives in
    `api.Modules.BankSync.Services.refresh_bank_balances` (PR 73).

    Returns `(updated_count, error_message_or_empty)`.
    """
    from api.Modules.BankSync.Services import refresh_bank_balances
    return refresh_bank_balances(db.session, store)

def _can_sync_bank_transactions(store, now=None):
    """Rate-limit gate for manual bank-transaction syncs.

    Returns (allowed, reason, retry_after_seconds). Resets the daily
    counter lazily when a new UTC day rolls over.
    """
    now = now or datetime.utcnow()
    today = now.date()
    if store.bank_sync_count_date != today:
        # Lazy daily reset. Caller commits after recording the sync.
        store.bank_sync_count_today = 0
        store.bank_sync_count_date = today
    if (store.bank_sync_count_today or 0) >= MAX_BANK_SYNCS_PER_DAY:
        return (False,
                f"Daily limit reached ({MAX_BANK_SYNCS_PER_DAY} syncs). Resets at midnight UTC.",
                0)
    if store.bank_sync_last_at:
        elapsed = (now - store.bank_sync_last_at).total_seconds()
        cooldown = BANK_SYNC_COOLDOWN_MINUTES * 60
        if elapsed < cooldown:
            wait = int(cooldown - elapsed)
            mins = max(1, (wait + 59) // 60)
            return (False,
                    f"Please wait {mins} more minute(s) between syncs.",
                    wait)
    return True, "", 0

def _record_bank_sync(store, now=None):
    """Bump the rate-limit counters. Caller commits."""
    now = now or datetime.utcnow()
    today = now.date()
    if store.bank_sync_count_date != today:
        store.bank_sync_count_today = 0
        store.bank_sync_count_date = today
    store.bank_sync_count_today = (store.bank_sync_count_today or 0) + 1
    store.bank_sync_last_at = now

def _upsert_bank_transaction(store_id, account_row, api_obj):
    """Persist (or refresh) a Stripe FC Transaction into our cache.
    Single source of truth lives in
    `api.Modules.BankSync.Services.upsert_bank_transaction` (PR 72).
    """
    from api.Modules.BankSync.Services import upsert_bank_transaction
    return upsert_bank_transaction(
        db.session, store_id, account_row, api_obj,
    )

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
_BANK_CATEGORY_PL_FIELD = {}


def _bank_category_label(slug):
    """Operator-friendly label for a category slug. Single source
    of truth lives in
    `api.Modules.BankSync.Services.bank_category_label` (PR 69).
    """
    from api.Modules.BankSync.Services import bank_category_label
    return bank_category_label(slug)


def _is_valid_bank_category(slug, store_id):
    """True iff `slug` is an acceptable target for a manual bank-
    transaction tag or a BankRule. Single source of truth lives in
    `api.Modules.BankSync.Services.is_valid_bank_category` (PR 69).
    """
    from api.Modules.BankSync.Services import is_valid_bank_category
    return is_valid_bank_category(db.session, slug, store_id)


def _bank_category_groups(store_id=None):
    """Grouped dropdown options for the bank-category picker.
    Single source of truth lives in
    `api.Modules.BankSync.Services.bank_category_groups` (PR 69).
    """
    from api.Modules.BankSync.Services import bank_category_groups
    return bank_category_groups(db.session, store_id)


def _is_daily_book_kind(slug):
    """True iff `slug` is a registered DailyBook line-item kind.
    Single source of truth lives in
    `api.Modules.BankSync.Services.is_daily_book_kind` (PR 69).
    """
    from api.Modules.BankSync.Services import is_daily_book_kind
    return is_daily_book_kind(slug)

def _bank_rule_matches(rule, txn):
    """True iff every set condition on `rule` matches `txn`.
    Single source of truth lives in
    `api.Modules.BankSync.Services.rule_matches` (PR 70)."""
    from api.Modules.BankSync.Services import rule_matches
    return rule_matches(rule, txn)


def _find_matching_rule(store_id, txn):
    """First enabled rule (lowest priority first) that matches.
    Single source of truth lives in
    `api.Modules.BankSync.Services.find_matching_rule` (PR 70)."""
    from api.Modules.BankSync.Services import find_matching_rule
    return find_matching_rule(db.session, store_id, txn)

def _apply_rules_to_uncategorized_row(row, account, *, allow_auto_post):
    """Run the rule chain (operator BankRule → built-in) against
    an uncategorised bank transaction and tag it. Single source of
    truth lives in
    `api.Modules.BankSync.Services.apply_rules_to_uncategorized_row`
    (PR 71).
    """
    from api.Modules.BankSync.Services import (
        apply_rules_to_uncategorized_row,
    )
    return apply_rules_to_uncategorized_row(
        db.session, row, account, allow_auto_post=allow_auto_post,
    )


def _categorize_bank_transaction(txn, target_kind, rule=None,
                                  post_to_daily=True, report_date=None):
    """Flask-side adapter for the categorize Service. Caller commits.

    Single source of truth lives in
    `api.Modules.BankSync.Services.categorize_transaction` (PR 36);
    this wrapper forwards `db.session` + the legacy
    `_is_daily_book_kind` predicate so the existing call sites keep
    their shape during the migration window.
    """
    from api.Modules.BankSync.Services import categorize_transaction
    return categorize_transaction(
        db.session, txn, target_kind,
        rule=rule, post_to_daily=post_to_daily,
        report_date=report_date,
        is_daily_book_kind=_is_daily_book_kind,
    )

def _uncategorize_bank_transaction(txn):
    """Flask-side adapter for the uncategorize Service. Caller commits."""
    from api.Modules.BankSync.Services import uncategorize_transaction
    return uncategorize_transaction(db.session, txn)

def sync_bank_transactions(store, since=None, until=None):
    """Pull transactions from every enabled FC account on the store.
    Single source of truth lives in
    `api.Modules.BankSync.Services.sync_bank_transactions` (PR 72).

    Returns `(new_rows, total_seen, last_error)`.
    """
    from api.Modules.BankSync.Services import sync_bank_transactions
    return sync_bank_transactions(db.session, store, since, until)


def _migrate_generic_bank_charge_per_account(store_id):
    """One-shot legacy migration of generic `bank_charge` rows.
    Single source of truth lives in
    `api.Modules.BankSync.Services.migrate_generic_bank_charge_per_account`
    (PR 72)."""
    from api.Modules.BankSync.Services import (
        migrate_generic_bank_charge_per_account,
    )
    return migrate_generic_bank_charge_per_account(db.session, store_id)


def _backfill_uncategorized_rows(store_id):
    """Run the rule chain against every uncategorised BankTransaction
    in the store. Single source of truth lives in
    `api.Modules.BankSync.Services.backfill_uncategorized_rows`
    (PR 72)."""
    from api.Modules.BankSync.Services import (
        backfill_uncategorized_rows,
    )
    return backfill_uncategorized_rows(db.session, store_id)


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


def push_enabled() -> bool:
    """Single source of truth lives in
    `api.Modules.Notifications.Services.push_is_enabled` (PR 67)."""
    from api.Modules.Notifications.Services import push_is_enabled
    return push_is_enabled()


def send_push(user_id: int, title: str, body: str = "",
              url: str = "/", tag: str | None = None) -> int:
    """Deliver a push notification to every device the user has
    subscribed. Single source of truth lives in
    `api.Modules.Notifications.Services.send_push` (PR 67).
    """
    from api.Modules.Notifications.Services import send_push as _svc
    return _svc(db.session, user_id, title, body, url, tag)

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


def _new_referral_code():
    """Mint an 8-char uppercase alphanumeric referral code.

    Single source of truth lives in
    `api.Modules.Billing.Services.new_referral_code` (PR 50).
    """
    from api.Modules.Billing.Services import (
        new_referral_code as _svc_new_referral_code,
    )
    return _svc_new_referral_code(db.session)

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

def apply_pending_referral_credits(referee_store):
    """Apply Stripe customer-balance credits on the referee's paid
    conversion + record a ReferralRedemption row so webhook retries
    can't double-credit.

    Single source of truth lives in
    `api.Modules.Billing.Services.apply_pending_referral_credits`
    (PR 51). Caller commits — same transactional contract as
    before.
    """
    from api.Modules.Billing.Services import (
        apply_pending_referral_credits as _svc_apply_pending,
    )
    return _svc_apply_pending(db.session, referee_store)

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

def _active_store_from_cookie():
    slug = request.cookies.get(LAST_STORE_SLUG_COOKIE)
    if not slug:
        return None
    store = db.session.query(Store).filter_by(slug=slug).first()
    if store and store.is_active:
        return store
    return None

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

TOTP_ISSUER = "DineroBook"
# Single source of truth for TOTP / recovery-code helpers lives in
# api.Modules.Auth.Services.totp (PR 41). The Flask-scope wrappers
# below forward to the Service so legacy callers keep their existing
# call shape during the migration window.
from api.Modules.Auth.Services import RECOVERY_CODES_PER_USER  # noqa: E402

def _needs_totp(user):
    """Which roles must use 2FA. Keep this the single gatekeeper."""
    from api.Modules.Auth.Services import needs_totp
    return needs_totp(user)

def _totp_is_enrolled(user):
    from api.Modules.Auth.Services import is_enrolled
    return is_enrolled(user)

def _pending_auth_user():
    uid = session.get("pending_auth_user_id")
    return db.session.get(User, uid) if uid else None

def _hash_recovery_code(raw):
    from api.Modules.Auth.Services import hash_recovery_code
    return hash_recovery_code(raw)

def _format_recovery_code(raw):
    from api.Modules.Auth.Services import format_recovery_code
    return format_recovery_code(raw)

def _generate_recovery_codes(user):
    """Wipe any existing codes for this user and mint a fresh batch.
    Caller is responsible for the surrounding transaction; we commit
    here for backwards-compat with existing call sites that never
    saw the flush."""
    from api.Modules.Auth.Services import generate_recovery_codes
    codes = generate_recovery_codes(db.session, user)
    db.session.commit()
    return codes

def _consume_recovery_code(user, raw):
    """Return True if `raw` matches an unused code for `user` and
    mark it used. Commits on hit so legacy callers don't need to."""
    from api.Modules.Auth.Services import consume_recovery_code
    hit = consume_recovery_code(db.session, user, raw)
    if hit:
        db.session.commit()
    return hit

def _verify_totp(user, token):
    from api.Modules.Auth.Services import verify_totp_token
    return verify_totp_token(user, token)

def _totp_qr_svg(secret, username):
    """SVG <svg>…</svg> string encoding the TOTP provisioning URI.
    Pure-Python (no Pillow) via qrcode.image.svg. Embeddable directly."""
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name=TOTP_ISSUER)
    img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage,
                      box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode("utf-8")

def _finalize_2fa_login(user):
    """Promote the partial-auth session to a full-auth session after
    successful TOTP/recovery-code verification or first enrollment."""
    session.pop("pending_auth_user_id", None)
    session.pop("totp_enrollment_codes", None)
    session["user_id"]  = user.id
    session["role"]     = user.role
    session["store_id"] = user.store_id
    _record_login(user); db.session.commit()

# ── Passkeys (WebAuthn) ──────────────────────────────────────
#
# A passkey is phishing-resistant MFA by construction — the credential
# is device-bound, user-presence-proven, and the RP ID prevents replay
# on a look-alike domain. So a successful passkey login is treated as
# MFA-sufficient for every role including superadmin (see the carve-out
# in CLAUDE.md invariant #13). Password login still gates superadmin
# through TOTP; passkey is the parallel path.

def _webauthn_rp_id():
    """The effective RP ID. Single source of truth lives in
    `api.Modules.Auth.Services.passkey_rp_id` (PR 63)."""
    from api.Modules.Auth.Services import passkey_rp_id
    return passkey_rp_id(request.host)

def _webauthn_rp_name():
    """Brand label shown by the OS picker. Single source of truth
    lives in `api.Modules.Auth.Services.passkey_rp_name` (PR 63)."""
    from api.Modules.Auth.Services import passkey_rp_name
    return passkey_rp_name()

def _webauthn_origin():
    """Expected Origin header for WebAuthn verification. Single
    source of truth lives in
    `api.Modules.Auth.Services.passkey_origin` (PR 63)."""
    from api.Modules.Auth.Services import passkey_origin
    return passkey_origin(request.scheme, request.host)

def _passkey_exclude_list(user):
    """Credential descriptors for every passkey this user already has.
    Single source of truth lives in
    `api.Modules.Auth.Services.passkey_exclude_credentials` (PR 63)."""
    from api.Modules.Auth.Services import passkey_exclude_credentials
    return passkey_exclude_credentials(db.session, user)

def _passkey_eligible(user):
    """Whether a user may enroll passkeys. Single source of truth
    lives in `api.Modules.Auth.Services.passkey_is_eligible` (PR 63)."""
    from api.Modules.Auth.Services import passkey_is_eligible
    return passkey_is_eligible(user)

def _update_user_password(user, current_pw, new_pw, confirm_pw):
    """Validate + apply a self-service password change. Returns
    `{}` on success or `{field: message}` on failure. Single source
    of truth lives in `api.Modules.Auth.Services.change_password`
    (PR 40); this wrapper is here for legacy call sites."""
    from api.Modules.Auth.Services import change_password
    return change_password(db.session, user, current_pw, new_pw, confirm_pw)

def _update_user_display_name(user, raw):
    """Validate + apply a display-name change. Same return contract as
    _update_user_password — empty dict means apply, else field errors."""
    name = (raw or "").strip()
    if not name:
        return {"full_name": "Display name cannot be empty."}
    if len(name) > 120:
        return {"full_name": "Display name is too long (max 120 characters)."}
    user.full_name = name
    return {}

# Loose email regex — RFC 5322 is famously underspecified, so we just
# require "something@something.something" to catch obvious typos. Final
# validity is whether mail actually delivers.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Phone: keep generous. Strip whitespace + hyphens + parens; require
# 7–20 digits with an optional leading +. We don't normalize beyond
# that — region codes vary too much for a one-size validator.
_PHONE_DIGITS_RE = re.compile(r"^\+?\d{7,20}$")

def _update_user_profile(user, raw_full_name, raw_email, raw_phone, raw_tz):
    """Validate + apply a profile change in one shot. All four fields
    are optional except full_name; empty string clears phone/email/tz."""
    errors = {}
    name = (raw_full_name or "").strip()
    if not name:
        errors["full_name"] = "Display name cannot be empty."
    elif len(name) > 120:
        errors["full_name"] = "Display name is too long (max 120 characters)."

    email = (raw_email or "").strip().lower()
    if email and not _EMAIL_RE.match(email):
        errors["email"] = "Enter a valid email address."
    elif len(email) > 255:
        errors["email"] = "Email is too long (max 255 characters)."

    phone_clean = re.sub(r"[\s\-\(\)]", "", raw_phone or "")
    if phone_clean and not _PHONE_DIGITS_RE.match(phone_clean):
        errors["phone"] = "Enter a valid phone number (7–20 digits, optional leading +)."

    tz = (raw_tz or "").strip()
    if tz and tz not in PROFILE_TIMEZONES:
        errors["timezone"] = "Pick a timezone from the list."

    if errors:
        return errors
    user.full_name = name
    user.email = email
    user.phone = phone_clean
    user.timezone = tz
    return {}

# Curated timezone list — Americas + the handful of Asia/Europe zones
# our owner-operators have actually asked for. Adding a zone is one
# line; we deliberately don't expose the full ~600 IANA list because
# that's a UX trap for non-technical cashiers. The empty string means
# "fall back to UTC / store default".
PROFILE_TIMEZONES = [
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Phoenix",
    "America/Los_Angeles",
    "America/Anchorage",
    "Pacific/Honolulu",
    "America/Mexico_City",
    "America/Bogota",
    "America/Lima",
    "America/Santiago",
    "America/Buenos_Aires",
    "America/Sao_Paulo",
    "Europe/London",
    "Europe/Madrid",
    "Asia/Manila",
    "Asia/Karachi",
    "UTC",
]

def _record_login(user, *, method=""):
    """Stamp last_login_at on a successful sign-in AND append a
    LoginEvent row for the DAU/MAU report. Called by every login
    path (password, store-scoped, owner, passkey). Caller must
    commit; we don't, because some login paths batch other writes
    (sign_count update on passkey login) into the same transaction.

    `method` is "password" / "passkey" / "totp" / "" (unspecified).
    """
    user.last_login_at = datetime.utcnow()
    db.session.add(LoginEvent(
        user_id=user.id, role=user.role or "",
        method=method, at=datetime.utcnow(),
    ))

def _require_pending_auth():
    """Shared guard for /login/2fa* routes: redirect back to /login if
    there's no partial-auth in flight (expired session, direct visit,
    etc.). Returns the pending user, or None (caller must return the
    redirect)."""
    u = _pending_auth_user()
    if not u or not u.is_active:
        session.pop("pending_auth_user_id", None)
        return None
    return u

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
PASSWORD_RESET_TTL_HOURS = 1

def _hash_token(raw):
    """sha256-hex — matches the column size and is fine for single-use tokens."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

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


def _owner_period_window(period, today):
    """Delegate to api.Modules.Owners.Services.owner_period_window."""
    return _svc_owner_period_window(period, today)


def _owner_store_ids(user):
    """Delegate to api.Modules.Owners.Services.owner_store_ids."""
    return _svc_owner_store_ids(db.session, user)


def _owner_kpis(store_ids, start, end):
    """Delegate to api.Modules.Owners.Services.owner_kpis."""
    return _svc_owner_kpis(db.session, store_ids, start, end)


def _owner_dashboard_context(user, period):
    """Rich metrics for /owner/dashboard. Single source of truth
    lives in `api.Modules.Owners.Services.owner_dashboard_context`
    (PR 74).
    """
    from api.Modules.Owners.Services import owner_dashboard_context
    return owner_dashboard_context(db.session, user, period)


def _owner_locations_payload(user, period, query):
    """Per-store rows for /owner/locations. Single source of truth
    lives in `api.Modules.Owners.Services.owner_locations_payload`
    (PR 74).
    """
    from api.Modules.Owners.Services import owner_locations_payload
    return owner_locations_payload(db.session, user, period, query)


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

def _tv_required(allow_employee=True):
    """Guard for /tv-display/* routes. Returns either:
      - (user, store) tuple on success, or
      - a Flask Response the caller should return verbatim
        (redirect to subscription page when add-on isn't active)
    Hard failures (no session / wrong role) `abort(404)` immediately."""
    user = current_user()
    store = current_store()
    if not user or not store:
        abort(404)
    roles = ("admin", "employee") if allow_employee else ("admin",)
    if user.role not in roles:
        abort(404)
    if not store_has_addon(store, "tv_display"):
        flash("The TV Display add-on isn't active for this store. "
              "Turn it on from your subscription page.", "warning")
        return redirect(url_for("subscription.admin_subscription"))
    return (user, store)

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
# To wire a new report: set `endpoint` (and optionally
# `endpoint_args`) to a registered url_for target. The card flips
# from "Coming soon" to a working link automatically.
_REPORT_CATEGORIES = [
    {
        "key":   "sales",
        "label": "Sales",
        "icon":  '<svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>',
        "reports": [
            {"key": "sales_by_company",
             "label": "Sales by Company",
             "description": "Volume, fees, and federal tax split between Intermex, Maxi, and Barri.",
             "endpoint": "report_sales_by_company"},
            {"key": "sales_by_service",
             "label": "Sales by Service Type",
             "description": "Money Transfer vs. Bill Payment vs. Top Up vs. Recharge — volume and count.",
             "endpoint": "report_sales_by_service_type"},
            {"key": "sales_by_employee",
             "label": "Sales by Employee",
             "description": "Per-employee transfer count and total volume.",
             "endpoint": "report_sales_by_employee"},
            {"key": "cashier_productivity",
             "label": "Cashier Productivity",
             "description": "Volume + count per cashier on duty (the 'Processed by' selection on each transfer).",
             "endpoint": "report_cashier_productivity"},
            {"key": "top_customers",
             "label": "Top Customers by Volume",
             "description": "Senders who moved the most in the period.",
             "endpoint": "report_top_customers"},
        ],
    },
    {
        "key":   "financial",
        "label": "Financial",
        "icon":  '<svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>',
        "reports": [
            {"key": "period_pl",
             "label": "Period P&L",
             "description": "Income, expenses, and net income aggregated for any date range.",
             "endpoint": "report_period_pl"},
            {"key": "ach_volume",
             "label": "ACH Volume",
             "description": "Daily ACH batches and totals per remittance company.",
             "endpoint": "report_ach_volume"},
            {"key": "bank_charges",
             "label": "Bank Charges by Account",
             "description": "Per-account charges aggregated for the period.",
             "endpoint": "report_bank_charges_by_account"},
            {"key": "period_comparison",
             "label": "Period Comparison",
             "description": "Side-by-side metrics vs. the prior period of the same length.",
             "endpoint": "report_period_comparison"},
            {"key": "fees_vs_tax",
             "label": "Fees vs. Federal Tax",
             "description": "Store revenue (fees) vs. ACH-bound federal tax.",
             "endpoint": "report_fees_vs_tax"},
        ],
    },
    {
        "key":   "operations",
        "label": "Operations",
        "icon":  '<svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>',
        "reports": [
            {"key": "returned_checks_status",
             "label": "Returned Check Status",
             "description": "Open, recovered, and lost returned checks for a period.",
             "endpoint": "report_returned_check_status"},
            {"key": "bank_txn_breakdown",
             "label": "Bank Transactions Breakdown",
             "description": "Synced bank-feed rows summarised by category.",
             "endpoint": "report_bank_txn_breakdown"},
            {"key": "daily_drops",
             "label": "Daily Drops",
             "description": "Cash drops by day across the period.",
             "endpoint": "report_daily_drops"},
            {"key": "check_deposits",
             "label": "Check Deposits",
             "description": "Deposit log totalled by day across the period.",
             "endpoint": "report_check_deposits"},
        ],
    },
    {
        "key":   "customers",
        "label": "Customers",
        "icon":  '<svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
        "reports": [
            {"key": "top_senders",
             "label": "Top Senders",
             "description": "Most-active senders by transaction count.",
             "endpoint": "report_top_senders"},
            {"key": "top_recipients",
             "label": "Top Recipients",
             "description": "Most-paid recipients across all senders.",
             "endpoint": "report_top_recipients"},
            {"key": "by_country",
             "label": "By Destination Country",
             "description": "Volume + count grouped by recipient country.",
             "endpoint": "report_by_destination_country"},
            {"key": "new_vs_returning",
             "label": "New vs. Returning Senders",
             "description": "First-time senders against repeat customers in the period.",
             "endpoint": "report_new_vs_returning"},
        ],
    },
    {
        "key":   "audit",
        "label": "Audit",
        "icon":  '<svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="13" y2="17"/></svg>',
        "reports": [
            {"key": "high_value_transfers",
             "label": "High-Value Transfers",
             "description": "Transfers above a configurable threshold (default $3,000).",
             "endpoint": "report_high_value_transfers"},
            {"key": "employee_activity",
             "label": "Employee Activity",
             "description": "Per-employee transfers, totals, cancelled count, and last activity.",
             "endpoint": "report_employee_activity"},
            {"key": "bank_rule_audit",
             "label": "Bank-Rule Audit Log",
             "description": "Which rule auto-categorised which transaction.",
             "endpoint": "report_bank_rule_audit"},
            {"key": "cancelled_transfers",
             "label": "Cancelled Transfers",
             "description": "Transfers cancelled or rejected within the period.",
             "endpoint": "report_cancelled_transfers"},
        ],
    },
]


def _resolved_report_categories(registry, endpoint_prefix=""):
    """Return `registry` with each report enriched with a rendered URL
    plus a `status` flag the template uses to swap between "View"
    button and "Coming soon" pill.

    URL derivation order:
      1. Literal ``url`` on the registry entry (wins outright).
      2. ``url_for(endpoint)`` if Flask has a matching route.
      3. ``_url_from_endpoint(endpoint)`` — convention-based fallback
         (``report_X_Y`` → ``/reports/x-y``). Needed because the HTML
         drilldown routes no longer register Flask handlers; they
         redirect to the SPA via the ``spa_cutover`` before_request
         hook, so the endpoint name only encodes the URL we want to
         link to.

    ``endpoint_prefix`` lets the owner Report Center reuse the admin
    registry while routing to owner-prefixed mirrors (every
    ``report_<x>`` admin endpoint maps to ``owner_report_<x>``).
    """
    out = []
    for cat in registry:
        reports = []
        for r in cat["reports"]:
            ep = r.get("endpoint")
            url = r.get("url")  # literal URL takes precedence
            if not url and ep:
                effective_ep = ep
                if endpoint_prefix and not ep.startswith(endpoint_prefix):
                    effective_ep = endpoint_prefix + ep
                try:
                    url = url_for(effective_ep,
                                  **(r.get("endpoint_args") or {}))
                except Exception:
                    url = _url_from_endpoint(effective_ep)
            reports.append({
                **r,
                "url": url,
                "status": "ready" if url else "coming_soon",
            })
        out.append({**cat, "reports": reports})
    return out


def _url_from_endpoint(endpoint: str) -> str | None:
    """Convention-based reverse of the report-route endpoint names.

      ``report_<slug_underscored>``            → ``/reports/<slug>``
      ``owner_report_<slug_underscored>``      → ``/owner/reports/<slug>``
      ``superadmin_report_<slug_underscored>`` → ``/superadmin/reports/<slug>``

    Returns None for names that don't match the convention so the
    Report Center can still flag those as ``coming_soon``.
    """
    if endpoint.startswith("owner_report_"):
        slug = endpoint[len("owner_report_"):].replace("_", "-")
        return f"/owner/reports/{slug}"
    if endpoint.startswith("superadmin_report_"):
        slug = endpoint[len("superadmin_report_"):].replace("_", "-")
        return f"/superadmin/reports/{slug}"
    if endpoint.startswith("report_"):
        slug = endpoint[len("report_"):].replace("_", "-")
        return f"/reports/{slug}"
    return None


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


def _active_transfers_period_filters(store_ids, d_from, d_to):
    """LEGACY shim — delegates to api.Modules.Reports.Repositories.

    The query logic now lives in the new layered module per the
    migration ADR. This wrapper keeps every existing caller in
    app.py working without changes; eventually those callers also
    move into Reports services and this function disappears with
    the cleanup PR."""
    from api.Modules.Reports.Repositories.transfers import period_filters
    return period_filters(store_ids, d_from, d_to)


def _aggregate_transfers(store_ids, d_from, d_to, group_col):
    """LEGACY shim — delegates to api.Modules.Reports.Repositories.

    See `_active_transfers_period_filters` above for the shim
    rationale. Same single-source-of-truth principle: aggregation
    SQL exists in exactly one place (the new repository), called
    from both Flask and FastAPI paths during the strangler-fig
    migration window."""
    from api.Modules.Reports.Repositories.transfers import aggregate
    return aggregate(db.session, store_ids, d_from, d_to, group_col)


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


def _new_vs_returning_data(store_ids, d_from, d_to):
    """Split senders into new / returning / walk-in buckets.
    Single source of truth lives in
    `api.Modules.Reports.Services.new_vs_returning` (PR 89)."""
    from api.Modules.Reports.Services import new_vs_returning
    return new_vs_returning(db.session, store_ids, d_from, d_to)


def _csv_response(buf, fname):
    """Wrap a StringIO buffer as a downloadable text/csv response.
    Pulled out so each report's CSV route stops repeating the
    Content-Disposition incantation."""
    return Response(buf.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ── Returned Check Status ────────────────────────────────────
def _returned_check_status_data(store_ids, d_from, d_to):
    """Group ReturnCheck rows bounced in the period by status.
    Single source of truth lives in
    `api.Modules.Reports.Services.returned_check_status` (PR 90)."""
    from api.Modules.Reports.Services import returned_check_status
    return returned_check_status(db.session, store_ids, d_from, d_to)


# ── Bank Transactions Breakdown ──────────────────────────────
def _bank_txn_breakdown_data(store_ids, d_from, d_to):
    """Group BankTransaction rows by category_slug. Single source
    of truth lives in
    `api.Modules.Reports.Services.bank_txn_breakdown` (PR 91)."""
    from api.Modules.Reports.Services import bank_txn_breakdown
    return bank_txn_breakdown(db.session, store_ids, d_from, d_to)


# ── Daily Drops ──────────────────────────────────────────────
def _daily_drops_data(store_ids, d_from, d_to):
    """Sum DailyDrop rows in the period, grouped by report_date.
    Single source of truth lives in
    `api.Modules.Reports.Services.daily_drops` (PR 92)."""
    from api.Modules.Reports.Services import daily_drops
    return daily_drops(db.session, store_ids, d_from, d_to)


# ── Check Deposits ───────────────────────────────────────────
def _check_deposits_data(store_ids, d_from, d_to):
    """Sum CheckDeposit rows in the period, grouped by report_date.
    Single source of truth lives in
    `api.Modules.Reports.Services.check_deposits` (PR 92)."""
    from api.Modules.Reports.Services import check_deposits
    return check_deposits(db.session, store_ids, d_from, d_to)


# ── High-Value Transfers ─────────────────────────────────────
def _high_value_transfers_data(store_ids, d_from, d_to, threshold):
    """List active transfers in the period >= threshold. Single
    source of truth lives in
    `api.Modules.Reports.Services.high_value_transfers` (PR 93)."""
    from api.Modules.Reports.Services import high_value_transfers
    return high_value_transfers(
        db.session, store_ids, d_from, d_to, threshold,
    )


def _parse_threshold(args, default=3000):
    try:
        v = float(args.get("threshold") or default)
    except (ValueError, TypeError):
        v = default
    return max(0.0, v)


# ── Employee Activity ────────────────────────────────────────
def _employee_activity_data(store_ids, d_from, d_to):
    """Per-employee activity audit. Single source of truth lives
    in `api.Modules.Reports.Services.employee_activity` (PR 94)."""
    from api.Modules.Reports.Services import employee_activity
    return employee_activity(db.session, store_ids, d_from, d_to)


# ── Bank-Rule Audit Log ──────────────────────────────────────
def _bank_rule_audit_data(store_ids, d_from, d_to):
    """Per-rule audit of operator-defined BankRule firings.
    Single source of truth lives in
    `api.Modules.Reports.Services.bank_rule_audit` (PR 95)."""
    from api.Modules.Reports.Services import bank_rule_audit
    return bank_rule_audit(db.session, store_ids, d_from, d_to)


# ── Cancelled Transfers ──────────────────────────────────────
def _cancelled_transfers_data(store_ids, d_from, d_to):
    """List Cancelled / Rejected transfers in the period.
    Single source of truth lives in
    `api.Modules.Reports.Services.cancelled_transfers` (PR 96)."""
    from api.Modules.Reports.Services import cancelled_transfers
    return cancelled_transfers(db.session, store_ids, d_from, d_to)


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


def _period_pl_data(store_ids, d_from, d_to):
    """Aggregate DailyReport + Transfer fees in the period into a
    daily-book P&L. Single source of truth lives in
    `api.Modules.Reports.Services.period_pl` (PR 87)."""
    from api.Modules.Reports.Services import period_pl
    return period_pl(db.session, store_ids, d_from, d_to)


# ── ACH Volume ───────────────────────────────────────────────
def _ach_volume_data(store_ids, d_from, d_to):
    """Group ACHBatch rows in the period by company. Single source
    of truth lives in `api.Modules.Reports.Services.ach_volume`
    (PR 88)."""
    from api.Modules.Reports.Services import ach_volume
    return ach_volume(db.session, store_ids, d_from, d_to)


# ── Bank Charges by Account ──────────────────────────────────
def _bank_charges_by_account_data(store_ids, d_from, d_to):
    """Sum BankTransaction rows tagged as bank charges, grouped
    by account. Single source of truth lives in
    `api.Modules.Reports.Services.bank_charges_by_account`
    (PR 84)."""
    from api.Modules.Reports.Services import bank_charges_by_account
    return bank_charges_by_account(db.session, store_ids, d_from, d_to)


# ── Period Comparison ────────────────────────────────────────
def _period_comparison_data(store_ids, d_from, d_to,
                              *, compare_from=None, compare_to=None):
    """Compare the chosen period against another period. Single
    source of truth lives in
    `api.Modules.Reports.Services.period_comparison` (PR 86)."""
    from api.Modules.Reports.Services import period_comparison
    return period_comparison(
        db.session, store_ids, d_from, d_to,
        compare_from=compare_from, compare_to=compare_to,
    )


# ── Fees vs. Federal Tax ─────────────────────────────────────
def _fees_vs_tax_data(store_ids, d_from, d_to):
    """Side-by-side: total fees vs. federal tax. Single source of
    truth lives in `api.Modules.Reports.Services.fees_vs_tax`
    (PR 85)."""
    from api.Modules.Reports.Services import fees_vs_tax
    return fees_vs_tax(db.session, store_ids, d_from, d_to)


# ── Period-comparison KPIs (multi-statement; can't be a lambda) ──
def _period_comparison_kpis(totals, rows, extra):
    def _row(label):
        return next((r for r in rows if r["label"] == label), None)
    inc, net, txn = (_row("Total Income"), _row("Net Income"),
                     _row("Transfers"))
    return [
        {"label": "Income Δ",
         "value": f"{inc['pct']:+.1f}%" if inc else "—",
         "tone":  "primary"},
        {"label": "Net Δ",
         "value": f"{net['pct']:+.1f}%" if net else "—",
         "tone":  "neon" if (net and net["pct"] >= 0) else "muted"},
        {"label": "Transfers Δ",
         "value": f"{txn['pct']:+.1f}%" if txn else "—",
         "tone":  "muted"},
    ]


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
    data_fn=_new_vs_returning_data,
    csv_columns=['Bucket', 'Customers', 'Transfers', 'Total Sent'],
    csv_row_fn=lambda r: [r['bucket'], r['customers'], r['txns'], f"{r['sent']:.2f}"],
    csv_totals_fn=lambda t: ['TOTAL', t['customers'], t['txns'], f"{t['sent']:.2f}"],
)

_make_report_routes(
    'returned-check-status',
    data_fn=_returned_check_status_data,
    csv_columns=['Status', 'Count', 'Amount', 'Recovered'],
    csv_row_fn=lambda r: [r['status'], r['count'], f"{r['amount']:.2f}", f"{r['recovered']:.2f}"],
    csv_totals_fn=lambda t: [['TOTAL', t['count'], f"{t['amount']:.2f}", f"{t['recovered']:.2f}"], ['NET G/L', '', '', f"{t['net_gl']:.2f}"]],
    csv_fname_prefix='returned-checks',
)

_make_report_routes(
    'bank-transactions-breakdown',
    data_fn=_bank_txn_breakdown_data,
    csv_columns=['Category', 'Count', 'Signed Amount', 'Absolute Amount'],
    csv_row_fn=lambda r: [r['label'], r['count'], f"{r['signed']:.2f}", f"{r['amount']:.2f}"],
    csv_fname_prefix='bank-txn-breakdown',
)

_make_report_routes(
    'daily-drops',
    data_fn=_daily_drops_data,
    csv_columns=['Date', 'Drop Count', 'Total Dropped'],
    csv_row_fn=lambda r: [r['date'].isoformat(), r['count'], f"{r['amount']:.2f}"],
    csv_totals_fn=lambda t: ['TOTAL', t['count'], f"{t['amount']:.2f}"],
)

_make_report_routes(
    'check-deposits',
    data_fn=_check_deposits_data,
    csv_columns=['Date', 'Deposit Count', 'Total Deposited'],
    csv_row_fn=lambda r: [r['date'].isoformat(), r['count'], f"{r['amount']:.2f}"],
    csv_totals_fn=lambda t: ['TOTAL', t['count'], f"{t['amount']:.2f}"],
)

_make_report_routes(
    'high-value-transfers',
    data_fn=_high_value_transfers_data,
    csv_columns=['Date', 'Sender', 'Recipient', 'Country', 'Company', 'Send Amount', 'Fee', 'Federal Tax', 'Confirm #'],
    csv_row_fn=lambda r: [r['send_date'].isoformat(), r['sender_name'], r['recipient_name'], r['country'], r['company'], f"{r['amount']:.2f}", f"{r['fee']:.2f}", f"{r['tax']:.2f}", r['confirm']],
    extra_args_fn=lambda: {'threshold': _parse_threshold(request.args)},
)

_make_report_routes(
    'employee-activity',
    data_fn=_employee_activity_data,
    csv_columns=['Employee', 'Username', 'Active Transfers', 'Total Sent', 'Cancelled / Rejected', 'Last Activity'],
    csv_row_fn=lambda r: [r['employee'], r['username'], r['count'], f"{r['sent']:.2f}", r['cancels'], r['last_activity'].isoformat() if r['last_activity'] else ''],
)

_make_report_routes(
    'bank-rule-audit',
    data_fn=_bank_rule_audit_data,
    csv_columns=['Rule', 'Match', 'Target', 'Matched Count', 'Total Amount'],
    csv_row_fn=lambda r: [r['label'], r['match'], r['target'], r['count'], f"{r['amount']:.2f}"],
)

_make_report_routes(
    'cancelled-transfers',
    data_fn=_cancelled_transfers_data,
    csv_columns=['Date', 'Sender', 'Recipient', 'Country', 'Company', 'Status', 'Send Amount', 'Notes', 'Confirm #'],
    csv_row_fn=lambda r: [r['send_date'].isoformat(), r['sender_name'], r['recipient_name'], r['country'], r['company'], r['status'], f"{r['amount']:.2f}", r['status_notes'], r['confirm']],
)

_make_report_routes(
    'period-pl',
    data_fn=_period_pl_data,
    csv_columns=['Section', 'Line', 'Amount'],
    csv_row_fn=lambda r: [r['section'], r['label'], f"{r['amount']:.2f}"],
    csv_totals_fn=lambda t: [['', 'Total Income', f"{t['income']:.2f}"], ['', 'Total Expenses', f"{t['expenses']:.2f}"], ['', 'Net', f"{t['net']:.2f}"]],
)

_make_report_routes(
    'ach-volume',
    data_fn=_ach_volume_data,
    csv_columns=['Company', 'Batch Count', 'Total ACH', 'Avg / Batch'],
    csv_row_fn=lambda r: [r['company'], r['count'], f"{r['amount']:.2f}", f"{r['avg']:.2f}"],
    csv_totals_fn=lambda t: ['TOTAL', t['count'], f"{t['amount']:.2f}", ''],
)

_make_report_routes(
    'bank-charges-by-account',
    data_fn=_bank_charges_by_account_data,
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
    data_fn=_period_comparison_data,
    csv_columns=lambda t: ['Metric', t['current_label'], t['prior_label'], 'Delta', '% Change'],
    csv_row_fn=lambda r: [r['label'], f"{r['current']:.2f}" if r['is_money'] else f"{int(r['current'])}", f"{r['prior']:.2f}" if r['is_money'] else f"{int(r['prior'])}", f"{r['delta']:.2f}" if r['is_money'] else f"{int(r['delta'])}", f"{r['pct']:+.1f}%"],
    extra_args_fn=lambda: _parse_compare_dates(request.args),
)

_make_report_routes(
    'fees-vs-tax',
    data_fn=_fees_vs_tax_data,
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
_SUPERADMIN_REPORT_CATEGORIES = [
    {
        "key":   "platform_health",
        "label": "Platform Health",
        "icon":  '<svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>',
        "reports": [
            {"key": "dau_mau",
             "label": "Daily / Monthly Actives",
             "description": "DAU + MAU per day from the LoginEvent feed, plus stickiness.",
             "endpoint": "superadmin_report_dau_mau"},
            {"key": "active_stores_by_plan",
             "label": "Active Stores by Plan",
             "description": "Headcount across trial / basic / pro / inactive.",
             "endpoint": "superadmin_report_active_stores_by_plan"},
            {"key": "signup_funnel",
             "label": "Signup Funnel",
             "description": "Stores created in the period bucketed by current plan.",
             "endpoint": "superadmin_report_signup_funnel"},
            {"key": "login_activity",
             "label": "Login Activity",
             "description": "Per-role sign-in counts in the period.",
             "endpoint": "superadmin_report_login_activity"},
        ],
    },
    {
        "key":   "revenue",
        "label": "Revenue",
        "icon":  '<svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>',
        "reports": [
            {"key": "mrr_arr",
             "label": "MRR / ARR",
             "description": "Recurring revenue split by plan and billing cycle.",
             "endpoint": "superadmin_report_mrr_arr"},
            {"key": "churn",
             "label": "Churn Cohort",
             "description": "Customer churn by signup cohort.",
             "endpoint": "superadmin_report_churn_cohort"},
            {"key": "refunds",
             "label": "Refunds",
             "description": "Stripe refunds in the period grouped by reason.",
             "endpoint": "superadmin_report_refunds"},
        ],
    },
    {
        "key":   "stripe",
        "label": "Stripe",
        "icon":  '<svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="5" width="20" height="14" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/></svg>',
        "reports": [
            {"key": "webhook_health",
             "label": "Webhook Health",
             "description": "Inbound Stripe webhook deliveries by status.",
             "endpoint": "superadmin_report_webhook_health"},
            {"key": "failed_payments",
             "label": "Failed Payments",
             "description": "Recent failed charges grouped by reason.",
             "endpoint": "superadmin_report_failed_payments"},
            {"key": "payouts",
             "label": "Payouts",
             "description": "Stripe payouts to the platform bank account.",
             "endpoint": "superadmin_report_payouts"},
        ],
    },
    {
        "key":   "trial",
        "label": "Trial Funnel",
        "icon":  '<svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
        "reports": [
            {"key": "conversion_rate",
             "label": "Conversion Rate",
             "description": "Trial → paid percentage for cohorts that signed up in the period.",
             "endpoint": "superadmin_report_conversion_rate"},
            {"key": "time_to_convert",
             "label": "Time to Convert",
             "description": "Per-store days from signup to today (paid stores only).",
             "endpoint": "superadmin_report_time_to_convert"},
            {"key": "trial_expiry_timing",
             "label": "Trial Expiry Timing",
             "description": "Where in their trial window each store sits at end of period.",
             "endpoint": "superadmin_report_trial_expiry_timing"},
        ],
    },
    {
        "key":   "feature_adoption",
        "label": "Feature Adoption",
        "icon":  '<svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
        "reports": [
            {"key": "bank_sync_adoption",
             "label": "Bank Sync Adoption",
             "description": "Stores that have connected at least one account, by plan.",
             "endpoint": "superadmin_report_bank_sync_adoption"},
            {"key": "tv_display_adoption",
             "label": "TV Display Add-on",
             "description": "Active TV-display installations by store.",
             "endpoint": "superadmin_report_tv_display_adoption"},
            {"key": "owner_adoption",
             "label": "Multi-store Owners",
             "description": "Owner accounts linked to more than one store.",
             "endpoint": "superadmin_report_owner_adoption"},
            {"key": "passkey_adoption",
             "label": "Passkey Adoption",
             "description": "Users with at least one registered passkey, by role.",
             "endpoint": "superadmin_report_passkey_adoption"},
        ],
    },
    {
        "key":   "support",
        "label": "Support / Audit",
        "icon":  '<svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="13" y2="17"/></svg>',
        "reports": [
            {"key": "audit_log",
             "label": "Superadmin Audit Log",
             "description": "Every superadmin mutation, with target and actor.",
             "url": "/app/superadmin/audit-log"},
            {"key": "password_resets",
             "label": "Password Resets",
             "description": "Reset-token activity in the period (used / expired / open).",
             "endpoint": "superadmin_report_password_resets"},
            {"key": "suspended_stores",
             "label": "Suspended / Inactive Stores",
             "description": "Stores currently suspended (is_active=False) or marked inactive.",
             "endpoint": "superadmin_report_suspended_stores"},
            {"key": "retention_queue",
             "label": "Retention Queue",
             "description": "Stores in the 180-day data-retention delete window.",
             "endpoint": "superadmin_report_retention_queue"},
        ],
    },
]


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
def _sa_active_stores_by_plan_data(d_from, d_to):
    """Headcount of stores per plan. Single source of truth lives
    in `api.Modules.Superadmin.Services.active_stores_by_plan`
    (PR 97)."""
    from api.Modules.Superadmin.Services import active_stores_by_plan
    return active_stores_by_plan(db.session, d_from, d_to)


def _sa_signup_funnel_data(d_from, d_to):
    """Stores created in the period bucketed by current plan.
    Single source of truth lives in
    `api.Modules.Superadmin.Services.signup_funnel` (PR 97)."""
    from api.Modules.Superadmin.Services import signup_funnel
    return signup_funnel(db.session, d_from, d_to)


def _sa_login_activity_data(d_from, d_to):
    """Per-role unique login counts in the period. Single source
    of truth lives in
    `api.Modules.Superadmin.Services.login_activity` (PR 97)."""
    from api.Modules.Superadmin.Services import login_activity
    return login_activity(db.session, d_from, d_to)


def _sa_mrr_arr_data(d_from, d_to):
    """MRR + ARR by plan/cycle. Single source of truth lives in
    `api.Modules.Superadmin.Services.mrr_arr` (PR 98)."""
    from api.Modules.Superadmin.Services import mrr_arr
    return mrr_arr(db.session, d_from, d_to)


def _sa_churn_cohort_data(d_from, d_to):
    """Stores cancelled in the period by signup-month cohort.
    Single source of truth lives in
    `api.Modules.Superadmin.Services.churn_cohort` (PR 98)."""
    from api.Modules.Superadmin.Services import churn_cohort
    return churn_cohort(db.session, d_from, d_to)


def _sa_conversion_rate_data(d_from, d_to):
    """Single summary of trial→paid conversion in the period.
    Single source of truth lives in
    `api.Modules.Superadmin.Services.conversion_rate` (PR 99)."""
    from api.Modules.Superadmin.Services import conversion_rate
    return conversion_rate(db.session, d_from, d_to)


def _sa_time_to_convert_data(d_from, d_to):
    """Days-since-signup for paid stores. Single source of truth
    lives in `api.Modules.Superadmin.Services.time_to_convert`
    (PR 99)."""
    from api.Modules.Superadmin.Services import time_to_convert
    return time_to_convert(db.session, d_from, d_to)


def _sa_trial_expiry_timing_data(d_from, d_to):
    """Bucket trial stores by where they are in their trial window.
    Single source of truth lives in
    `api.Modules.Superadmin.Services.trial_expiry_timing` (PR 99)."""
    from api.Modules.Superadmin.Services import trial_expiry_timing
    return trial_expiry_timing(db.session, d_from, d_to)


def _sa_bank_sync_adoption_data(d_from, d_to):
    """Stores with at least one connected StripeBankAccount, by plan.
    Single source of truth lives in
    `api.Modules.Superadmin.Services.bank_sync_adoption` (PR 100)."""
    from api.Modules.Superadmin.Services import bank_sync_adoption
    return bank_sync_adoption(db.session, d_from, d_to)


def _sa_tv_display_adoption_data(d_from, d_to):
    """Stores with the TV-display add-on enabled. Single source of
    truth lives in
    `api.Modules.Superadmin.Services.tv_display_adoption` (PR 100)."""
    from api.Modules.Superadmin.Services import tv_display_adoption
    return tv_display_adoption(db.session, d_from, d_to)


def _sa_owner_adoption_data(d_from, d_to):
    """Owners with multiple linked stores. Single source of truth
    lives in `api.Modules.Superadmin.Services.owner_adoption`
    (PR 100)."""
    from api.Modules.Superadmin.Services import owner_adoption
    return owner_adoption(db.session, d_from, d_to)


def _sa_passkey_adoption_data(d_from, d_to):
    """Users with at least one passkey, by role. Single source of
    truth lives in
    `api.Modules.Superadmin.Services.passkey_adoption` (PR 100)."""
    from api.Modules.Superadmin.Services import passkey_adoption
    return passkey_adoption(db.session, d_from, d_to)


def _sa_password_resets_data(d_from, d_to):
    """Password-reset token activity. Single source of truth lives
    in `api.Modules.Superadmin.Services.password_resets` (PR 101)."""
    from api.Modules.Superadmin.Services import password_resets
    return password_resets(db.session, d_from, d_to)


def _sa_suspended_stores_data(d_from, d_to):
    """Stores currently suspended or inactive. Single source of
    truth lives in
    `api.Modules.Superadmin.Services.suspended_stores` (PR 101)."""
    from api.Modules.Superadmin.Services import suspended_stores
    return suspended_stores(db.session, d_from, d_to)


def _sa_retention_queue_data(d_from, d_to):
    """Stores in the data-retention delete queue. Single source
    of truth lives in
    `api.Modules.Superadmin.Services.retention_queue` (PR 101)."""
    from api.Modules.Superadmin.Services import retention_queue
    return retention_queue(db.session, d_from, d_to)


def _stripe_period_unix(d_from, d_to):
    """Return (gte, lte) Unix timestamps covering [d_from, d_to]
    inclusive. Stripe list APIs filter on `created` with this shape."""
    start = _day_start(d_from)
    end   = _day_end(d_to)
    return int(start.timestamp()), int(end.timestamp())


def _stripe_iter(list_call, *, limit_per_call=100, max_total=500,
                 **kwargs):
    """Page through a Stripe `list` API. Caps total rows at
    `max_total` so a high-volume month doesn't tie up the page."""
    if not stripe.api_key:
        raise RuntimeError("Stripe API key not configured")
    items = []
    for obj in list_call(**kwargs, limit=limit_per_call).auto_paging_iter():
        items.append(obj)
        if len(items) >= max_total:
            break
    return items


def _sa_refunds_data(d_from, d_to):
    """Stripe refunds in the period. Single source of truth lives
    in `api.Modules.Superadmin.Services.refunds` (PR 102)."""
    from api.Modules.Superadmin.Services import refunds
    return refunds(db.session, d_from, d_to)


def _sa_failed_payments_data(d_from, d_to):
    """Recent failed Stripe charges. Single source of truth lives
    in `api.Modules.Superadmin.Services.failed_payments` (PR 102)."""
    from api.Modules.Superadmin.Services import failed_payments
    return failed_payments(db.session, d_from, d_to)


def _sa_payouts_data(d_from, d_to):
    """Stripe payouts to the platform. Single source of truth lives
    in `api.Modules.Superadmin.Services.payouts` (PR 102)."""
    from api.Modules.Superadmin.Services import payouts
    return payouts(db.session, d_from, d_to)


def _sa_dau_mau_data(d_from, d_to):
    """Distinct-user counts per day. Single source of truth lives
    in `api.Modules.Superadmin.Services.dau_mau` (PR 103)."""
    from api.Modules.Superadmin.Services import dau_mau
    return dau_mau(db.session, d_from, d_to)


def _sa_webhook_health_data(d_from, d_to):
    """Inbound Stripe webhooks by status. Single source of truth
    lives in `api.Modules.Superadmin.Services.webhook_health`
    (PR 103)."""
    from api.Modules.Superadmin.Services import webhook_health
    return webhook_health(db.session, d_from, d_to)


# ── Superadmin reports: registry of routes ───────────────────
_make_superadmin_report_routes(
    'active-stores-by-plan',
    data_fn=_sa_active_stores_by_plan_data,
    csv_columns=['Plan', 'Stores'],
    csv_row_fn=lambda r: [r['plan'], r['count']],
    csv_totals_fn=lambda t: ['TOTAL', t['count']],
    csv_fname_prefix='active-stores-by-plan',
)

_make_superadmin_report_routes(
    'signup-funnel',
    data_fn=_sa_signup_funnel_data,
    csv_columns=['Plan', 'Signups'],
    csv_row_fn=lambda r: [r['plan'], r['count']],
    csv_totals_fn=lambda t: ['TOTAL', t['count']],
)

_make_superadmin_report_routes(
    'login-activity',
    data_fn=_sa_login_activity_data,
    csv_columns=['Role', 'Active Users'],
    csv_row_fn=lambda r: [r['role'], r['count']],
    csv_totals_fn=lambda t: ['TOTAL', t['count']],
)

_make_superadmin_report_routes(
    'mrr-arr',
    data_fn=_sa_mrr_arr_data,
    csv_columns=['Plan', 'Cycle', 'Stores', 'MRR', 'ARR'],
    csv_row_fn=lambda r: [r['plan'], r['cycle'], r['stores'], f"{r['mrr']:.2f}", f"{r['arr']:.2f}"],
    csv_totals_fn=lambda t: ['TOTAL', '', t['stores'], f"{t['mrr']:.2f}", f"{t['arr']:.2f}"],
)

_make_superadmin_report_routes(
    'churn-cohort',
    data_fn=_sa_churn_cohort_data,
    csv_columns=['Cohort', 'Cancelled', 'Still Active', 'Churn %'],
    csv_row_fn=lambda r: [r['cohort'], r['cancelled'], r['active'], f"{r['churn_pct']:.1f}%"],
)

_make_superadmin_report_routes(
    'conversion-rate',
    data_fn=_sa_conversion_rate_data,
    csv_columns=['Status', 'Stores'],
    csv_row_fn=lambda r: [r['label'], r['count']],
    csv_totals_fn=lambda t: ['TOTAL', t['total']],
)

_make_superadmin_report_routes(
    'time-to-convert',
    data_fn=_sa_time_to_convert_data,
    csv_columns=['Slug', 'Name', 'Plan', 'Signed Up', 'Days Active'],
    csv_row_fn=lambda r: [r['slug'], r['name'], r['plan'], r['signed_up'].isoformat(), r['days']],
)

_make_superadmin_report_routes(
    'trial-expiry-timing',
    data_fn=_sa_trial_expiry_timing_data,
    csv_columns=['Bucket', 'Stores'],
    csv_row_fn=lambda r: [r['bucket'], r['count']],
)

_make_superadmin_report_routes(
    'bank-sync-adoption',
    data_fn=_sa_bank_sync_adoption_data,
    csv_columns=['Plan', 'Connected', 'Total', 'Adoption %'],
    csv_row_fn=lambda r: [r['plan'], r['connected'], r['total'], f"{r['rate_pct']:.1f}%"],
)

_make_superadmin_report_routes(
    'tv-display-adoption',
    data_fn=_sa_tv_display_adoption_data,
    csv_columns=['Slug', 'Name', 'Plan'],
    csv_row_fn=lambda r: [r['slug'], r['name'], r['plan']],
)

_make_superadmin_report_routes(
    'owner-adoption',
    data_fn=_sa_owner_adoption_data,
    csv_columns=['Owner', 'Email', 'Linked Stores'],
    csv_row_fn=lambda r: [r['owner'], r['email'], r['stores']],
)

_make_superadmin_report_routes(
    'passkey-adoption',
    data_fn=_sa_passkey_adoption_data,
    csv_columns=['Role', 'Users with Passkey'],
    csv_row_fn=lambda r: [r['role'], r['count']],
)

_make_superadmin_report_routes(
    'password-resets',
    data_fn=_sa_password_resets_data,
    csv_columns=['Created', 'Username', 'Role', 'Status'],
    csv_row_fn=lambda r: [r['created_at'].isoformat() if r['created_at'] else '', r['username'], r['role'], r['status']],
)

_make_superadmin_report_routes(
    'suspended-stores',
    data_fn=_sa_suspended_stores_data,
    csv_columns=['Slug', 'Name', 'Plan', 'Reason'],
    csv_row_fn=lambda r: [r['slug'], r['name'], r['plan'], r['reason']],
)

_make_superadmin_report_routes(
    'retention-queue',
    data_fn=_sa_retention_queue_data,
    csv_columns=['Slug', 'Name', 'Plan', 'Purge Date', 'Days Left'],
    csv_row_fn=lambda r: [r['slug'], r['name'], r['plan'], r['until'].isoformat() if r['until'] else '', r['days_left']],
)

_make_superadmin_report_routes(
    'refunds',
    data_fn=_sa_refunds_data,
    csv_columns=['Reason', 'Count', 'Amount'],
    csv_row_fn=lambda r: [r['reason'], r['count'], f"{r['amount']:.2f}"],
    csv_totals_fn=lambda t: ['TOTAL', t['count'], f"{t['amount']:.2f}"],
)

_make_superadmin_report_routes(
    'failed-payments',
    data_fn=_sa_failed_payments_data,
    csv_columns=['Reason', 'Count', 'Amount'],
    csv_row_fn=lambda r: [r['reason'], r['count'], f"{r['amount']:.2f}"],
    csv_totals_fn=lambda t: ['TOTAL', t['count'], f"{t['amount']:.2f}"],
)

_make_superadmin_report_routes(
    'payouts',
    data_fn=_sa_payouts_data,
    csv_columns=['Payout ID', 'Amount', 'Status', 'Method', 'Arrival'],
    csv_row_fn=lambda r: [r['id'], f"{r['amount']:.2f}", r['status'], r['method'], r['arrival'].isoformat() if r['arrival'] else ''],
    csv_totals_fn=lambda t: ['TOTAL', f"{t['amount']:.2f}", '', '', ''],
)

_make_superadmin_report_routes(
    'dau-mau',
    data_fn=_sa_dau_mau_data,
    csv_columns=['Date', 'Active Users'],
    csv_row_fn=lambda r: [str(r['day']), r['users']],
    csv_totals_fn=lambda t: ['TOTAL (MAU)', t['mau']],
)

_make_superadmin_report_routes(
    'webhook-health',
    data_fn=_sa_webhook_health_data,
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

def _parse_dob(raw):
    """Parse a YYYY-MM-DD date string from the form, or None when
    blank/bad. Single source of truth lives in
    `api.Modules.Transfers.Services.parse_dob` (PR 78)."""
    from api.Modules.Transfers.Services import parse_dob
    return parse_dob(raw)


def _active_roster(store_id):
    """Names available in the "Processed by" dropdown. Single
    source of truth lives in
    `api.Modules.Transfers.Services.active_roster` (PR 78)."""
    from api.Modules.Transfers.Services import active_roster
    return active_roster(db.session, store_id)


def _pick_employee(store_id, raw_id):
    """Resolve a form `employee_id` value against the roster.
    Single source of truth lives in
    `api.Modules.Transfers.Services.pick_employee` (PR 78)."""
    from api.Modules.Transfers.Services import pick_employee
    return pick_employee(db.session, store_id, raw_id)

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


def _normalize_service_type(raw):
    """Coerce the form input to a known service type. Single
    source of truth lives in
    `api.Modules.Transfers.Services.normalize_service_type`
    (PR 76)."""
    from api.Modules.Transfers.Services import normalize_service_type
    return normalize_service_type(raw)


def _federal_tax_for(send_amount, service_type, store, country=None):
    """The single source of truth for transfer tax. Single source
    of truth lives in
    `api.Modules.Transfers.Services.federal_tax_for` (PR 76).
    """
    from api.Modules.Transfers.Services import federal_tax_for
    return federal_tax_for(send_amount, service_type, store, country)

def _summarize_transfer_changes(before, after, max_fields=4):
    """Format a before/after diff into the audit-log summary
    string. Single source of truth lives in
    `api.Modules.Transfers.Services.summarize_transfer_changes`
    (PR 77)."""
    from api.Modules.Transfers.Services import (
        summarize_transfer_changes,
    )
    return summarize_transfer_changes(before, after, max_fields)


def _record_transfer_audit(transfer, user, action, employee_id,
                            employee_name, summary):
    """Append a TransferAudit row. Single source of truth lives
    in `api.Modules.Transfers.Services.record_transfer_audit`
    (PR 77)."""
    from api.Modules.Transfers.Services import record_transfer_audit
    return record_transfer_audit(
        db.session, transfer, user, action,
        employee_id, employee_name, summary,
    )


def _transfer_snapshot(t):
    """Capture the audited subset of `t` as a dict. Single source
    of truth lives in
    `api.Modules.Transfers.Services.transfer_snapshot` (PR 77)."""
    from api.Modules.Transfers.Services import transfer_snapshot
    return transfer_snapshot(t)

def _transfer_form_ctx(store):
    return dict(
        today=date.today().isoformat(),
        phone_country_codes=PHONE_COUNTRY_CODES,
        mt_companies=store_mt_companies(store),
        service_types=SERVICE_TYPES,
        tax_exempt_services=sorted(_TAX_EXEMPT_SERVICES),
        transfer_countries=TRANSFER_COUNTRIES,
        tax_exempt_countries=sorted(_DOMESTIC_COUNTRIES),
        federal_tax_rate=(store.federal_tax_rate or 0),
    )

# /transfers/new + /transfers/<int>/edit + /transfers/<int>/delete
# moved to blueprints/transfers_redirects.py (D2 phase 14).


# ── Daily Book ───────────────────────────────────────────────
# Companies a new store can pick from on the settings page. The daily book
# and transfer form both pull per-store from Store.companies (resolved via
# store_mt_companies), so this is only the catalog — not a hardcoded list.
KNOWN_MT_COMPANIES = [
    "Intermex", "Maxi", "Barri", "Ria", "Vigo",
    "Inter Cambio", "Sigue", "MoneyGram", "Western Union",
    "Dolex", "Viamericas", "Transfast", "Pangea", "Boss Revolution",
]
# Money-transfer company list resolution now lives in
# api.Modules.Transfers.Services.companies (PR 80). Re-exports
# below preserve the legacy import shape during the migration
# window.
from api.Modules.Transfers.Services import (
    DEFAULT_MT_COMPANIES,
    store_mt_companies,
)

# /daily moved to blueprints/bookkeeping_redirects.py (D2 phase 15).

def _ensure_daily_report(store_id, report_date):
    """Return the DailyReport for (store, date), creating an empty one
    if needed. Single source of truth lives in
    `api.Modules.DailyBook.Services.ensure_daily_report` (PR 34); this
    Flask-scope wrapper exists so the legacy callers
    (_recompute_line_items_total, daily_report POST) keep their
    existing call shape during the migration window."""
    from api.Modules.DailyBook.Services import ensure_daily_report
    return ensure_daily_report(db.session, store_id, report_date)

_DAILY_LOCKED_MSG = "This daily report is locked. Unlock it before making changes."

def _daily_is_locked(store_id, report_date):
    """True iff DailyReport for (store, date) is locked. Single
    source of truth lives in
    `api.Modules.DailyBook.Services.is_daily_report_locked` (PR 81).
    """
    from api.Modules.DailyBook.Services import is_daily_report_locked
    return is_daily_report_locked(db.session, store_id, report_date)

def _reject_if_locked(store_id, report_date, ds):
    """Shared guard for every daily-book write route. Returns a Flask
    response to return to the client when locked, or None when the
    caller may proceed. JSON callers get a 403 payload; HTML callers
    get a flash + redirect back to the report."""
    if not _daily_is_locked(store_id, report_date):
        return None
    if _wants_json():
        return jsonify({"ok": False, "error": _DAILY_LOCKED_MSG}), 403
    flash(_DAILY_LOCKED_MSG, "error")
    return redirect(url_for("bookkeeping_mutations.daily_report", ds=ds))



def _migrate_legacy_line_item_tables():
    """One-time, idempotent migration: copy legacy DailyDrop and
    CheckDeposit rows into DailyLineItem with discriminator kinds
    ('drop' and 'check_deposit'). Runs at boot after Alembic upgrade.

    Why this exists: DailyDrop and CheckDeposit predated the generic
    DailyLineItem(kind=...) model. They were kept side-by-side because
    they had the same shape but the migration cost wasn't worth it
    until enough other kinds (return_payback, cash_purchase, etc.)
    accumulated. Now that we want a single code path for every
    "log multiple things in a day with time + amount + note" widget,
    the migration is finally worth running.

    Idempotency: for each legacy row, we look for a matching
    DailyLineItem (same store_id + report_date + kind + at_time +
    amount). If one exists we skip — a re-run inserts nothing new.
    The legacy tables themselves are NOT dropped; their rows stay
    intact as a safety net + forensic record. A future cleanup PR can
    remove the model classes and tables once a few weeks of main
    have confirmed nothing references them.

    Returns the number of rows inserted (useful for boot logs +
    test assertions). Quiet no-op on a fresh DB where neither legacy
    table has any rows.
    """
    inserted = 0
    try:
        legacy_drops = db.session.query(DailyDrop).all()
    except Exception:
        # Defensive — caller wraps this whole function in a try
        # block; this inner guard catches the case where the legacy
        # tables were already dropped from a freshly-baselined DB.
        legacy_drops = []
    for dd in legacy_drops:
        existing = db.session.query(DailyLineItem).filter_by(
            store_id=dd.store_id, report_date=dd.report_date,
            kind="drop", at_time=dd.drop_time,
        ).filter(DailyLineItem.amount == dd.amount).first()
        if existing is None:
            db.session.add(DailyLineItem(
                store_id=dd.store_id, report_date=dd.report_date,
                kind="drop", at_time=dd.drop_time,
                amount=dd.amount, note=dd.note or "",
                created_by=dd.created_by,
                created_at=dd.created_at or datetime.utcnow(),
            ))
            inserted += 1
    try:
        legacy_checks = db.session.query(CheckDeposit).all()
    except Exception:
        legacy_checks = []
    for cd in legacy_checks:
        existing = db.session.query(DailyLineItem).filter_by(
            store_id=cd.store_id, report_date=cd.report_date,
            kind="check_deposit", at_time=cd.deposit_time,
        ).filter(DailyLineItem.amount == cd.amount).first()
        if existing is None:
            db.session.add(DailyLineItem(
                store_id=cd.store_id, report_date=cd.report_date,
                kind="check_deposit", at_time=cd.deposit_time,
                amount=cd.amount, note=cd.note or "",
                created_by=cd.created_by,
                created_at=cd.created_at or datetime.utcnow(),
            ))
            inserted += 1
    if inserted:
        db.session.commit()
    return inserted


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

def _recompute_line_items_total(kind, store_id, report_date):
    """Sum DailyLineItem rows of the given kind and push the total
    onto the matching DailyReport field. Single source of truth lives
    in `api.Modules.DailyBook.Services.recompute_line_items_total`
    (PR 42); this Flask-scope wrapper resolves the kind→field
    mapping from the legacy `_LINE_ITEM_KINDS` map and forwards."""
    from api.Modules.DailyBook.Services import recompute_line_items_total
    field, _, _ = _LINE_ITEM_KINDS[kind]
    return recompute_line_items_total(
        db.session, store_id, report_date,
        kind=kind, daily_report_field=field,
    )

# Fields on DailyReport the main form still edits. Derived fields
# (outside_cash_drops, checks_deposit, and every DailyReport field
# in _LINE_ITEM_KINDS) are intentionally omitted — each is recomputed
# from its own line-item rows.
_DAILY_REPORT_FIELDS = [
    "taxable_sales","non_taxable","sales_tax","bill_payment_charge","phone_recargas",
    "boost_mobile","money_transfer","money_order","check_cashing_fees","return_check_hold_fees",
    "forward_balance","from_bank","rebates_commissions",
    "cash_deposit","safe_balance","payroll_expense","over_short",
]

# /daily/<ds> (GET, POST) moved to
# blueprints/bookkeeping_mutations.py (D2 phase 26).


def _wants_json():
    """Client explicitly asked for JSON (AJAX from the drops widget).

    Keeping the drop routes dual-mode means they still work as plain HTML
    form posts if JS is off, so the feature degrades gracefully.
    """
    accept = request.accept_mimetypes
    return bool(accept and accept.best == "application/json")

def _line_items_json_payload(kind, store_id, report_date):
    """Current state of a generic line-item widget for a given day + kind."""
    rows = (db.session.query(DailyLineItem)
            .filter_by(store_id=store_id, report_date=report_date, kind=kind)
            .order_by(DailyLineItem.at_time).all())
    total = sum(r.amount for r in rows)
    return {"ok": True, "kind": kind, "total": float(total),
            "items": [r.to_dict() for r in rows]}

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

def _return_check_writeoff_total(store_ids, start, end, status_value):
    """Sum the still-owed balance of return checks marked `status_value`.
    Single source of truth lives in
    `api.Modules.Owners.Services.return_check_writeoff_total` (PR 62).
    """
    from api.Modules.Owners.Services import return_check_writeoff_total
    return return_check_writeoff_total(
        db.session, store_ids, start, end, status_value,
    )


def _return_check_period_aggregates(store_ids, start, end):
    """Sum recoveries / losses / fraud / pending balance for the
    window. Single source of truth lives in
    `api.Modules.Owners.Services.return_check_period_aggregates`
    (PR 62). Returns gain-positive `net_gl`; `_return_check_monthly_pl`
    flips the sign for the P&L expense column.
    """
    from api.Modules.Owners.Services import return_check_period_aggregates
    return return_check_period_aggregates(db.session, store_ids, start, end)


def _return_check_aging_buckets(store_ids, today=None):
    """Pending balance sliced into 0–30 / 31–60 / 61–90 / 90+ day
    buckets. Single source of truth lives in
    `api.Modules.Owners.Services.return_check_aging_buckets` (PR 62).
    """
    from api.Modules.Owners.Services import return_check_aging_buckets
    return return_check_aging_buckets(db.session, store_ids, today=today)


def _bank_charges_for_month(store_id, year, month, category_slug=None,
                             *, prefix=None):
    """Sum the absolute amount of BankTransactions tagged for the given
    month. Single source of truth lives in
    `api.Modules.BankSync.Services.bank_charges_for_month` (PR 57).
    """
    from api.Modules.BankSync.Services import bank_charges_for_month as _svc
    return _svc(db.session, store_id, year, month, category_slug,
                prefix=prefix)

def _bank_charges_breakdown_for_month(store_id, year, month):
    """Two-level breakdown feeding the expandable Bank Charges block on
    the monthly P&L. Single source of truth lives in
    `api.Modules.BankSync.Services.bank_charges_breakdown_for_month`
    (PR 57).
    """
    from api.Modules.BankSync.Services import (
        bank_charges_breakdown_for_month as _svc,
    )
    return _svc(db.session, store_id, year, month)

def _return_check_monthly_pl(store_id, year, month):
    """Signed value for the monthly P&L's Return Check (G/L) line,
    using EXPENSE convention. Single source of truth lives in
    `api.Modules.Owners.Services.return_check_monthly_pl` (PR 62).
    """
    from api.Modules.Owners.Services import return_check_monthly_pl
    return return_check_monthly_pl(db.session, store_id, year, month)


def _return_check_monthly_series(store_ids, today=None):
    """12-month bars for the owner dashboard. Single source of truth
    lives in `api.Modules.Owners.Services.return_check_monthly_series`
    (PR 62).
    """
    from api.Modules.Owners.Services import return_check_monthly_series
    return return_check_monthly_series(db.session, store_ids, today=today)


# ── ACH Batches ──────────────────────────────────────────────
_BATCH_SORT_COLUMNS = {
    "date":     ACHBatch.ach_date,
    "company":  ACHBatch.company,
    "ref":      ACHBatch.batch_ref,
    "amount":   ACHBatch.ach_amount,
    "status":   ACHBatch.status,
}


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
STORES_PER_PAGE = 20

# /superadmin/controls moved to blueprints/superadmin_redirects.py (D2 phase 18).

# /superadmin/send-test-email moved to
# blueprints/superadmin_extras.py (D2 phase 28).


# ── Per-store actions (superadmin) ───────────────────────────
def _store_or_404(store_id): return db.session.get(Store, store_id) or abort(404)

def _parse_extend_days(form, default, maximum):
    """Read `days` from the POST form, default to `default`, clamp to
    [1, maximum]. Used by every route that pushes a deadline forward;
    centralizes the bounds so an admin can't accidentally extend a
    trial by 10,000 days."""
    return max(1, min(int(form.get("days", default) or default), maximum))


def _extended_deadline(existing, days):
    """Push `existing` (a UTC datetime) forward by `days` — but if
    it's already in the past (or unset), push from `now()` instead.
    This avoids the regression where re-extending an already-lapsed
    trial just adds days to a stale past date and stays expired."""
    now = datetime.utcnow()
    base = existing if (existing and existing > now) else now
    return base + timedelta(days=days)


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

def _resolve_catalog_row(catalog_type, slug):
    """Returns the parent catalog row for a (type, slug) pair, or
    None if neither table has a match. Used by the upload + edit
    endpoints to validate the slug before they touch the DB."""
    if catalog_type == "company":
        return db.session.query(TVCompanyCatalog).filter_by(slug=slug).first()
    if catalog_type == "bank":
        return db.session.query(TVBankCatalog).filter_by(slug=slug).first()
    return None

# /superadmin/tv-catalog/<type>/<slug>/logo moved to
# blueprints/superadmin_extras.py (D2 phase 28).


# /superadmin/tv-catalog/<type>/<slug>/edit moved to
# blueprints/superadmin_extras.py (D2 phase 28).


def _slugify_catalog_name(name):
    """Display name → URL-safe lowercase slug. Wraps python-slugify
    with our catalog conventions: '_' separator, max length 60,
    accents stripped, non-alnum collapsed.

      "BBVA Bancomer"      → "bbva_bancomer"
      "Banamex México"     → "banamex_mexico"
      "Cibao Express, S.A." → "cibao_express_s_a"
    """
    if not name:
        return ""
    return slugify(name, separator="_", lowercase=True,
                    max_length=60, word_boundary=False)

def _slugify_bank_name(name, country_code):
    """Banks slug as <iso2>_<name>. Multiple countries can have a
    "BAC Credomatic" (GT/HN/SV); the country prefix keeps them
    distinct so each can carry its own logo."""
    base = _slugify_catalog_name(name)
    if not base:
        return ""
    cc = (country_code or "").strip().lower()
    if cc:
        return (cc + "_" + base)[:60]
    return base

def _next_unique_slug(catalog_type, base_slug):
    """If base_slug exists already, append _2, _3, … until we find
    a free one. Caps at 99 attempts (operationally impossible to
    hit; bails out rather than infinite-looping on a pathological
    state)."""
    if not base_slug:
        return ""
    if _resolve_catalog_row(catalog_type, base_slug) is None:
        return base_slug
    for n in range(2, 100):
        candidate = f"{base_slug}_{n}"[:60]
        if _resolve_catalog_row(catalog_type, candidate) is None:
            return candidate
    return ""  # exhausted; caller flashes the duplicate-slug error

# /superadmin/tv-catalog/new moved to
# blueprints/superadmin_extras.py (D2 phase 28).


# ── Discount codes (superadmin) ──────────────────────────────
def _sync_discount_to_stripe(dc):
    """Best-effort mirror of a DiscountCode into Stripe as a coupon + promotion code.

    Silent on Stripe errors — the local record is still usable for bookkeeping,
    and the operator will see the missing IDs in the UI.
    """
    try:
        coupon_kwargs = {"duration": dc.duration, "name": dc.label or dc.code}
        if dc.percent_off: coupon_kwargs["percent_off"] = dc.percent_off
        if dc.amount_off_cents:
            coupon_kwargs["amount_off"] = dc.amount_off_cents
            coupon_kwargs["currency"] = "usd"
        if dc.duration == "repeating" and dc.duration_in_months:
            coupon_kwargs["duration_in_months"] = dc.duration_in_months
        if dc.max_redemptions: coupon_kwargs["max_redemptions"] = dc.max_redemptions
        if dc.expires_at:
            coupon_kwargs["redeem_by"] = int(dc.expires_at.timestamp())
        coupon = stripe.Coupon.create(**coupon_kwargs)
        promo = stripe.PromotionCode.create(coupon=coupon.id, code=dc.code)
        dc.stripe_coupon_id = coupon.id
        dc.stripe_promotion_code_id = promo.id
    except Exception as e:
        app.logger.warning(f"Stripe discount sync failed for {dc.code}: {e}")

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

from api.Modules.Notifications.Services.locked_day_digest import (
    LOCKED_DAY_BODY as _LOCKED_DAY_BODY,
    LOCKED_DAY_SUBJECT as _LOCKED_DAY_SUBJECT,
    eligible_recipients as _locked_day_recipients_svc,
)


def _fmt_money_2(n: float) -> str:
    """Mirror the React editor's mono money format so the digest
    line items look the same in the inbox as on screen."""
    try:
        return "${:,.2f}".format(float(n or 0))
    except (TypeError, ValueError):
        return "$0.00"


def send_locked_day_digest(report, base_url: str | None = None) -> int:
    """Mail the daily-book close-out summary to every eligible
    recipient (admins + linked owners with the toggle on). Returns
    the count of emails actually sent.

    Safe to call inside the lock route — failures during email
    send don't roll back the lock (we catch + log, matching the
    trial-reminder cron's policy of "deliverability is
    best-effort, don't punish the user for a flaky SMTP").
    """
    from app import Store, User
    if report is None or report.store_id is None:
        return 0
    store = db.session.get(Store, report.store_id)
    if store is None:
        return 0
    base_url = (base_url or os.environ.get("APP_BASE_URL",
                                           "https://dinerobook.com")).rstrip("/")
    date_iso = report.report_date.isoformat() if report.report_date else ""
    date_human = (
        report.report_date.strftime("%B %d, %Y")
        if report.report_date else ""
    )
    locked_by_user = (
        db.session.get(User, report.locked_by) if report.locked_by else None
    )
    locked_by_name = (
        (locked_by_user.full_name or locked_by_user.username)
        if locked_by_user else "an admin"
    )
    view_url = f"{base_url}/app/daily/edit?date={date_iso}"
    notifications_url = f"{base_url}/app/account/notifications"

    receipts = float(report.total_receipts or 0)
    disbursements = float(report.total_disbursements or 0)
    over_short = float(report.over_short or 0)
    net = receipts - disbursements + over_short

    sent = 0
    try:
        recipients = _locked_day_recipients_svc(db.session, store)
    except Exception:
        logger.exception("locked-day digest: recipient query failed")
        return 0

    for u in recipients:
        body = _LOCKED_DAY_BODY.format(
            name=u.full_name or u.username,
            store_name=store.name,
            date_human=date_human,
            locked_by=locked_by_name,
            receipts=_fmt_money_2(receipts),
            disbursements=_fmt_money_2(disbursements),
            over_short=_fmt_money_2(over_short),
            net=_fmt_money_2(net),
            view_url=view_url,
            notifications_url=notifications_url,
        )
        try:
            html = render_email_template(
                "emails/locked_day_digest.html",
                preheader=(
                    f"Daily book locked for {store.name} on "
                    f"{date_human}. Net {_fmt_money_2(net)}."
                ),
                name=u.full_name or "",
                store_name=store.name,
                date_human=date_human,
                locked_by=locked_by_name,
                receipts=_fmt_money_2(receipts),
                disbursements=_fmt_money_2(disbursements),
                over_short=_fmt_money_2(over_short),
                net=_fmt_money_2(net),
                net_negative=(net < 0),
                view_url=view_url,
                notifications_url=notifications_url,
                year=datetime.utcnow().year,
                base_url=base_url,
            )
            subject = _LOCKED_DAY_SUBJECT.format(
                store_name=store.name, date_human=date_human,
            )
            if _send_email(u.email, subject, body, html=html):
                sent += 1
        except Exception:
            logger.exception(
                "locked-day digest: send failed for user_id=%s", u.id,
            )
    return sent

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


# Indexes safety-net. Alembic's autogenerate doesn't always pick
# up index-only changes, so we keep an explicit `CREATE INDEX IF
# NOT EXISTS` list that runs on boot. Idempotent — the IF NOT
# EXISTS no-ops once the index is in place.
#
# Each entry is `(index_name, table, column_csv)`. When adding a
# new index, ALSO declare it on the SQLAlchemy model so a fresh
# Alembic baseline picks it up; this list is the bridge for
# already-deployed DBs.
_ADDED_INDEXES = [
    # Transfer hot path (PR 104).
    ("ix_transfer_store_send_date", "transfer", "store_id, send_date"),
    ("ix_transfer_customer_id",     "transfer", "customer_id"),
    ("ix_transfer_created_by",      "transfer", "created_by"),
    ("ix_transfer_status",          "transfer", "status"),
    ("ix_transfer_confirm_number",  "transfer", "confirm_number"),
    # Customer umbrella-upsert lookup (PR 105). Non-unique on
    # (phone_country, phone_number); the existing unique constraint
    # on (store_id, phone_country, phone_number) stays put for
    # duplicate prevention.
    ("ix_customer_phone",           "customer", "phone_country, phone_number"),
    # User cross-store username lookup (PR 106). Standalone index
    # on `username`; the existing unique constraint on
    # (store_id, username) stays put. `user` is a Postgres reserved
    # word, but `_ensure_added_indexes()` already double-quotes the
    # table name in the DDL — so the plain table name here is
    # correct. Quoting it twice would produce `""user""`.
    ("ix_user_username",            "user",     "username"),
    # LoginEvent DAU/MAU covering composite (PR 107). The
    # standalone `at` and `user_id` indexes from `index=True` stay
    # untouched — this is purely additive.
    ("ix_login_event_at_user",      "login_event", "at, user_id"),
    # Missing FK indexes on `store_id` for cascade-delete + JOIN
    # performance (PR 108). Postgres does not auto-index FKs, and
    # the data-retention purge (`purge_expired_stores`) does
    # `DELETE FROM <tbl> WHERE store_id = ?` on every per-store
    # table — without these, each cascade is a full table scan.
    # Names match SQLAlchemy's `index=True` auto-naming
    # (`ix_<tbl>_store_id`) so fresh installs and existing-prod
    # installs converge on the same name.
    ("ix_store_employee_store_id",      "store_employee",      "store_id"),
    ("ix_operator_audit_log_store_id",  "operator_audit_log",  "store_id"),
    ("ix_transfer_audit_store_id",      "transfer_audit",      "store_id"),
    ("ix_daily_drop_store_id",          "daily_drop",          "store_id"),
    ("ix_check_deposit_store_id",       "check_deposit",       "store_id"),
    ("ix_return_check_store_id",        "return_check",        "store_id"),
    ("ix_daily_line_item_store_id",     "daily_line_item",     "store_id"),
    ("ix_stripe_bank_account_store_id", "stripe_bank_account", "store_id"),
    ("ix_store_owner_link_store_id",    "store_owner_link",    "store_id"),
]


def _ensure_added_indexes():
    """Apply the _ADDED_INDEXES migrations. Idempotent and safe on
    every boot.

    Both sqlite and Postgres support `CREATE INDEX IF NOT EXISTS`,
    so the same DDL works for both. Each statement runs in its own
    transaction on Postgres so one failure doesn't poison the rest.
    Failures log a warning instead of crashing boot — a missing
    index slows queries but doesn't stop the app.
    """
    try:
        dialect = db.engine.dialect.name
    except Exception as e:
        app.logger.warning(f"index migration skipped (no engine): {e}")
        return
    for name, table, cols in _ADDED_INDEXES:
        ddl = f'CREATE INDEX IF NOT EXISTS {name} ON "{table}" ({cols})'
        try:
            if dialect == "sqlite":
                with db.engine.connect() as conn:
                    conn.exec_driver_sql(ddl)
                    conn.commit()
            else:
                with db.engine.begin() as conn:
                    conn.exec_driver_sql(ddl)
        except Exception as e:
            app.logger.warning(
                f"{dialect} CREATE INDEX failed for {name}: {e}")


# Legacy tables that have been removed from the model registry but may
# still exist in production databases. DROP TABLE IF EXISTS is idempotent
# on every restart — safe to leave forever.
_DROPPED_TABLES = ["simplefin_config", "owner_invite_code"]

def _drop_legacy_tables():
    try:
        for table in _DROPPED_TABLES:
            with db.engine.begin() as conn:
                conn.exec_driver_sql(f'DROP TABLE IF EXISTS "{table}"')
    except Exception as e:
        app.logger.warning(f"legacy table drop skipped: {e}")

# Feature flags seeded on first boot. Each entry is (key, label, description, enabled).
# Declaring them here means a fresh install has a real starting set for the UI.
_DEFAULT_FEATURE_FLAGS = [
    ("addon_tv_display", "Add-on: TV Display & Rates",
     "Show the TV Display add-on in the subscription page.", True),
    ("bank_sync", "Bank sync (Stripe)",
     "Enable the Pro-tier Stripe Financial Connections bank sync for stores.", True),
    ("multi_store_owner", "Multi-store owner portal",
     "Allow store admins to generate owner invite codes.", True),
]

def _seed_feature_flags():
    for key, label, description, enabled in _DEFAULT_FEATURE_FLAGS:
        if not db.session.query(FeatureFlag).filter_by(key=key).first():
            db.session.add(FeatureFlag(
                key=key, label=label, description=description,
                enabled_by_default=enabled,
            ))
    db.session.commit()

def _rename_maxi_transfer_to_maxi():
    """One-time idempotent backfill: rename legacy 'Maxi Transfer' to 'Maxi'
    in every place a company name is persisted. Safe on every boot — after
    the first run, nothing matches and the update is a no-op."""
    try:
        db.session.query(Transfer).filter_by(company="Maxi Transfer").update({"company": "Maxi"})
        db.session.query(ACHBatch).filter_by(company="Maxi Transfer").update({"company": "Maxi"})
        db.session.query(MoneyTransferSummary).filter_by(company="Maxi Transfer").update({"company": "Maxi"})
        # Store.companies is a comma-separated string — split, replace, rejoin.
        for s in db.session.query(Store).filter(Store.companies.like("%Maxi Transfer%")).all():
            parts = [p.strip() for p in (s.companies or "").split(",") if p.strip()]
            s.companies = ",".join(["Maxi" if p == "Maxi Transfer" else p for p in parts])
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.warning(f"Maxi Transfer rename backfill skipped: {e}")

def _apply_schema():
    """Bring the DB schema up to the latest Alembic revision.

    Three cases:

    1. **Empty DB** (no ``alembic_version``, no app tables) — fresh
       install. Alembic ``upgrade head`` runs every revision from
       the baseline, creating every table.
    2. **Pre-Alembic DB** (no ``alembic_version`` BUT app tables
       already exist) — the production prod database before chunk
       1 + a few dev databases that were created via the old
       ``db.create_all()`` + ``_ADDED_COLUMNS`` path. Running
       ``upgrade head`` here would try to ``CREATE TABLE`` on
       tables that already exist and crash boot.

       Recovery: ``alembic stamp head`` — record "we're at head"
       without running any DDL. The schema is already current
       because ``db.create_all()`` + ``_ADDED_COLUMNS`` produced
       the same shape the baseline migration produces. Future
       boots see ``alembic_version`` and take case 3.
    3. **Managed DB** (``alembic_version`` exists) — normal path.
       ``upgrade head`` applies any new revisions since the last
       boot. No-op when already at head.

    Critical for the production deploy after the chunk-1 cleanup —
    without the case-2 stamp, the first boot post-merge crashed
    with ``relation feature_flag already exists`` and the
    gunicorn worker exited.

    Flask's existing DB connection is passed in via
    ``cfg.attributes`` so both Alembic and Flask run against the
    SAME database — matters for the in-memory SQLite the tests
    use (each engine creates its own private DB, so an Alembic-
    owned engine would migrate a DB the Flask app can't see).
    """
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", str(db.engine.url))

    prev_skip = os.environ.get("DINEROBOOK_SKIP_INIT_DB")
    try:
        # ``engine.begin()`` opens a transaction and commits on exit
        # (vs ``engine.connect()`` which silently rolls back). Alembic's
        # own ``context.begin_transaction()`` opens a SAVEPOINT inside
        # ours; both commit cleanly on success. The explicit commit is
        # critical for SQLite in-memory tests + StaticPool — without it
        # the upgrade DDL evaporates when the connection returns to the
        # pool and the test suite finds no tables.
        with db.engine.begin() as connection:
            cfg.attributes["connection"] = connection
            inspector = inspect(connection)
            table_names = set(inspector.get_table_names())
            has_alembic_table = "alembic_version" in table_names
            has_app_tables = bool(
                table_names - {"alembic_version"}
            )
            if not has_alembic_table and has_app_tables:
                # Case 2: schema exists from the pre-Alembic boot
                # path (db.create_all + _ADDED_COLUMNS). Stamp head
                # without running any DDL so the next upgrade lands
                # cleanly.
                command.stamp(cfg, "head")
                app.logger.info(
                    "Alembic stamped 'head' on pre-managed DB "
                    "(%d existing tables)",
                    len(table_names),
                )
            else:
                # Case 1 (fresh DB) and case 3 (already managed)
                # both take the standard upgrade path.
                command.upgrade(cfg, "head")
                app.logger.info("Alembic upgrade head: OK")
    finally:
        if prev_skip is None:
            os.environ.pop("DINEROBOOK_SKIP_INIT_DB", None)
        else:
            os.environ["DINEROBOOK_SKIP_INIT_DB"] = prev_skip


def init_db():
    with app.app_context():
        # Alembic builds + upgrades the schema. No db.create_all,
        # no _ADDED_COLUMNS — every schema change is a revision.
        _apply_schema()
        _ensure_added_indexes()
        _drop_legacy_tables()
        _rename_maxi_transfer_to_maxi()
        # One-time copy of legacy DailyDrop + CheckDeposit rows into
        # the generic DailyLineItem table. Idempotent — safe on every
        # boot, no-op once the data has been migrated.
        try:
            _migrate_legacy_line_item_tables()
        except Exception as e:
            app.logger.warning(f"Legacy line-item migration skipped: {e}")
        _seed_feature_flags()
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
