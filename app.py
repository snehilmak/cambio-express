from flask import Flask, request, session, Response
from datetime import datetime, date, timedelta
import base64, os, logging, re, secrets, hashlib, hmac, smtplib, csv, io, sys

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
# call sites keep working. New code imports from the Models
# package directly.
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

# ``active_announcements`` lives in
# ``api.Modules.Announcements.Services``. Imported at module-load
# time so the trial-context processor below doesn't re-do the
# lookup on every request.
from api.Modules.Announcements.Services import (  # noqa: E402
    active_announcements,
)


@app.context_processor
def inject_trial_context():
    """trial_status, trial_days_left, store, announcements, my_referral_code."""
    try:
        announcements = active_announcements(db.session)
    except Exception:
        announcements = []
    user = current_user()
    if not user:
        return {"trial_status": "exempt", "trial_days_left": 0, "store": None,
                "announcements": announcements}
    if user.role in ("superadmin", "owner"):
        return {"trial_status": "exempt", "trial_days_left": 0, "store": None,
                "announcements": announcements}
    from api.Modules.Billing.Services import (
        ensure_referral_code as _svc_ensure_referral_code,
        get_trial_status as _svc_get_trial_status,
    )
    store = current_store()
    status = _svc_get_trial_status(store)
    days_left = 0
    if store and store.trial_ends_at:
        delta = store.trial_ends_at - datetime.utcnow()
        days_left = max(0, delta.days)
    my_referral_code = ""
    if (user.role == "admin"
        and store is not None
        and store.plan in ("basic", "pro")):
        try:
            rc = db.session.query(ReferralCode).filter_by(owner_store_id=store.id).first()
            if rc is None:
                rc = _svc_ensure_referral_code(db.session, store)
                db.session.commit()
            my_referral_code = rc.code if rc else ""
        except Exception as e:
            app.logger.warning(f"referral code lookup failed: {e}")
    return {"trial_status": status, "trial_days_left": days_left, "store": store,
            "announcements": announcements, "my_referral_code": my_referral_code}


@app.context_processor
def inject_impersonation_context():
    """is_impersonating + impersonated_store_name for the banner."""
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
    """active_addons set for sidebar feature-link gating."""
    store = current_store()
    return {"active_addons": store_addon_keys(store)}

@app.context_processor
def inject_theme():
    """Active UI theme: user preference or 'dark' default."""
    user = current_user()
    if user is None:
        return {"theme": "dark"}
    pref = getattr(user, "theme_preference", None)
    if pref not in ("dark", "light"):
        return {"theme": "dark"}
    return {"theme": pref}

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


# ── Pair-code system for the Fire TV / Google TV companion app ─
# TV-initiated flow (mirrors Netflix/YouTube/Disney+ on TV):
# 1) TV POSTs /api/tv-pair/init → server mints code + device_token,
#    returns both, TV polls /api/tv-pair/status.
# 2) Operator types code on /tv-display claim panel.
# 3) Server revokes any prior active TVPairing on the display and
#    creates a fresh one reusing the pending device_token.
# 4) TV's next poll returns "claimed" + per-device URL; rate board
#    loads. addon=tv_display is required to claim.
#
# Ambiguous chars excluded from the alphabet: O / 0 / I / 1 / L / B / 8.
_PAIR_CODE_ALPHABET = "ACDEFGHJKMNPQRTUVWXYZ234579"
_PAIR_CODE_LIFETIME = timedelta(minutes=10)

def _generate_pair_code():
    """6-char code from _PAIR_CODE_ALPHABET. Brute-force resistance
    comes from the 10-min expiry + addon gate, not the code length
    (27**6 ~ 387M)."""
    return "".join(secrets.choice(_PAIR_CODE_ALPHABET) for _ in range(6))

def _generate_device_token():
    """32-byte URL-safe random. Loops 8x on collision against
    TVPairing or TVPendingPair before raising."""
    for _ in range(8):
        t = secrets.token_urlsafe(24)
        if (not db.session.query(TVPairing).filter_by(device_token=t).first()
                and not db.session.query(TVPendingPair).filter_by(device_token=t).first()):
            return t
    raise RuntimeError("Could not mint a unique device_token")


# ── Report Center ────────────────────────────────────────────
from api.Modules.Reports.Services.categories import resolved_categories as _resolved_report_categories


# ── Reports: shared period helpers ───────────────────────────
def _report_period(args):
    """Parse ?from=YYYY-MM-DD&to=YYYY-MM-DD; default current month."""
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
    """Admin → [own store_id]; owner → every linked store_id.
    Logged-out / unauthorised → []."""
    role = session.get("role")
    if role == "owner":
        u = current_user()
        return _svc_owner_store_ids(db.session, u) if u else []
    sid = session.get("store_id")
    return [sid] if sid else []


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


def _make_report_routes(slug, *, data_fn, csv_columns, csv_row_fn,
                         csv_totals_fn=None, csv_fname_prefix=None,
                         extra_args_fn=None):
    """Register admin + owner CSV download routes for one report.
    The HTML drilldown lives on the SPA (spa_cutover redirects)."""
    fname_prefix = csv_fname_prefix or slug
    extra_args_fn = extra_args_fn or (lambda: {})
    underscored = slug.replace("-", "_")

    def _csv():
        return _run_report_csv(data_fn, scope="store",
            columns=csv_columns, row_fn=csv_row_fn,
            totals_row_fn=csv_totals_fn,
            fname_prefix=fname_prefix,
            extra_args=extra_args_fn(),
        )

    app.add_url_rule(f"/reports/{slug}.csv",
                     endpoint=f"report_{underscored}_csv",
                     view_func=_csv, methods=["GET"])
    app.add_url_rule(f"/owner/reports/{slug}.csv",
                     endpoint=f"owner_report_{underscored}_csv",
                     view_func=_csv, methods=["GET"])


def _service_fn(service):
    """Bind db.session to a (store_ids, d_from, d_to, **kw) Reports
    service so _make_report_routes' data_fn signature lines up."""
    def _inner(store_ids, d_from, d_to, **kwargs):
        return service(db.session, store_ids, d_from, d_to, **kwargs)
    return _inner

from api.Modules.Reports.Services import (  # noqa: E402
    ach_volume, bank_charges_by_account, bank_rule_audit,
    bank_txn_breakdown, cancelled_transfers, check_deposits,
    daily_drops, employee_activity, fees_vs_tax,
    high_value_transfers, period_comparison, period_pl,
    returned_check_status,
)

from api.Modules.Reports.Services import new_vs_returning  # noqa: E402


from api.Modules.Superadmin.Services import (  # noqa: E402
    active_stores_by_plan, bank_sync_adoption, churn_cohort,
    conversion_rate, dau_mau, failed_payments, login_activity,
    mrr_arr, owner_adoption, passkey_adoption, password_resets,
    payouts, refunds, retention_queue, signup_funnel,
    suspended_stores, time_to_convert, trial_expiry_timing,
    tv_display_adoption, webhook_health,
)


def _sa_service_fn(service):
    """Bind db.session to a (d_from, d_to, **kw) Superadmin service."""
    def _inner(d_from, d_to, **kwargs):
        return service(db.session, d_from, d_to, **kwargs)
    return _inner


def _csv_response(buf, fname):
    return Response(buf.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'})


def _parse_threshold(args, default=3000):
    try:
        v = float(args.get("threshold") or default)
    except (ValueError, TypeError):
        v = default
    return max(0.0, v)


# Daily-book P&L line constants are re-exported here so existing
# call sites (period P&L, period comparison, monthly P&L feed)
# keep their import shape. Canonical source:
# api.Modules.Reports.Services.period_comparison.
from api.Modules.Reports.Services import (
    PL_EXPENSE_LINES as _PL_EXPENSE_LINES,
    PL_INCOME_LINES as _PL_INCOME_LINES,
)


# ── Report-route registry ───────────────────────────────────
# Each _make_report_routes() registers admin + owner CSV routes.
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


# Owner mirror: every /reports/<slug>.csv admin route gets a matching
# /owner/reports/<slug>.csv endpoint reusing the same handler. Scope
# flips via _report_scope_ids() reading session role.
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
        original = getattr(wrapped, "__wrapped__", wrapped)
        owner_path = "/owner" + rule.rule
        app.add_url_rule(owner_path, endpoint=owner_ep,
                         view_func=original,
                         methods=list(rule.methods - {"HEAD", "OPTIONS"}))


_register_owner_report_mirrors()


# ── Superadmin reports: shared route helpers ─────────────────
# Same shape as _make_report_routes but scoped to
# /superadmin/reports/<slug>.csv. Data functions don't take store_ids.


def _make_superadmin_report_routes(slug, *, data_fn,
                                     csv_columns, csv_row_fn,
                                     csv_totals_fn=None,
                                     csv_fname_prefix=None,
                                     extra_args_fn=None):
    """Register the ``/superadmin/reports/<slug>.csv`` route. HTML
    drilldown lives on the SPA (spa_cutover redirects)."""
    fname_prefix = csv_fname_prefix or slug
    extra_args_fn = extra_args_fn or (lambda: {})
    underscored = slug.replace("-", "_")

    def _csv():
        return _run_report_csv(data_fn, scope="platform",
            columns=csv_columns, row_fn=csv_row_fn,
            totals_row_fn=csv_totals_fn,
            fname_prefix=fname_prefix,
            extra_args=extra_args_fn(),
        )

    app.add_url_rule(f"/superadmin/reports/{slug}.csv",
                     endpoint=f"superadmin_report_{underscored}_csv",
                     view_func=_csv,
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

_RESEND_REPLAY_WINDOW_SECONDS = 5 * 60

def _verify_resend_signature(secret, svix_id, svix_timestamp, svix_signature,
                              raw_body):
    """Verify a Svix-style signature. Header may carry multiple
    space-separated 'v1,{base64}' entries (key rotation); accept any."""
    if not (secret and svix_id and svix_timestamp and svix_signature):
        return False
    try:
        ts_int = int(svix_timestamp)
        now_int = int(datetime.utcnow().timestamp())
        if abs(now_int - ts_int) > _RESEND_REPLAY_WINDOW_SECONDS:
            return False
    except ValueError:
        return False
    if not secret.startswith("whsec_"):
        return False
    try:
        secret_bytes = base64.b64decode(secret[len("whsec_"):])
    except Exception:
        return False
    signed_payload = f"{svix_id}.{svix_timestamp}.".encode() + raw_body
    expected = hmac.new(secret_bytes, signed_payload, hashlib.sha256).digest()
    expected_b64 = base64.b64encode(expected).decode()
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
    """Hard-bounce → stamp email_bounced_at. Complaint → same, plus
    flip every notify_* toggle off."""
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

@app.cli.command("purge-expired-stores")
def purge_expired_stores_cmd():
    """Delete inactive stores past their retention deadline. Run daily."""
    n = purge_expired_stores()
    print(f"Purged {n} expired store(s).")


@app.cli.command("send-trial-reminders")
def send_trial_reminders_cmd():
    """Email admins/owners of stores in expiring_soon. Run daily."""
    from api.Core.Database import SessionLocal
    from api.Modules.Notifications.Services.trial_reminders import run as _run
    with SessionLocal() as s:
        n = _run(s)
    print(f"Sent {n} trial reminder email(s).")


@app.cli.command("broadcast-announcement")
@click.argument("announcement_id", type=int)
def broadcast_announcement_cmd(announcement_id):
    """Resend an announcement email (no-op if already broadcast)."""
    from api.Core.Database import SessionLocal
    from api.Modules.Notifications.Services.broadcasts import run as _run
    with SessionLocal() as s:
        n = _run(s, announcement_id)
    print(f"Broadcast announcement {announcement_id}: {n} email(s) sent.")


@app.cli.command("reset-superadmin")
@click.argument("username", required=False)
@click.option("--reset-2fa", is_flag=True,
              help="Also wipe TOTP secret + recovery codes.")
def reset_superadmin_cmd(username, reset_2fa):
    """Recover a locked-out superadmin from the Render shell.
    /forgot-password intentionally skips this role."""
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

from blueprints import errors as _bp_errors  # noqa: E402
_bp_errors.register(app, current_user)


# Bootstrap shims for legacy ``from app import _X`` test imports;
# canonical home is api.Core.Bootstrap.
from api.Core.Bootstrap import ADDED_INDEXES as _ADDED_INDEXES


def _ensure_added_indexes():
    from api.Core.Bootstrap import ensure_added_indexes
    ensure_added_indexes(db.engine, app.logger)


def init_db():
    """Boot-time DB init: Alembic upgrade + index safety-net + legacy
    drops + line-item migration + feature-flag seed + TV catalog seed
    + superadmin seed. Idempotent on every boot."""
    from api.Core.Bootstrap import (
        apply_schema as _bs_apply_schema,
        drop_legacy_tables as _bs_drop_legacy,
        ensure_added_indexes as _bs_ensure_indexes,
        migrate_legacy_line_item_tables as _bs_migrate_line_items,
        rename_maxi_transfer_to_maxi as _bs_rename_maxi,
        seed_feature_flags as _bs_seed_flags,
    )
    with app.app_context():
        _bs_apply_schema(db.engine, app.logger)
        _bs_ensure_indexes(db.engine, app.logger)
        _bs_drop_legacy(db.engine, app.logger)
        _bs_rename_maxi(db.session, app.logger)
        try:
            _bs_migrate_line_items(db.session)
        except Exception as e:
            app.logger.warning(f"Legacy line-item migration skipped: {e}")
        _bs_seed_flags(db.session)
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

# DINEROBOOK_SKIP_INIT_DB is set by alembic/env.py (it imports app
# only to harvest db.metadata).
if not os.environ.get("DINEROBOOK_SKIP_INIT_DB"):
    init_db()

# ── FastAPI + SPA strangler-fig dispatcher ──────────────────────
# Mounts /api/v2 and /app onto Flask's wsgi_app so Flask's
# test_client can reach them. Production routes via asgi.py and
# bypasses this entirely; conftest.py swaps the ASGIMiddleware
# wrappers for TestClient-backed bridges to avoid the a2wsgi
# leaked-task pathology under coverage.
try:
    from api.main import api_app as _fastapi_app
    from api.spa import spa_app as _spa_app
    from a2wsgi import ASGIMiddleware
    from werkzeug.middleware.dispatcher import DispatcherMiddleware
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
    app.logger.warning(f"FastAPI mount skipped: {_fastapi_err}")


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
