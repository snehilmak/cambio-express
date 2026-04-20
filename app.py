from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, abort
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
from functools import wraps
from calendar import monthrange
import requests, base64, os, calendar, logging, re, secrets, string
import stripe
from slugify import slugify

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cambio-dev-secret-change-in-prod")

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///cambio.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"]        = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"]      = {"pool_pre_ping": True}
db = SQLAlchemy(app)
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")

# ── Models ───────────────────────────────────────────────────
class Store(db.Model):
    __tablename__ = "store"
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(120), nullable=False)
    slug          = db.Column(db.String(60), unique=True, nullable=False)
    email         = db.Column(db.String(120), default="")
    phone         = db.Column(db.String(40), default="")
    address       = db.Column(db.String(255), default="")
    plan          = db.Column(db.String(30), default="trial")
    stripe_customer_id     = db.Column(db.String(60), default="")
    stripe_subscription_id = db.Column(db.String(60), default="")
    is_active     = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    trial_ends_at = db.Column(db.DateTime, nullable=True)
    grace_ends_at = db.Column(db.DateTime, nullable=True)
    addons        = db.Column(db.String(255), default="")
    canceled_at           = db.Column(db.DateTime, nullable=True)
    data_retention_until  = db.Column(db.DateTime, nullable=True)

class User(db.Model):
    __tablename__ = "user"
    id            = db.Column(db.Integer, primary_key=True)
    store_id      = db.Column(db.Integer, db.ForeignKey("store.id"), nullable=True)
    username      = db.Column(db.String(80), nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role          = db.Column(db.String(20), default="employee")
    full_name     = db.Column(db.String(120), default="")
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    is_active     = db.Column(db.Boolean, default=True)
    __table_args__ = (db.UniqueConstraint("store_id","username"),)
    def set_password(self,pw): self.password_hash=generate_password_hash(pw)
    def check_password(self,pw): return check_password_hash(self.password_hash,pw)

class Transfer(db.Model):
    __tablename__ = "transfer"
    id             = db.Column(db.Integer, primary_key=True)
    store_id       = db.Column(db.Integer, db.ForeignKey("store.id"), nullable=False)
    created_by     = db.Column(db.Integer, db.ForeignKey("user.id"))
    send_date      = db.Column(db.Date, nullable=False)
    company        = db.Column(db.String(30), nullable=False)
    sender_name    = db.Column(db.String(120), nullable=False)
    send_amount    = db.Column(db.Float, nullable=False)
    fee            = db.Column(db.Float, default=0.0)
    commission     = db.Column(db.Float, default=0.0)
    recipient_name = db.Column(db.String(120), default="")
    country        = db.Column(db.String(60), default="")
    recipient_phone= db.Column(db.String(40), default="")
    confirm_number = db.Column(db.String(60), default="")
    status         = db.Column(db.String(30), default="Sent")
    status_notes   = db.Column(db.String(255), default="")
    batch_id       = db.Column(db.String(60), default="")
    internal_notes = db.Column(db.String(255), default="")
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at     = db.Column(db.DateTime, default=datetime.utcnow)
    creator        = db.relationship("User", foreign_keys=[created_by])
    @property
    def total_collected(self): return self.send_amount + self.fee

class ACHBatch(db.Model):
    __tablename__ = "ach_batch"
    id             = db.Column(db.Integer, primary_key=True)
    store_id       = db.Column(db.Integer, db.ForeignKey("store.id"), nullable=False)
    ach_date       = db.Column(db.Date, nullable=False)
    company        = db.Column(db.String(30), nullable=False)
    batch_ref      = db.Column(db.String(60), nullable=False)
    ach_amount     = db.Column(db.Float, nullable=False)
    transfer_dates = db.Column(db.String(60), default="")
    status         = db.Column(db.String(30), default="Pending")
    reconciled     = db.Column(db.Boolean, default=False)
    notes          = db.Column(db.String(255), default="")
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("store_id","batch_ref"),)
    @property
    def transfers_total(self):
        v=db.session.query(db.func.sum(Transfer.send_amount)).filter_by(store_id=self.store_id,batch_id=self.batch_ref).scalar()
        return v or 0.0
    @property
    def variance(self): return round(self.ach_amount-self.transfers_total,2)
    @property
    def transfer_count(self): return Transfer.query.filter_by(store_id=self.store_id,batch_id=self.batch_ref).count()

class DailyReport(db.Model):
    __tablename__ = "daily_report"
    id                    = db.Column(db.Integer, primary_key=True)
    store_id              = db.Column(db.Integer, db.ForeignKey("store.id"), nullable=False)
    report_date           = db.Column(db.Date, nullable=False)
    taxable_sales         = db.Column(db.Float, default=0.0)
    non_taxable           = db.Column(db.Float, default=0.0)
    sales_tax             = db.Column(db.Float, default=0.0)
    bill_payment_charge   = db.Column(db.Float, default=0.0)
    phone_recargas        = db.Column(db.Float, default=0.0)
    boost_mobile          = db.Column(db.Float, default=0.0)
    money_transfer        = db.Column(db.Float, default=0.0)
    money_order           = db.Column(db.Float, default=0.0)
    check_cashing_fees    = db.Column(db.Float, default=0.0)
    return_check_hold_fees= db.Column(db.Float, default=0.0)
    return_check_paid_back= db.Column(db.Float, default=0.0)
    forward_balance       = db.Column(db.Float, default=0.0)
    from_bank             = db.Column(db.Float, default=0.0)
    other_cash_in         = db.Column(db.Float, default=0.0)
    rebates_commissions   = db.Column(db.Float, default=0.0)
    cash_purchases        = db.Column(db.Float, default=0.0)
    cash_expense          = db.Column(db.Float, default=0.0)
    check_purchases       = db.Column(db.Float, default=0.0)
    check_expense         = db.Column(db.Float, default=0.0)
    outside_cash_drops    = db.Column(db.Float, default=0.0)
    cash_deposit          = db.Column(db.Float, default=0.0)
    checks_deposit        = db.Column(db.Float, default=0.0)
    safe_balance          = db.Column(db.Float, default=0.0)
    payroll_expense       = db.Column(db.Float, default=0.0)
    other_cash_out        = db.Column(db.Float, default=0.0)
    over_short            = db.Column(db.Float, default=0.0)
    notes                 = db.Column(db.Text, default="")
    updated_at            = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("store_id","report_date"),)
    @property
    def total_receipts(self):
        return sum([self.taxable_sales,self.non_taxable,self.sales_tax,self.bill_payment_charge,
            self.phone_recargas,self.boost_mobile,self.money_transfer,self.money_order,
            self.check_cashing_fees,self.return_check_hold_fees,self.return_check_paid_back,
            self.forward_balance,self.from_bank,self.other_cash_in,self.rebates_commissions])
    @property
    def total_disbursements(self):
        return sum([self.cash_purchases,self.cash_expense,self.check_purchases,self.check_expense,
            self.outside_cash_drops,self.cash_deposit,self.checks_deposit,
            self.payroll_expense,self.other_cash_out])

class MoneyTransferSummary(db.Model):
    __tablename__ = "mt_summary"
    id          = db.Column(db.Integer, primary_key=True)
    store_id    = db.Column(db.Integer, db.ForeignKey("store.id"), nullable=False)
    report_date = db.Column(db.Date, nullable=False)
    company     = db.Column(db.String(40), nullable=False)
    amount      = db.Column(db.Float, default=0.0)
    fees        = db.Column(db.Float, default=0.0)
    commission  = db.Column(db.Float, default=0.0)
    __table_args__ = (db.UniqueConstraint("store_id","report_date","company"),)
    @property
    def individual_total(self): return self.amount+self.fees+self.commission

class MonthlyFinancial(db.Model):
    __tablename__ = "monthly_financial"
    id                    = db.Column(db.Integer, primary_key=True)
    store_id              = db.Column(db.Integer, db.ForeignKey("store.id"), nullable=False)
    year                  = db.Column(db.Integer, nullable=False)
    month                 = db.Column(db.Integer, nullable=False)
    taxable_sales         = db.Column(db.Float, default=0.0)
    non_taxable           = db.Column(db.Float, default=0.0)
    bill_payment_charge   = db.Column(db.Float, default=0.0)
    phone_recargas        = db.Column(db.Float, default=0.0)
    boost_mobile          = db.Column(db.Float, default=0.0)
    check_cashing_fees    = db.Column(db.Float, default=0.0)
    return_check_hold_fees= db.Column(db.Float, default=0.0)
    rebates_commissions   = db.Column(db.Float, default=0.0)
    mt_commission_in_bank = db.Column(db.Float, default=0.0)
    other_income_1        = db.Column(db.Float, default=0.0)
    other_income_2        = db.Column(db.Float, default=0.0)
    other_income_3        = db.Column(db.Float, default=0.0)
    cash_purchases        = db.Column(db.Float, default=0.0)
    check_purchases       = db.Column(db.Float, default=0.0)
    cash_expenses         = db.Column(db.Float, default=0.0)
    check_expenses        = db.Column(db.Float, default=0.0)
    cash_payroll          = db.Column(db.Float, default=0.0)
    bank_charges_210      = db.Column(db.Float, default=0.0)
    bank_charges_230      = db.Column(db.Float, default=0.0)
    credit_card_fees      = db.Column(db.Float, default=0.0)
    money_order_rent      = db.Column(db.Float, default=0.0)
    emaginenet_tech       = db.Column(db.Float, default=0.0)
    irs_payroll_tax       = db.Column(db.Float, default=0.0)
    texas_workforce       = db.Column(db.Float, default=0.0)
    other_taxes           = db.Column(db.Float, default=0.0)
    accounting_charges    = db.Column(db.Float, default=0.0)
    return_check_gl       = db.Column(db.Float, default=0.0)
    other_expense_1       = db.Column(db.Float, default=0.0)
    other_expense_2       = db.Column(db.Float, default=0.0)
    other_expense_3       = db.Column(db.Float, default=0.0)
    other_expense_4       = db.Column(db.Float, default=0.0)
    other_expense_5       = db.Column(db.Float, default=0.0)
    over_short            = db.Column(db.Float, default=0.0)
    borrowed_money_return = db.Column(db.Float, default=0.0)
    profit_distributed    = db.Column(db.Float, default=0.0)
    cash_carry_forward    = db.Column(db.Float, default=0.0)
    notes                 = db.Column(db.Text, default="")
    updated_at            = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("store_id","year","month"),)
    @property
    def total_revenue(self):
        return sum([self.taxable_sales,self.non_taxable,self.bill_payment_charge,
            self.phone_recargas,self.boost_mobile,self.check_cashing_fees,
            self.return_check_hold_fees,self.rebates_commissions,self.mt_commission_in_bank,
            self.other_income_1,self.other_income_2,self.other_income_3])
    @property
    def total_purchases(self): return self.cash_purchases+self.check_purchases
    @property
    def total_expenses(self):
        return sum([self.cash_expenses,self.check_expenses,self.cash_payroll,
            self.bank_charges_210,self.bank_charges_230,self.credit_card_fees,
            self.money_order_rent,self.emaginenet_tech,self.irs_payroll_tax,
            self.texas_workforce,self.other_taxes,self.accounting_charges,
            self.return_check_gl,self.other_expense_1,self.other_expense_2,
            self.other_expense_3,self.other_expense_4,self.other_expense_5])
    @property
    def net_income(self): return self.total_revenue-self.total_purchases-self.total_expenses+self.over_short

class SimpleFINConfig(db.Model):
    __tablename__ = "simplefin_config"
    id          = db.Column(db.Integer, primary_key=True)
    store_id    = db.Column(db.Integer, db.ForeignKey("store.id"), unique=True, nullable=False)
    access_url  = db.Column(db.String(500), default="")
    last_synced = db.Column(db.DateTime, nullable=True)

class StoreOwnerLink(db.Model):
    __tablename__ = "store_owner_link"
    id        = db.Column(db.Integer, primary_key=True)
    owner_id  = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    store_id  = db.Column(db.Integer, db.ForeignKey("store.id"), nullable=False)
    linked_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("owner_id", "store_id"),)

class OwnerInviteCode(db.Model):
    __tablename__ = "owner_invite_code"
    id               = db.Column(db.Integer, primary_key=True)
    store_id         = db.Column(db.Integer, db.ForeignKey("store.id"), nullable=False)
    code             = db.Column(db.String(8), unique=True, nullable=False)
    created_by       = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at       = db.Column(db.DateTime, nullable=False)
    used_at          = db.Column(db.DateTime, nullable=True)
    used_by_owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

# ── Superadmin models ────────────────────────────────────────
# Platform-level tables owned by the superadmin. None of these are
# scoped to a single store so they're safe from the store purge job.

class DiscountCode(db.Model):
    """Promo code the superadmin mints; synced to Stripe when possible.

    Either percent_off *or* amount_off_cents is set — never both. When Stripe
    is reachable we create a coupon + promotion code and store their IDs;
    customers can then enter the code at checkout because subscribe_checkout
    passes allow_promotion_codes=True.
    """
    __tablename__ = "discount_code"
    id                        = db.Column(db.Integer, primary_key=True)
    code                      = db.Column(db.String(40), unique=True, nullable=False)
    label                     = db.Column(db.String(120), default="")
    percent_off               = db.Column(db.Integer, nullable=True)   # 1..100
    amount_off_cents          = db.Column(db.Integer, nullable=True)   # USD cents
    duration                  = db.Column(db.String(16), default="once")  # once | forever | repeating
    duration_in_months        = db.Column(db.Integer, nullable=True)
    max_redemptions           = db.Column(db.Integer, nullable=True)
    redeemed_count            = db.Column(db.Integer, default=0)
    expires_at                = db.Column(db.DateTime, nullable=True)
    stripe_coupon_id          = db.Column(db.String(60), default="")
    stripe_promotion_code_id  = db.Column(db.String(60), default="")
    is_active                 = db.Column(db.Boolean, default=True)
    created_at                = db.Column(db.DateTime, default=datetime.utcnow)
    created_by                = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    @property
    def value_label(self):
        if self.percent_off:
            return f"{self.percent_off}% off"
        if self.amount_off_cents:
            return f"${self.amount_off_cents / 100:.2f} off"
        return "—"

class FeatureFlag(db.Model):
    """Global feature switch the superadmin can flip without a deploy.

    enabled_by_default is the baseline; StoreFeatureOverride can flip it for a
    single store (e.g. beta-test a feature with one customer).
    """
    __tablename__ = "feature_flag"
    id                 = db.Column(db.Integer, primary_key=True)
    key                = db.Column(db.String(60), unique=True, nullable=False)
    label              = db.Column(db.String(120), default="")
    description        = db.Column(db.Text, default="")
    enabled_by_default = db.Column(db.Boolean, default=True)
    created_at         = db.Column(db.DateTime, default=datetime.utcnow)

class StoreFeatureOverride(db.Model):
    """Per-store override of a FeatureFlag's global default."""
    __tablename__ = "store_feature_override"
    id         = db.Column(db.Integer, primary_key=True)
    store_id   = db.Column(db.Integer, db.ForeignKey("store.id"), nullable=False)
    flag_key   = db.Column(db.String(60), nullable=False)
    enabled    = db.Column(db.Boolean, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    __table_args__ = (db.UniqueConstraint("store_id", "flag_key"),)

class SuperadminAuditLog(db.Model):
    """Append-only record of platform-admin actions for traceability."""
    __tablename__ = "superadmin_audit_log"
    id          = db.Column(db.Integer, primary_key=True)
    admin_id    = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    admin_name  = db.Column(db.String(120), default="")  # snapshot in case the user row is deleted
    action      = db.Column(db.String(60), nullable=False)   # e.g. "extend_trial", "comp_plan"
    target_type = db.Column(db.String(30), default="")       # "store" | "discount" | "feature"
    target_id   = db.Column(db.String(60), default="")
    details     = db.Column(db.Text, default="")             # free-form, usually short JSON/text
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

class Announcement(db.Model):
    """Global banner the superadmin can post across the app.

    Shown on every admin/employee page between starts_at and expires_at while
    is_active. Level maps onto the banner-* utility classes in app.css.
    """
    __tablename__ = "announcement"
    id         = db.Column(db.Integer, primary_key=True)
    message    = db.Column(db.Text, nullable=False)
    level      = db.Column(db.String(16), default="info")  # info | warning | error | success
    is_active  = db.Column(db.Boolean, default=True)
    starts_at  = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

# ── Auth ─────────────────────────────────────────────────────
def current_user():  return db.session.get(User,  session["user_id"])  if "user_id"  in session else None
def current_store(): return db.session.get(Store, session["store_id"]) if session.get("store_id") else None

_TRIAL_EXEMPT = {"subscribe", "subscribe_checkout", "subscribe_success", "logout",
                 "owner_dashboard", "owner_link_store", "owner_unlink_store",
                 "admin_subscription", "admin_subscription_billing_portal",
                 "admin_subscription_toggle_addon", "admin_subscription_cancel"}

# ── Add-ons catalog ──────────────────────────────────────────
# Each add-on has a stable key used in the Store.addons CSV column.
# Add-ons require an active paid subscription (basic or pro) before they
# can be activated. status="coming_soon" disables activation in the UI
# and on the server until the underlying integration ships.
ADDONS_CATALOG = {
    "tv_display": {
        "name": "TV Display & Live Rates",
        "price_cents": 200,
        "price_label": "$2 / month",
        "tagline": "Show ads & money transfer rates on the TV behind your counter.",
        "description": (
            "Connects this store to the upcoming DineroBook TV app on Amazon Fire TV "
            "and Google TV. Stream your branded display ads and live money transfer "
            "rates straight from your DineroBook account — inspired by Xenok Display."
        ),
        "status": "coming_soon",
    },
}

def store_addon_keys(store):
    """Return the set of add-on keys currently active for a store."""
    if not store or not store.addons:
        return set()
    return {k.strip() for k in store.addons.split(",") if k.strip()}

def store_has_paid_plan(store):
    return bool(store) and store.plan in ("basic", "pro")

# ── Cancellation & data retention ────────────────────────────
DATA_RETENTION_DAYS = 180  # 6 months

def data_retention_days_left(store):
    """Days until cancelled-store data is purged. Returns None if not scheduled."""
    if not store or not store.data_retention_until:
        return None
    delta = store.data_retention_until - datetime.utcnow()
    return max(0, delta.days)

# ── Superadmin helpers ───────────────────────────────────────
def record_audit(action, target_type="", target_id="", details=""):
    """Append a row to the superadmin audit log.

    Safe to call from any request — reads the current user from session so it
    can stamp admin_name even if the User row is later deleted.
    """
    u = current_user()
    if not u:
        return
    row = SuperadminAuditLog(
        admin_id=u.id,
        admin_name=u.full_name or u.username or "",
        action=action,
        target_type=str(target_type)[:30],
        target_id=str(target_id)[:60],
        details=str(details)[:2000],
    )
    db.session.add(row)
    # Intentionally no commit — caller commits as part of its own transaction.

def store_feature_enabled(store, flag_key):
    """Resolve a feature flag for a store: per-store override > global default > True."""
    if store is not None:
        override = StoreFeatureOverride.query.filter_by(
            store_id=store.id, flag_key=flag_key
        ).first()
        if override is not None:
            return bool(override.enabled)
    flag = FeatureFlag.query.filter_by(key=flag_key).first()
    if flag is None:
        return True  # Unknown flag = allow by default (fail-open for undeclared features).
    return bool(flag.enabled_by_default)

def stripe_health_check():
    """Return a dict describing the Stripe integration state.

    Keys:
      env: {secret_key, webhook_secret, basic_price_id, pro_price_id}  (booleans)
      ok:  True if we reached Stripe and retrieved the account
      account_email / account_id / mode: filled on success
      price_ok: {basic, pro} — booleans, True if the ID resolved
      error: str on failure
    """
    env = {
        "secret_key":      bool(os.environ.get("STRIPE_SECRET_KEY")),
        "webhook_secret":  bool(os.environ.get("STRIPE_WEBHOOK_SECRET")),
        "basic_price_id":  bool(os.environ.get("STRIPE_BASIC_PRICE_ID")),
        "pro_price_id":    bool(os.environ.get("STRIPE_PRO_PRICE_ID")),
    }
    result = {"env": env, "ok": False, "error": "", "price_ok": {"basic": False, "pro": False}}
    if not env["secret_key"]:
        result["error"] = "STRIPE_SECRET_KEY is not configured."
        return result
    try:
        acct = stripe.Account.retrieve()
        result["ok"] = True
        result["account_id"]    = acct.get("id", "")
        result["account_email"] = acct.get("email", "")
        # Test-mode keys start with sk_test_; live keys with sk_live_.
        result["mode"] = "test" if (os.environ.get("STRIPE_SECRET_KEY", "").startswith("sk_test_")) else "live"
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        return result
    for plan in ("basic", "pro"):
        pid = os.environ.get(f"STRIPE_{plan.upper()}_PRICE_ID", "")
        if not pid:
            continue
        try:
            stripe.Price.retrieve(pid)
            result["price_ok"][plan] = True
        except Exception:
            pass
    return result

def active_announcements():
    """Currently-visible announcements (active, within start/expiry window)."""
    now = datetime.utcnow()
    q = Announcement.query.filter_by(is_active=True)
    rows = q.order_by(Announcement.created_at.desc()).all()
    out = []
    for a in rows:
        if a.starts_at and a.starts_at > now:
            continue
        if a.expires_at and a.expires_at <= now:
            continue
        out.append(a)
    return out

def login_required(f):
    @wraps(f)
    def d(*a, **k):
        if "user_id" not in session:
            return redirect(url_for("login"))
        user = current_user()
        if user and user.role != "superadmin" and f.__name__ not in _TRIAL_EXEMPT:
            store = current_store()
            if store and get_trial_status(store) == "expired":
                return redirect(url_for("subscribe"))
        return f(*a, **k)
    return d

def admin_required(f):
    @wraps(f)
    def d(*a,**k):
        if "user_id" not in session: return redirect(url_for("login"))
        u=current_user()
        if not u or u.role not in ("admin","superadmin"):
            flash("Admin access required.","error"); return redirect(url_for("dashboard"))
        return f(*a,**k)
    return d

def superadmin_required(f):
    @wraps(f)
    def d(*a,**k):
        if "user_id" not in session: return redirect(url_for("login"))
        u=current_user()
        if not u or u.role!="superadmin":
            flash("Superadmin access required.","error"); return redirect(url_for("dashboard"))
        return f(*a,**k)
    return d

def owner_required(f):
    @wraps(f)
    def d(*a, **k):
        if "user_id" not in session:
            return redirect(url_for("login"))
        u = current_user()
        if not u or u.role != "owner":
            abort(403)
        return f(*a, **k)
    return d

# ── Trial Status ─────────────────────────────────────────────
def get_trial_status(store):
    """Return trial status string for the given store.

    Returns: "exempt" | "active" | "expiring_soon" | "grace" | "expired"
    """
    if store is None:
        return "exempt"
    if store.plan in ("basic", "pro"):
        return "exempt"
    if store.plan == "inactive":
        return "expired"
    if store.trial_ends_at is None:
        return "exempt"
    now = datetime.utcnow()
    if store.grace_ends_at is not None and now >= store.grace_ends_at:
        return "expired"
    if now >= store.trial_ends_at:
        return "grace"
    if now >= store.trial_ends_at - timedelta(days=3):
        return "expiring_soon"
    return "active"

@app.context_processor
def inject_trial_context():
    """Inject trial_status, trial_days_left, store, and announcements globally.

    Announcements are visible on every page for every role (including logged-out)
    so the superadmin can reach the whole audience with one message.
    """
    try:
        announcements = active_announcements()
    except Exception:
        # Table may not exist yet on a fresh install between db.create_all() calls.
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
    return {"trial_status": status, "trial_days_left": days_left, "store": store,
            "announcements": announcements}

# ── SimpleFIN (FIXED) ────────────────────────────────────────
def require_store_context():
    """Returns store_id or None. Routes needing a store should call this."""
    return session.get("store_id")

def get_sfin_cfg(store_id):
    return SimpleFINConfig.query.filter_by(store_id=store_id).first()

def simplefin_fetch(store_id):
    cfg=get_sfin_cfg(store_id)
    if not cfg or not cfg.access_url: return None,"SimpleFIN not configured."
    try:
        url=cfg.access_url.rstrip("/")
        if not url.endswith("/accounts"): url+="/accounts"
        r=requests.get(url,timeout=20)
        r.raise_for_status(); data=r.json()
        cfg.last_synced=datetime.utcnow(); db.session.commit()
        return data,None
    except requests.exceptions.ConnectionError: return None,"Cannot connect to SimpleFIN. Check internet."
    except requests.exceptions.Timeout: return None,"SimpleFIN timed out. Try again."
    except requests.exceptions.HTTPError as e:
        code=e.response.status_code
        if code==403: return None,"SimpleFIN access denied. Your URL may be expired — generate a new token."
        return None,f"SimpleFIN error {code}. Try reconnecting."
    except Exception as e:
        app.logger.error(f"SimpleFIN: {e}"); return None,f"Error: {str(e)}"

def simplefin_claim_token(token_raw,store_id):
    token_raw=token_raw.strip()
    # Direct access URL
    if token_raw.startswith("https://"):
        cfg=get_sfin_cfg(store_id) or SimpleFINConfig(store_id=store_id)
        cfg.access_url=token_raw; db.session.add(cfg); db.session.commit()
        return True,"Access URL saved. Testing connection..."
    # Base64 setup token
    try:
        clean=token_raw.replace(" ","").replace("\n","").replace("\r","")
        pad=4-len(clean)%4
        if pad!=4: clean+="="*pad
        claim_url=base64.b64decode(clean).decode("utf-8").strip()
    except Exception as e:
        return False,f"Invalid token — make sure you copied it completely. ({e})"
    if not claim_url.startswith("https://"):
        return False,"Token decoded to an unexpected value. Generate a fresh token from SimpleFIN."
    try:
        r=requests.post(claim_url,timeout=20)
        if r.status_code==403: return False,"This token was already used. Generate a new one at simplefin.org."
        r.raise_for_status()
        access_url=r.text.strip()
        if not access_url.startswith("https://"):
            return False,"SimpleFIN returned unexpected data. Try a new token."
        cfg=get_sfin_cfg(store_id) or SimpleFINConfig(store_id=store_id)
        cfg.access_url=access_url; db.session.add(cfg); db.session.commit()
        return True,"SimpleFIN connected successfully!"
    except requests.exceptions.HTTPError as e:
        return False,f"SimpleFIN claim failed ({e.response.status_code}). Token may be expired."
    except Exception as e:
        return False,f"Connection error: {str(e)}"

# ── Login ────────────────────────────────────────────────────
@app.route("/")
def landing():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("landing.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        u = current_user()
        if u and u.role == "owner":
            return redirect(url_for("owner_dashboard"))
        return redirect(url_for("dashboard"))
    error=None
    if request.method=="POST":
        username=request.form.get("username","").strip()
        u=User.query.filter_by(username=username).first()
        if u and u.is_active and u.check_password(request.form.get("password","")):
            if u.role == "employee":
                error = "Please use your store's login link."
            else:
                session["user_id"]=u.id; session["role"]=u.role; session["store_id"]=u.store_id
                if u.role == "owner":
                    return redirect(url_for("owner_dashboard"))
                return redirect(url_for("dashboard"))
        else:
            error="Invalid username or password."
    return render_template("login.html",error=error)

@app.route("/login/<slug>", methods=["GET", "POST"])
def login_store(slug):
    store = Store.query.filter_by(slug=slug).first_or_404()
    if not store.is_active:
        abort(404)
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        u = User.query.filter_by(username=username, store_id=store.id).first()
        if u and u.is_active and u.check_password(request.form.get("password", "")):
            session["user_id"] = u.id
            session["role"] = u.role
            session["store_id"] = u.store_id
            return redirect(url_for("dashboard"))
        error = "Invalid username or password."
    return render_template("login_store.html", store=store, error=error)

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if "user_id" in session and request.method == "GET":
        return redirect(url_for("dashboard"))
    errors = {}
    form = {}
    if request.method == "POST":
        store_name = request.form.get("store_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        phone = request.form.get("phone", "").strip()
        form = {"store_name": store_name, "email": email, "phone": phone}

        if not store_name:
            errors["store_name"] = "Store name is required."
        if not email:
            errors["email"] = "Email is required."
        if not password:
            errors["password"] = "Password is required."
        elif len(password) < 8:
            errors["password"] = "Password must be at least 8 characters."

        if not errors:
            existing = User.query.filter_by(username=email).filter(
                User.store_id.isnot(None)).first()
            if existing:
                errors["email"] = "An account with this email already exists."

        if not errors:
            slug_base = slugify(store_name)
            slug = slug_base
            counter = 1
            while Store.query.filter_by(slug=slug).first():
                slug = f"{slug_base}-{counter}"
                counter += 1
            s = Store(name=store_name, slug=slug, email=email,
                      phone=phone, plan="trial")
            db.session.add(s)
            db.session.flush()
            s.trial_ends_at = datetime.utcnow() + timedelta(days=7)
            s.grace_ends_at = s.trial_ends_at + timedelta(days=4)
            u = User(store_id=s.id, username=email,
                     full_name=store_name, role="admin")
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            session["user_id"] = u.id
            session["role"] = u.role
            session["store_id"] = s.id
            flash("Welcome! Your 7-day free trial has started.", "success")
            return redirect(url_for("dashboard"))

    return render_template("signup.html", errors=errors, form=form)

@app.route("/signup/owner", methods=["GET", "POST"])
def signup_owner():
    if "user_id" in session:
        u = current_user()
        if u and u.role == "owner":
            return redirect(url_for("owner_dashboard"))
        return redirect(url_for("dashboard"))
    errors = {}
    form = {}
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email     = request.form.get("email", "").strip().lower()
        password  = request.form.get("password", "")
        form = {"full_name": full_name, "email": email}
        if not full_name:
            errors["full_name"] = "Full name is required."
        if not email:
            errors["email"] = "Email is required."
        elif not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            errors["email"] = "Enter a valid email address."
        if not password:
            errors["password"] = "Password is required."
        elif len(password) < 8:
            errors["password"] = "Password must be at least 8 characters."
        if not errors:
            taken_null  = User.query.filter(User.username == email, User.store_id.is_(None)).first()
            taken_admin = User.query.filter(User.username == email, User.role == "admin").first()
            if taken_null or taken_admin:
                errors["email"] = "An account with this email already exists."
        if not errors:
            u = User(store_id=None, username=email, full_name=full_name, role="owner")
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            session["user_id"]  = u.id
            session["role"]     = "owner"
            session["store_id"] = None
            return redirect(url_for("owner_dashboard"))
    return render_template("signup_owner.html", errors=errors, form=form)

@app.route("/logout")
def logout():
    user = current_user()
    store = current_store()
    is_employee = user and user.role == "employee"
    slug = store.slug if store else None
    session.clear()
    if is_employee and slug:
        return redirect(url_for("login_store", slug=slug))
    return redirect(url_for("login"))

@app.route("/owner/dashboard")
@owner_required
def owner_dashboard():
    u = current_user()
    period = request.args.get("period", "today")
    today = date.today()

    links = StoreOwnerLink.query.filter_by(owner_id=u.id).all()
    store_ids = [l.store_id for l in links]
    stores = Store.query.filter(Store.id.in_(store_ids)).order_by(Store.name).all() if store_ids else []

    if period == "today":
        date_start = date_end = today
    elif period == "month":
        date_start = date(today.year, today.month, 1)
        date_end = today
    else:
        date_start = date(today.year, 1, 1)
        date_end = today

    if store_ids:
        agg_transfer_count = Transfer.query.filter(
            Transfer.store_id.in_(store_ids),
            Transfer.send_date >= date_start,
            Transfer.send_date <= date_end
        ).count()
        agg_volume = db.session.query(db.func.sum(Transfer.send_amount)).filter(
            Transfer.store_id.in_(store_ids),
            Transfer.send_date >= date_start,
            Transfer.send_date <= date_end
        ).scalar() or 0.0
        agg_over_short = db.session.query(db.func.sum(DailyReport.over_short)).filter(
            DailyReport.store_id.in_(store_ids),
            DailyReport.report_date >= date_start,
            DailyReport.report_date <= date_end
        ).scalar() or 0.0
    else:
        agg_transfer_count = 0
        agg_volume = 0.0
        agg_over_short = 0.0

    # Batch Transfer stats for all stores in one query
    transfer_rows = db.session.query(
        Transfer.store_id,
        db.func.count(Transfer.id),
        db.func.sum(Transfer.send_amount),
    ).filter(
        Transfer.store_id.in_(store_ids),
        Transfer.send_date >= date_start,
        Transfer.send_date <= date_end,
    ).group_by(Transfer.store_id).all() if store_ids else []
    transfer_stats = {sid: (cnt, vol or 0.0) for sid, cnt, vol in transfer_rows}

    # Batch DailyReport rows for all stores in one query
    all_reports = DailyReport.query.filter(
        DailyReport.store_id.in_(store_ids),
        DailyReport.report_date >= date_start,
        DailyReport.report_date <= date_end,
    ).all() if store_ids else []
    reports_by_store = {}
    for r in all_reports:
        reports_by_store.setdefault(r.store_id, []).append(r)

    store_data = []
    for store in stores:
        t_count, t_volume = transfer_stats.get(store.id, (0, 0.0))
        reports = reports_by_store.get(store.id, [])
        store_data.append({
            "store": store,
            "transfer_count": t_count,
            "volume": t_volume,
            "total_receipts": sum(r.total_receipts for r in reports),
            "over_short": sum(r.over_short for r in reports),
        })

    return render_template("owner_dashboard.html",
        user=u, period=period,
        agg_transfer_count=agg_transfer_count,
        agg_volume=agg_volume,
        agg_over_short=agg_over_short,
        store_count=len(stores),
        store_data=store_data,
    )

@app.route("/owner/link", methods=["POST"])
@owner_required
def owner_link_store():
    """Redeem an 8-char invite code to link the current owner to a store."""
    u = current_user()
    code = request.form.get("code", "").strip().upper()
    now = datetime.utcnow()
    # NOTE: TOCTOU window between lookup and commit — safe under SQLite (serialised
    # writes) but a Postgres migration should add SELECT FOR UPDATE here.
    invite = OwnerInviteCode.query.filter(
        OwnerInviteCode.code == code,
        OwnerInviteCode.used_at.is_(None),
        OwnerInviteCode.expires_at > now
    ).first()
    if not invite:
        flash("Invalid or expired code.", "error")
        return redirect(url_for("owner_dashboard"))
    already = StoreOwnerLink.query.filter_by(owner_id=u.id, store_id=invite.store_id).first()
    if already:
        flash("You're already connected to this store.", "info")
        return redirect(url_for("owner_dashboard"))
    link = StoreOwnerLink(owner_id=u.id, store_id=invite.store_id)
    invite.used_at = now
    invite.used_by_owner_id = u.id
    db.session.add(link)
    db.session.commit()
    store = db.session.get(Store, invite.store_id)
    flash(f"{store.name} connected successfully.", "success")
    return redirect(url_for("owner_dashboard"))


@app.route("/owner/unlink/<int:store_id>", methods=["POST"])
@owner_required
def owner_unlink_store(store_id):
    """Remove an owner→store relationship. Does not affect store data itself."""
    u = current_user()
    link = StoreOwnerLink.query.filter_by(owner_id=u.id, store_id=store_id).first_or_404()
    db.session.delete(link)
    db.session.commit()
    flash("Store removed from your account.", "success")
    return redirect(url_for("owner_dashboard"))

@app.route("/subscribe")
@login_required
def subscribe():
    user = current_user()
    store = current_store()
    return render_template("subscribe.html", user=user, store=store)

@app.route("/subscribe/checkout", methods=["POST"])
@login_required
def subscribe_checkout():
    """Create a Stripe Checkout Session for the chosen plan and redirect there.

    The webhook (checkout.session.completed) is what actually flips the store
    onto the new plan — this route only initiates the payment flow.
    """
    store = current_store()
    plan = request.form.get("plan", "").strip()
    price_map = {
        "basic": os.environ.get("STRIPE_BASIC_PRICE_ID", ""),
        "pro":   os.environ.get("STRIPE_PRO_PRICE_ID", ""),
    }
    if plan not in price_map or not price_map[plan]:
        flash("Invalid plan selected.", "error")
        return redirect(url_for("subscribe"))
    try:
        kwargs = dict(
            mode="subscription",
            line_items=[{"price": price_map[plan], "quantity": 1}],
            metadata={"store_id": str(store.id)},
            success_url=url_for("subscribe_success", _external=True),
            cancel_url=url_for("subscribe", _external=True),
            # Surface the discount-code entry field on the Stripe checkout page.
            allow_promotion_codes=True,
        )
        if store.stripe_customer_id:
            kwargs["customer"] = store.stripe_customer_id
        checkout_session = stripe.checkout.Session.create(**kwargs)
        return redirect(checkout_session.url, code=303)
    except stripe.error.StripeError as e:
        app.logger.error(f"Stripe error: {e}")
        flash("Payment service error. Please try again.", "error")
        return redirect(url_for("subscribe"))

@app.route("/subscribe/success")
@login_required
def subscribe_success():
    user = current_user()
    store = current_store()
    return render_template("subscribe_success.html", user=user, store=store)

# ── Subscription management ──────────────────────────────────
@app.route("/admin/subscription")
@admin_required
def admin_subscription():
    user = current_user()
    store = current_store()
    active_addons = store_addon_keys(store)
    # Each add-on can be gated behind a feature flag keyed "addon_<key>".
    # If no flag has been declared the add-on shows normally (fail-open).
    visible_addons = {
        k: v for k, v in ADDONS_CATALOG.items()
        if store_feature_enabled(store, f"addon_{k}")
    }
    plan_labels = {
        "trial":    "Free Trial",
        "basic":    "Basic",
        "pro":      "Pro",
        "inactive": "Inactive",
    }
    plan_prices = {"basic": "$20 / month", "pro": "$30 / month"}
    return render_template("admin_subscription.html",
        user=user, store=store,
        addons_catalog=visible_addons,
        active_addons=active_addons,
        has_paid_plan=store_has_paid_plan(store),
        plan_label=plan_labels.get(store.plan if store else "", "Unknown"),
        plan_price=plan_prices.get(store.plan if store else "", ""),
        retention_days_left=data_retention_days_left(store),
        retention_total_days=DATA_RETENTION_DAYS,
    )

@app.route("/admin/subscription/billing-portal", methods=["POST"])
@admin_required
def admin_subscription_billing_portal():
    store = current_store()
    if not store or not store.stripe_customer_id:
        flash("No billing account found. Choose a plan to get started.", "error")
        return redirect(url_for("subscribe"))
    try:
        portal = stripe.billing_portal.Session.create(
            customer=store.stripe_customer_id,
            return_url=url_for("admin_subscription", _external=True),
        )
        return redirect(portal.url, code=303)
    except stripe.error.StripeError as e:
        app.logger.error(f"Stripe billing portal error: {e}")
        flash("Could not open billing portal. Please try again.", "error")
        return redirect(url_for("admin_subscription"))

@app.route("/admin/subscription/cancel", methods=["POST"])
@admin_required
def admin_subscription_cancel():
    """User has acknowledged the 6-month retention policy. Send them to the
    Stripe billing portal to actually cancel; the webhook will then mark the
    store inactive and start the 180-day retention timer."""
    store = current_store()
    if not store_has_paid_plan(store) or not store.stripe_customer_id:
        flash("No active subscription to cancel.", "error")
        return redirect(url_for("admin_subscription"))
    try:
        portal = stripe.billing_portal.Session.create(
            customer=store.stripe_customer_id,
            return_url=url_for("admin_subscription", _external=True),
        )
        return redirect(portal.url, code=303)
    except stripe.error.StripeError as e:
        app.logger.error(f"Stripe billing portal error (cancel): {e}")
        flash("Could not open the cancellation page. Please try again.", "error")
        return redirect(url_for("admin_subscription"))

@app.route("/admin/subscription/addons/<addon_key>", methods=["POST"])
@admin_required
def admin_subscription_toggle_addon(addon_key):
    store = current_store()
    addon = ADDONS_CATALOG.get(addon_key)
    if not addon:
        flash("Unknown add-on.", "error")
        return redirect(url_for("admin_subscription"))
    if not store_has_paid_plan(store):
        flash("Add-ons require an active Basic or Pro subscription.", "error")
        return redirect(url_for("admin_subscription"))
    if addon.get("status") == "coming_soon":
        flash(f"{addon['name']} is coming soon — we'll let you know when it goes live.",
              "success")
        return redirect(url_for("admin_subscription"))
    # Future: real activation flow (Stripe subscription item update, etc.)
    flash("Add-on updated.", "success")
    return redirect(url_for("admin_subscription"))

# ── Dashboard ────────────────────────────────────────────────
@app.route("/dashboard")
@login_required
def dashboard():
    user=current_user(); store=current_store(); today=date.today()
    month_start=date(today.year,today.month,1)
    if user.role=="superadmin":
        stores=Store.query.order_by(Store.created_at.desc()).all()
        return render_template("dashboard_superadmin.html",user=user,stores=stores,today=today)
    sid=store.id
    if user.role=="admin":
        total_transfers=Transfer.query.filter_by(store_id=sid).count()
        today_transfers=Transfer.query.filter_by(store_id=sid,send_date=today).count()
        pending_ach=ACHBatch.query.filter_by(store_id=sid,reconciled=False).count()
        recent_transfers=Transfer.query.filter_by(store_id=sid).order_by(Transfer.created_at.desc()).limit(8).all()
        recent_batches=ACHBatch.query.filter_by(store_id=sid).order_by(ACHBatch.ach_date.desc()).limit(5).all()
        company_stats={}
        for co in ["Intermex","Maxi","Barri"]:
            rows=Transfer.query.filter(Transfer.store_id==sid,Transfer.company==co,
                Transfer.send_date>=month_start,Transfer.status.notin_(["Canceled","Rejected"])).all()
            company_stats[co]={"count":len(rows),"total":sum(r.send_amount for r in rows),"fees":sum(r.fee for r in rows)}
        today_report=DailyReport.query.filter_by(store_id=sid,report_date=today).first()
        month_report=MonthlyFinancial.query.filter_by(store_id=sid,year=today.year,month=today.month).first()
        cfg=get_sfin_cfg(sid)
        bank_data,bank_error=simplefin_fetch(sid) if (cfg and cfg.access_url) else (None,None)
        return render_template("dashboard_admin.html",user=user,store=store,today=today,
            total_transfers=total_transfers,today_transfers=today_transfers,
            pending_ach=pending_ach,recent_transfers=recent_transfers,recent_batches=recent_batches,
            company_stats=company_stats,today_report=today_report,month_report=month_report,
            bank_data=bank_data,bank_error=bank_error,cfg=cfg)
    else:
        my_today=Transfer.query.filter_by(store_id=sid,created_by=user.id,send_date=today).order_by(Transfer.created_at.desc()).all()
        my_total=Transfer.query.filter_by(store_id=sid,created_by=user.id).count()
        my_month=Transfer.query.filter(Transfer.store_id==sid,Transfer.created_by==user.id,Transfer.send_date>=month_start).count()
        return render_template("dashboard_employee.html",user=user,store=store,today=today,
            my_today=my_today,my_total=my_total,my_month=my_month)

# ── Transfers ────────────────────────────────────────────────
@app.route("/transfers")
@login_required
def transfers():
    user=current_user(); sid=session.get("store_id")
    if not sid:
        flash("Select a store first.","error"); return redirect(url_for("dashboard"))
    q=Transfer.query.filter_by(store_id=sid)
    if user.role=="employee": q=q.filter_by(created_by=user.id)
    company=request.args.get("company",""); status=request.args.get("status","")
    date_from=request.args.get("date_from",""); date_to=request.args.get("date_to","")
    if company: q=q.filter_by(company=company)
    if status:  q=q.filter_by(status=status)
    if date_from:
        try: q=q.filter(Transfer.send_date>=datetime.strptime(date_from,"%Y-%m-%d").date())
        except: pass
    if date_to:
        try: q=q.filter(Transfer.send_date<=datetime.strptime(date_to,"%Y-%m-%d").date())
        except: pass
    rows=q.order_by(Transfer.send_date.desc(),Transfer.created_at.desc()).all()
    return render_template("transfers.html",user=user,transfers=rows,
        company=company,status=status,date_from=date_from,date_to=date_to)

@app.route("/transfers/new",methods=["GET","POST"])
@login_required
def new_transfer():
    user=current_user(); sid=session.get("store_id")
    if not sid:
        flash("Select a store first.","error"); return redirect(url_for("dashboard"))
    if request.method=="POST":
        t=Transfer(store_id=sid,created_by=user.id,
            send_date=datetime.strptime(request.form["send_date"],"%Y-%m-%d").date(),
            company=request.form["company"],sender_name=request.form["sender_name"],
            send_amount=float(request.form.get("send_amount") or 0),
            fee=float(request.form.get("fee") or 0),
            commission=float(request.form.get("commission") or 0),
            recipient_name=request.form.get("recipient_name",""),
            country=request.form.get("country",""),
            recipient_phone=request.form.get("recipient_phone",""),
            confirm_number=request.form.get("confirm_number",""),
            status=request.form.get("status","Sent"),
            status_notes=request.form.get("status_notes",""),
            batch_id=request.form.get("batch_id",""),
            internal_notes=request.form.get("internal_notes",""))
        db.session.add(t); db.session.commit()
        flash("Transfer logged successfully.","success"); return redirect(url_for("transfers"))
    return render_template("transfer_form.html",user=user,transfer=None,today=date.today().isoformat())

@app.route("/transfers/<int:tid>/edit",methods=["GET","POST"])
@login_required
def edit_transfer(tid):
    """Edit a transfer. Employees can only edit their own; admins can edit any."""
    user=current_user(); sid=session.get("store_id")
    if not sid:
        flash("Select a store first.","error"); return redirect(url_for("dashboard"))
    t=Transfer.query.filter_by(id=tid,store_id=sid).first_or_404()
    if user.role=="employee" and t.created_by!=user.id:
        flash("Access denied.","error"); return redirect(url_for("transfers"))
    if request.method=="POST":
        t.send_date=datetime.strptime(request.form["send_date"],"%Y-%m-%d").date()
        t.company=request.form["company"]; t.sender_name=request.form["sender_name"]
        t.send_amount=float(request.form.get("send_amount") or 0)
        t.fee=float(request.form.get("fee") or 0)
        t.commission=float(request.form.get("commission") or 0)
        t.recipient_name=request.form.get("recipient_name","")
        t.country=request.form.get("country","")
        t.recipient_phone=request.form.get("recipient_phone","")
        t.confirm_number=request.form.get("confirm_number","")
        t.status=request.form.get("status","Sent")
        t.status_notes=request.form.get("status_notes","")
        t.batch_id=request.form.get("batch_id","")
        t.internal_notes=request.form.get("internal_notes","")
        t.updated_at=datetime.utcnow()
        db.session.commit(); flash("Transfer updated.","success")
        return redirect(url_for("transfers"))
    return render_template("transfer_form.html",user=user,transfer=t,today=date.today().isoformat())

# ── Daily Book ───────────────────────────────────────────────
DAILY_COMPANIES=["Barri","Boost Rev.","Inter Cambio","Intermex","Maxi Transfer","Sigue","Vigo"]

@app.route("/daily")
@admin_required
def daily_list():
    user=current_user(); sid=session["store_id"]; today=date.today()
    month=int(request.args.get("month",today.month)); year=int(request.args.get("year",today.year))
    days_in_month=monthrange(year,month)[1]
    reports={r.report_date.day:r for r in DailyReport.query.filter(
        DailyReport.store_id==sid,
        db.extract("year",DailyReport.report_date)==year,
        db.extract("month",DailyReport.report_date)==month).all()}
    month_report=MonthlyFinancial.query.filter_by(store_id=sid,year=year,month=month).first()
    prev_month=month-1 if month>1 else 12; prev_year=year if month>1 else year-1
    next_month=month+1 if month<12 else 1; next_year=year if month<12 else year+1
    return render_template("daily_list.html",user=user,year=year,month=month,
        days=days_in_month,reports=reports,month_report=month_report,today=today,
        month_name=calendar.month_name[month],
        prev_month=prev_month,prev_year=prev_year,next_month=next_month,next_year=next_year)

@app.route("/daily/<string:ds>",methods=["GET","POST"])
@admin_required
def daily_report(ds):
    user=current_user(); sid=session["store_id"]
    try: report_date=datetime.strptime(ds,"%Y-%m-%d").date()
    except: flash("Invalid date.","error"); return redirect(url_for("daily_list"))
    report=DailyReport.query.filter_by(store_id=sid,report_date=report_date).first()
    mt_rows={r.company:r for r in MoneyTransferSummary.query.filter_by(store_id=sid,report_date=report_date).all()}
    auto_mt={}
    for co in ["Intermex","Maxi","Barri"]:
        rows=Transfer.query.filter(Transfer.store_id==sid,Transfer.company==co,
            Transfer.send_date==report_date,Transfer.status.notin_(["Canceled","Rejected"])).all()
        auto_mt[co]={"amount":sum(r.send_amount for r in rows),"fees":sum(r.fee for r in rows),
                     "commission":sum(r.commission for r in rows),"count":len(rows)}
    if request.method=="POST":
        if not report: report=DailyReport(store_id=sid,report_date=report_date); db.session.add(report)
        def fv(k): return float(request.form.get(k) or 0)
        for field in ["taxable_sales","non_taxable","sales_tax","bill_payment_charge","phone_recargas",
            "boost_mobile","money_transfer","money_order","check_cashing_fees","return_check_hold_fees",
            "return_check_paid_back","forward_balance","from_bank","other_cash_in","rebates_commissions",
            "cash_purchases","cash_expense","check_purchases","check_expense","outside_cash_drops",
            "cash_deposit","checks_deposit","safe_balance","payroll_expense","other_cash_out","over_short"]:
            setattr(report,field,fv(field))
        report.notes=request.form.get("notes",""); report.updated_at=datetime.utcnow()
        for co in DAILY_COMPANIES:
            key=co.lower().replace(" ","_").replace(".","")
            ex=mt_rows.get(co) or MoneyTransferSummary(store_id=sid,report_date=report_date,company=co)
            ex.amount=fv(f"mt_amount_{key}"); ex.fees=fv(f"mt_fees_{key}")
            ex.commission=fv(f"mt_commission_{key}"); db.session.add(ex)
        db.session.commit()
        flash(f"Daily report for {report_date.strftime('%B %d, %Y')} saved.","success")
        return redirect(url_for("daily_list",month=report_date.month,year=report_date.year))
    return render_template("daily_report.html",user=user,report_date=report_date,
        report=report,mt_rows=mt_rows,companies=DAILY_COMPANIES,auto_mt=auto_mt)

# ── Monthly P&L ──────────────────────────────────────────────
@app.route("/monthly")
@admin_required
def monthly_list():
    user=current_user(); sid=session["store_id"]
    reports=MonthlyFinancial.query.filter_by(store_id=sid).order_by(
        MonthlyFinancial.year.desc(),MonthlyFinancial.month.desc()).all()
    return render_template("monthly_list.html",user=user,reports=reports,today=date.today())

@app.route("/monthly/<int:year>/<int:month>",methods=["GET","POST"])
@admin_required
def monthly_report(year,month):
    user=current_user(); sid=session["store_id"]
    report=MonthlyFinancial.query.filter_by(store_id=sid,year=year,month=month).first()
    month_start=date(year,month,1); month_end=date(year,month,monthrange(year,month)[1])
    daily_rows=DailyReport.query.filter(DailyReport.store_id==sid,
        DailyReport.report_date>=month_start,DailyReport.report_date<=month_end).all()
    auto={"taxable_sales":sum(r.taxable_sales for r in daily_rows),
          "non_taxable":sum(r.non_taxable for r in daily_rows),
          "bill_payment_charge":sum(r.bill_payment_charge for r in daily_rows),
          "phone_recargas":sum(r.phone_recargas for r in daily_rows),
          "boost_mobile":sum(r.boost_mobile for r in daily_rows),
          "check_cashing_fees":sum(r.check_cashing_fees for r in daily_rows),
          "return_check_hold_fees":sum(r.return_check_hold_fees for r in daily_rows),
          "rebates_commissions":sum(r.rebates_commissions for r in daily_rows),
          "cash_purchases":sum(r.cash_purchases for r in daily_rows),
          "check_purchases":sum(r.check_purchases for r in daily_rows),
          "cash_expenses":sum(r.cash_expense for r in daily_rows),
          "check_expenses":sum(r.check_expense for r in daily_rows),
          "cash_payroll":sum(r.payroll_expense for r in daily_rows),
          "over_short":sum(r.over_short for r in daily_rows)}
    if request.method=="POST":
        if not report: report=MonthlyFinancial(store_id=sid,year=year,month=month); db.session.add(report)
        def fv(k): return float(request.form.get(k) or 0)
        for f in ["taxable_sales","non_taxable","bill_payment_charge","phone_recargas","boost_mobile",
            "check_cashing_fees","return_check_hold_fees","rebates_commissions","mt_commission_in_bank",
            "other_income_1","other_income_2","other_income_3","cash_purchases","check_purchases",
            "cash_expenses","check_expenses","cash_payroll","bank_charges_210","bank_charges_230",
            "credit_card_fees","money_order_rent","emaginenet_tech","irs_payroll_tax","texas_workforce",
            "other_taxes","accounting_charges","return_check_gl","other_expense_1","other_expense_2",
            "other_expense_3","other_expense_4","other_expense_5","over_short",
            "borrowed_money_return","profit_distributed","cash_carry_forward"]:
            setattr(report,f,fv(f))
        report.notes=request.form.get("notes",""); report.updated_at=datetime.utcnow()
        db.session.commit(); flash(f"P&L for {calendar.month_name[month]} {year} saved.","success")
        return redirect(url_for("monthly_list"))
    return render_template("monthly_report.html",user=user,year=year,month=month,
        month_name=calendar.month_name[month],report=report,auto=auto)

@app.route("/monthly/new")
@admin_required
def monthly_new():
    today=date.today(); return redirect(url_for("monthly_report",year=today.year,month=today.month))

# ── ACH Batches ──────────────────────────────────────────────
@app.route("/batches")
@admin_required
def batches():
    user=current_user(); sid=session["store_id"]
    rows=ACHBatch.query.filter_by(store_id=sid).order_by(ACHBatch.ach_date.desc()).all()
    return render_template("batches.html",user=user,batches=rows)

@app.route("/batches/new",methods=["GET","POST"])
@admin_required
def new_batch():
    user=current_user(); sid=session["store_id"]
    if request.method=="POST":
        b=ACHBatch(store_id=sid,
            ach_date=datetime.strptime(request.form["ach_date"],"%Y-%m-%d").date(),
            company=request.form["company"],batch_ref=request.form["batch_ref"],
            ach_amount=float(request.form.get("ach_amount") or 0),
            transfer_dates=request.form.get("transfer_dates",""),
            status=request.form.get("status","Pending"),
            reconciled=request.form.get("reconciled")=="on",
            notes=request.form.get("notes",""))
        db.session.add(b); db.session.commit()
        flash("ACH batch logged.","success"); return redirect(url_for("batches"))
    return render_template("batch_form.html",user=user,batch=None,today=date.today().isoformat())

@app.route("/batches/<int:bid>/edit",methods=["GET","POST"])
@admin_required
def edit_batch(bid):
    user=current_user(); sid=session["store_id"]
    b=ACHBatch.query.filter_by(id=bid,store_id=sid).first_or_404()
    if request.method=="POST":
        b.ach_date=datetime.strptime(request.form["ach_date"],"%Y-%m-%d").date()
        b.company=request.form["company"]; b.batch_ref=request.form["batch_ref"]
        b.ach_amount=float(request.form.get("ach_amount") or 0)
        b.transfer_dates=request.form.get("transfer_dates","")
        b.status=request.form.get("status","Pending")
        b.reconciled=request.form.get("reconciled")=="on"
        b.notes=request.form.get("notes","")
        db.session.commit(); flash("Batch updated.","success"); return redirect(url_for("batches"))
    return render_template("batch_form.html",user=user,batch=b,today=date.today().isoformat())

@app.route("/batches/<int:bid>/transfers")
@admin_required
def batch_transfers(bid):
    user=current_user(); sid=session["store_id"]
    b=ACHBatch.query.filter_by(id=bid,store_id=sid).first_or_404()
    rows=Transfer.query.filter_by(store_id=sid,batch_id=b.batch_ref).all()
    return render_template("batch_detail.html",user=user,batch=b,transfers=rows)

# ── Bank / SimpleFIN ─────────────────────────────────────────
@app.route("/bank")
@admin_required
def bank():
    user=current_user(); sid=session["store_id"]
    cfg=get_sfin_cfg(sid)
    bank_data,bank_error=simplefin_fetch(sid) if (cfg and cfg.access_url) else (None,None)
    return render_template("bank.html",user=user,bank_data=bank_data,bank_error=bank_error,cfg=cfg)

@app.route("/bank/setup",methods=["POST"])
@admin_required
def bank_setup():
    sid=session["store_id"]
    token=request.form.get("token","").strip()
    if not token: flash("Please paste your SimpleFIN token or access URL.","error"); return redirect(url_for("bank"))
    ok,message=simplefin_claim_token(token,sid)
    flash(message,"success" if ok else "error")
    return redirect(url_for("bank"))

@app.route("/bank/disconnect",methods=["POST"])
@admin_required
def bank_disconnect():
    cfg=get_sfin_cfg(session["store_id"])
    if cfg: cfg.access_url=""; db.session.commit()
    flash("SimpleFIN disconnected.","success"); return redirect(url_for("bank"))

@app.route("/api/bank/refresh")
@admin_required
def bank_refresh():
    data,error=simplefin_fetch(session["store_id"])
    if error: return jsonify({"error":error}),400
    return jsonify(data)

# ── Admin Users ──────────────────────────────────────────────
@app.route("/admin/users")
@admin_required
def admin_users():
    user=current_user(); sid=session["store_id"]
    users=User.query.filter_by(store_id=sid).all()
    return render_template("admin_users.html",user=user,users=users)

@app.route("/admin/users/new",methods=["GET","POST"])
@admin_required
def admin_new_user():
    user=current_user(); sid=session["store_id"]
    if request.method=="POST":
        un=request.form.get("username","").strip()
        if User.query.filter_by(store_id=sid,username=un).first():
            flash("Username already exists.","error")
        else:
            u=User(store_id=sid,username=un,full_name=request.form.get("full_name",""),
                   role=request.form.get("role","employee"))
            u.set_password(request.form["password"]); db.session.add(u); db.session.commit()
            flash(f"User '{u.username}' created.","success"); return redirect(url_for("admin_users"))
    return render_template("admin_user_form.html",user=user,edit_user=None)

@app.route("/admin/users/<int:uid>/edit",methods=["GET","POST"])
@admin_required
def admin_edit_user(uid):
    user=current_user(); sid=session["store_id"]
    eu=User.query.filter_by(id=uid,store_id=sid).first_or_404()
    if request.method=="POST":
        eu.full_name=request.form.get("full_name",""); eu.role=request.form.get("role","employee")
        eu.is_active=request.form.get("is_active")=="on"
        if request.form.get("password"): eu.set_password(request.form["password"])
        db.session.commit(); flash("User updated.","success"); return redirect(url_for("admin_users"))
    return render_template("admin_user_form.html",user=user,edit_user=eu)

@app.route("/admin/settings", methods=["GET", "POST"])
@admin_required
def admin_settings():
    """Tabbed admin settings (store info / security / team / owner access).

    The active tab comes from ?tab=… on GET and from the hidden _tab field on
    POST. Each tab handles its own validation and stays put on errors.
    """
    user = current_user()
    store = current_store()
    active_tab = request.args.get("tab", "store")
    errors = {}

    if request.method == "POST":
        form_tab = request.form.get("_tab", "store")
        active_tab = form_tab

        if form_tab == "store":
            name = request.form.get("store_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            phone = request.form.get("phone", "").strip()

            if not name:
                errors["store_name"] = "Store name is required."
            if not email:
                errors["email"] = "Email is required."
            elif not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                errors["email"] = "Enter a valid email address."
            if not errors:
                taken = User.query.filter(
                    User.username == email,
                    User.role == "admin",
                    User.store_id != store.id
                ).first()
                if taken:
                    errors["email"] = "That email is already registered to another account."

            if not errors:
                store.name = name
                store.email = email
                store.phone = phone
                user.username = email
                db.session.commit()
                flash("Store info updated.", "success")
                return redirect(url_for("admin_settings", tab="store"))

        elif form_tab == "security":
            current_pw = request.form.get("current_password", "")
            new_pw = request.form.get("new_password", "")
            confirm_pw = request.form.get("confirm_password", "")

            if not user.check_password(current_pw):
                errors["current_password"] = "Current password is incorrect."
            elif len(new_pw) < 8:
                errors["new_password"] = "Password must be at least 8 characters."
            elif new_pw != confirm_pw:
                errors["confirm_password"] = "Passwords do not match."

            if not errors:
                user.set_password(new_pw)
                db.session.commit()
                flash("Password updated.", "success")
                return redirect(url_for("admin_settings", tab="security"))

    employees = User.query.filter(
        User.store_id == store.id,
        User.id != user.id
    ).order_by(User.full_name).all()

    now = datetime.utcnow()
    owner_invite = OwnerInviteCode.query.filter(
        OwnerInviteCode.store_id == store.id,
        OwnerInviteCode.used_at.is_(None),
        OwnerInviteCode.expires_at > now
    ).order_by(OwnerInviteCode.created_at.desc()).first()

    owner_link = StoreOwnerLink.query.filter_by(store_id=store.id).first()
    owner_user = db.session.get(User, owner_link.owner_id) if owner_link else None

    return render_template("admin_settings.html",
        user=user, store=store,
        active_tab=active_tab, errors=errors,
        employees=employees,
        owner_invite=owner_invite,
        owner_link=owner_link,
        owner_user=owner_user,
    )


@app.route("/admin/settings/team/<int:uid>", methods=["POST"])
@admin_required
def admin_reset_employee_password(uid):
    sid = session["store_id"]
    emp = User.query.filter_by(id=uid, store_id=sid).first_or_404()
    pw = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")
    if len(pw) < 8:
        flash("Password must be at least 8 characters.", "error")
    elif pw != confirm:
        flash("Passwords do not match.", "error")
    else:
        emp.set_password(pw)
        db.session.commit()
        flash(f"Password updated for {emp.full_name or emp.username}.", "success")
    return redirect(url_for("admin_settings", tab="team"))


@app.route("/admin/settings/owner/generate-code", methods=["POST"])
@admin_required
def admin_generate_owner_code():
    """Mint a fresh 7-day invite code; expires any previous unused codes first."""
    store = current_store()
    now = datetime.utcnow()
    OwnerInviteCode.query.filter(
        OwnerInviteCode.store_id == store.id,
        OwnerInviteCode.used_at.is_(None),
        OwnerInviteCode.expires_at > now
    ).update({"expires_at": now})
    db.session.flush()
    alphabet = string.ascii_uppercase + string.digits
    code = None
    for _ in range(10):
        candidate = "".join(secrets.choice(alphabet) for _ in range(8))
        if not OwnerInviteCode.query.filter_by(code=candidate).first():
            code = candidate
            break
    if code is None:
        flash("Could not generate a unique code. Please try again.", "error")
        return redirect(url_for("admin_settings", tab="owner"))
    invite = OwnerInviteCode(
        store_id=store.id,
        code=code,
        created_by=current_user().id,
        expires_at=now + timedelta(days=7),
    )
    db.session.add(invite)
    db.session.commit()
    flash("Invite code generated.", "success")
    return redirect(url_for("admin_settings", tab="owner"))


@app.route("/admin/settings/owner/remove-access", methods=["POST"])
@admin_required
def admin_remove_owner_access():
    store = current_store()
    owner_id = request.form.get("owner_id", type=int)
    if not owner_id:
        flash("Invalid request.", "error")
        return redirect(url_for("admin_settings", tab="owner"))
    StoreOwnerLink.query.filter_by(store_id=store.id, owner_id=owner_id).delete()
    db.session.commit()
    flash("Owner access removed.", "success")
    return redirect(url_for("admin_settings", tab="owner"))


# ── Superadmin ───────────────────────────────────────────────
@app.route("/superadmin/stores")
@superadmin_required
def superadmin_stores():
    user=current_user(); stores=Store.query.order_by(Store.created_at.desc()).all()
    return render_template("superadmin_stores.html",user=user,stores=stores)

@app.route("/superadmin/stores/new",methods=["GET","POST"])
@superadmin_required
def superadmin_new_store():
    user=current_user()
    if request.method=="POST":
        slug=request.form.get("slug","").strip().lower().replace(" ","-")
        if Store.query.filter_by(slug=slug).first():
            flash("Slug already taken.","error")
        else:
            s=Store(name=request.form["name"],slug=slug,email=request.form.get("email",""),
                phone=request.form.get("phone",""),address=request.form.get("address",""),
                plan=request.form.get("plan","trial"))
            db.session.add(s); db.session.flush()
            a=User(store_id=s.id,username=request.form.get("admin_username","admin"),
                full_name=request.form.get("admin_name","Store Admin"),role="admin")
            a.set_password(request.form.get("admin_password","changeme123!"))
            db.session.add(a); db.session.commit()
            flash(f"Store '{s.name}' created.","success"); return redirect(url_for("superadmin_stores"))
    return render_template("superadmin_store_form.html",user=user,store=None)

@app.route("/superadmin/impersonate/<int:store_id>")
@superadmin_required
def superadmin_impersonate(store_id):
    """Swap the current session into the target store's admin user.

    Used by the superadmin to debug a customer's view. The action is written
    to the audit log so impersonations stay traceable.
    """
    store=Store.query.get_or_404(store_id)
    admin=User.query.filter_by(store_id=store_id,role="admin").first()
    if not admin: flash("No admin for this store.","error"); return redirect(url_for("superadmin_stores"))
    record_audit("impersonate", target_type="store", target_id=store.id,
                 details=f"as {admin.username}")
    session["user_id"]=admin.id; session["role"]=admin.role; session["store_id"]=store_id
    db.session.commit()
    flash(f"Viewing as {store.name}","success"); return redirect(url_for("dashboard"))

# ── Superadmin control panel ─────────────────────────────────
STORES_PER_PAGE = 20

@app.route("/superadmin/controls")
@superadmin_required
def superadmin_controls():
    """Tabbed superadmin hub: overview, stores, discounts, feature flags, audit, announcements."""
    user = current_user()
    active_tab = request.args.get("tab", "overview")

    # Aggregate metrics — cheap, compute once for the overview + sidebar snapshot.
    plan_counts = dict(db.session.query(Store.plan, db.func.count(Store.id))
                       .group_by(Store.plan).all())
    basic_count    = plan_counts.get("basic", 0)
    pro_count      = plan_counts.get("pro", 0)
    trial_count    = plan_counts.get("trial", 0)
    inactive_count = plan_counts.get("inactive", 0)
    total_stores   = Store.query.count()

    retention_queue = Store.query.filter(
        Store.plan == "inactive",
        Store.data_retention_until.isnot(None),
    ).count()

    # Rough MRR — basic $20, pro $30. Real invoices live in Stripe.
    estimated_mrr = basic_count * 20 + pro_count * 30

    # Stripe health only hit on the overview tab (API call costs one round trip).
    stripe_health = stripe_health_check() if active_tab == "overview" else None

    # ── Stores tab: search, filters, pagination ──
    q_text        = request.args.get("q", "").strip()
    plan_filter   = request.args.get("plan", "").strip()
    status_filter = request.args.get("status", "").strip()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    stores_q = Store.query
    if q_text:
        like = f"%{q_text}%"
        stores_q = stores_q.filter(db.or_(
            Store.name.ilike(like),
            Store.slug.ilike(like),
            Store.email.ilike(like),
        ))
    if plan_filter in ("trial", "basic", "pro", "inactive"):
        stores_q = stores_q.filter(Store.plan == plan_filter)
    if status_filter == "active":
        stores_q = stores_q.filter(Store.is_active.is_(True))
    elif status_filter == "disabled":
        stores_q = stores_q.filter(Store.is_active.is_(False))

    stores_matching = stores_q.count()
    total_pages = max(1, (stores_matching + STORES_PER_PAGE - 1) // STORES_PER_PAGE)
    page = min(page, total_pages)
    stores = (stores_q.order_by(Store.created_at.desc())
              .offset((page - 1) * STORES_PER_PAGE)
              .limit(STORES_PER_PAGE).all())

    discounts = DiscountCode.query.order_by(DiscountCode.created_at.desc()).all()
    flags = FeatureFlag.query.order_by(FeatureFlag.key).all()
    # Feature-flag overrides are keyed by (store_id, flag_key); fetch only for visible stores.
    visible_ids = [s.id for s in stores]
    override_rows = (StoreFeatureOverride.query.filter(StoreFeatureOverride.store_id.in_(visible_ids)).all()
                     if visible_ids else [])
    overrides = {(o.store_id, o.flag_key): o.enabled for o in override_rows}
    audit = (SuperadminAuditLog.query
             .order_by(SuperadminAuditLog.created_at.desc())
             .limit(100).all())
    announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()

    return render_template("superadmin_controls.html",
        user=user, active_tab=active_tab,
        stores=stores, discounts=discounts, flags=flags,
        overrides=overrides, audit=audit, announcements=announcements,
        basic_count=basic_count, pro_count=pro_count,
        trial_count=trial_count, inactive_count=inactive_count,
        retention_queue=retention_queue, estimated_mrr=estimated_mrr,
        total_stores=total_stores,
        stripe_health=stripe_health,
        # Pagination + filter state for the Stores tab.
        q=q_text, plan_filter=plan_filter, status_filter=status_filter,
        page=page, total_pages=total_pages, stores_matching=stores_matching,
        stores_per_page=STORES_PER_PAGE,
    )

# ── Per-store actions (superadmin) ───────────────────────────
def _store_or_404(store_id): return Store.query.get_or_404(store_id)

@app.route("/superadmin/stores/<int:store_id>/extend-trial", methods=["POST"])
@superadmin_required
def superadmin_extend_trial(store_id):
    """Push the store's trial/grace deadlines forward by N days (default 7)."""
    store = _store_or_404(store_id)
    days = max(1, min(int(request.form.get("days", 7) or 7), 180))
    now = datetime.utcnow()
    base = store.trial_ends_at if (store.trial_ends_at and store.trial_ends_at > now) else now
    store.trial_ends_at = base + timedelta(days=days)
    store.grace_ends_at = store.trial_ends_at + timedelta(days=4)
    if store.plan == "inactive":
        store.plan = "trial"
        store.data_retention_until = None
        store.canceled_at = None
    record_audit("extend_trial", target_type="store", target_id=store.id,
                 details=f"+{days}d → {store.trial_ends_at.isoformat()}")
    db.session.commit()
    flash(f"{store.name}: trial extended by {days} days.", "success")
    return redirect(url_for("superadmin_controls", tab="stores"))

@app.route("/superadmin/stores/<int:store_id>/comp-plan", methods=["POST"])
@superadmin_required
def superadmin_comp_plan(store_id):
    """Grant a free plan (basic or pro) bypassing Stripe. For friends/family/comps."""
    store = _store_or_404(store_id)
    plan = request.form.get("plan", "pro")
    if plan not in ("basic", "pro"):
        flash("Invalid plan.", "error"); return redirect(url_for("superadmin_controls", tab="stores"))
    store.plan = plan
    store.canceled_at = None
    store.data_retention_until = None
    record_audit("comp_plan", target_type="store", target_id=store.id,
                 details=f"granted {plan} (no Stripe)")
    db.session.commit()
    flash(f"{store.name}: comped to {plan.title()}.", "success")
    return redirect(url_for("superadmin_controls", tab="stores"))

@app.route("/superadmin/stores/<int:store_id>/toggle-active", methods=["POST"])
@superadmin_required
def superadmin_toggle_active(store_id):
    """Enable/disable the store account without touching billing state."""
    store = _store_or_404(store_id)
    store.is_active = not store.is_active
    record_audit("toggle_active", target_type="store", target_id=store.id,
                 details=f"is_active={store.is_active}")
    db.session.commit()
    flash(f"{store.name}: {'active' if store.is_active else 'disabled'}.", "success")
    return redirect(url_for("superadmin_controls", tab="stores"))

@app.route("/superadmin/stores/<int:store_id>/extend-retention", methods=["POST"])
@superadmin_required
def superadmin_extend_retention(store_id):
    """Push the 6-month data purge deadline out by N days (default 30)."""
    store = _store_or_404(store_id)
    days = max(1, min(int(request.form.get("days", 30) or 30), 720))
    base = store.data_retention_until if store.data_retention_until else datetime.utcnow()
    store.data_retention_until = base + timedelta(days=days)
    record_audit("extend_retention", target_type="store", target_id=store.id,
                 details=f"+{days}d → {store.data_retention_until.isoformat()}")
    db.session.commit()
    flash(f"{store.name}: retention extended by {days} days.", "success")
    return redirect(url_for("superadmin_controls", tab="stores"))

@app.route("/superadmin/stores/<int:store_id>/revert-to-trial", methods=["POST"])
@superadmin_required
def superadmin_revert_to_trial(store_id):
    """Drop a paid/comped store back onto the 7-day trial. Keeps all data."""
    store = _store_or_404(store_id)
    now = datetime.utcnow()
    store.plan = "trial"
    store.trial_ends_at = now + timedelta(days=7)
    store.grace_ends_at = now + timedelta(days=11)
    store.canceled_at = None
    store.data_retention_until = None
    record_audit("revert_to_trial", target_type="store", target_id=store.id)
    db.session.commit()
    flash(f"{store.name}: reverted to 7-day trial.", "success")
    return redirect(url_for("superadmin_controls", tab="stores"))

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

@app.route("/superadmin/discounts/new", methods=["POST"])
@superadmin_required
def superadmin_new_discount():
    """Create a discount code; sync to Stripe if the key is configured."""
    code = request.form.get("code", "").strip().upper()
    if not code or not re.match(r"^[A-Z0-9_-]{3,40}$", code):
        flash("Code must be 3–40 chars (A-Z, 0-9, _, -).", "error")
        return redirect(url_for("superadmin_controls", tab="discounts"))
    if DiscountCode.query.filter_by(code=code).first():
        flash("That code already exists.", "error")
        return redirect(url_for("superadmin_controls", tab="discounts"))
    kind = request.form.get("kind", "percent")
    percent = int(request.form.get("percent_off") or 0) if kind == "percent" else 0
    amount_cents = int(float(request.form.get("amount_off") or 0) * 100) if kind == "amount" else 0
    if kind == "percent" and not (1 <= percent <= 100):
        flash("Percent off must be 1–100.", "error")
        return redirect(url_for("superadmin_controls", tab="discounts"))
    if kind == "amount" and amount_cents <= 0:
        flash("Amount off must be greater than zero.", "error")
        return redirect(url_for("superadmin_controls", tab="discounts"))
    duration = request.form.get("duration", "once")
    duration_months = int(request.form.get("duration_months") or 0) if duration == "repeating" else None
    max_redemptions = int(request.form.get("max_redemptions") or 0) or None
    expires_days = int(request.form.get("expires_days") or 0)
    expires_at = datetime.utcnow() + timedelta(days=expires_days) if expires_days else None

    dc = DiscountCode(
        code=code, label=request.form.get("label", "").strip(),
        percent_off=percent or None, amount_off_cents=amount_cents or None,
        duration=duration, duration_in_months=duration_months,
        max_redemptions=max_redemptions, expires_at=expires_at,
        created_by=current_user().id,
    )
    db.session.add(dc); db.session.flush()
    if stripe.api_key:
        _sync_discount_to_stripe(dc)
    record_audit("create_discount", target_type="discount", target_id=dc.id,
                 details=f"{dc.code} {dc.value_label}")
    db.session.commit()
    flash(f"Discount code {code} created.", "success")
    return redirect(url_for("superadmin_controls", tab="discounts"))

@app.route("/superadmin/discounts/<int:dc_id>/toggle", methods=["POST"])
@superadmin_required
def superadmin_toggle_discount(dc_id):
    """Activate/deactivate a discount code locally and in Stripe."""
    dc = DiscountCode.query.get_or_404(dc_id)
    dc.is_active = not dc.is_active
    if dc.stripe_promotion_code_id:
        try:
            stripe.PromotionCode.modify(dc.stripe_promotion_code_id, active=dc.is_active)
        except Exception as e:
            app.logger.warning(f"Stripe promo toggle failed: {e}")
    record_audit("toggle_discount", target_type="discount", target_id=dc.id,
                 details=f"active={dc.is_active}")
    db.session.commit()
    flash(f"{dc.code}: {'active' if dc.is_active else 'disabled'}.", "success")
    return redirect(url_for("superadmin_controls", tab="discounts"))

# ── Feature flags (superadmin) ───────────────────────────────
@app.route("/superadmin/features/new", methods=["POST"])
@superadmin_required
def superadmin_new_feature():
    """Declare a new feature flag. Key must be a short lowercase identifier."""
    key = request.form.get("key", "").strip().lower()
    if not re.match(r"^[a-z][a-z0-9_]{1,40}$", key):
        flash("Flag key must be lowercase letters/numbers/underscore, 2–41 chars.", "error")
        return redirect(url_for("superadmin_controls", tab="features"))
    if FeatureFlag.query.filter_by(key=key).first():
        flash("That flag already exists.", "error")
        return redirect(url_for("superadmin_controls", tab="features"))
    flag = FeatureFlag(
        key=key,
        label=request.form.get("label", "").strip() or key,
        description=request.form.get("description", "").strip(),
        enabled_by_default=request.form.get("enabled_by_default") == "on",
    )
    db.session.add(flag)
    record_audit("create_feature", target_type="feature", target_id=key)
    db.session.commit()
    flash(f"Feature flag {key} created.", "success")
    return redirect(url_for("superadmin_controls", tab="features"))

@app.route("/superadmin/features/<string:key>/toggle-global", methods=["POST"])
@superadmin_required
def superadmin_toggle_feature_global(key):
    """Flip a feature's global default on/off."""
    flag = FeatureFlag.query.filter_by(key=key).first_or_404()
    flag.enabled_by_default = not flag.enabled_by_default
    record_audit("toggle_feature_global", target_type="feature", target_id=flag.key,
                 details=f"enabled_by_default={flag.enabled_by_default}")
    db.session.commit()
    flash(f"Flag {key} globally {'on' if flag.enabled_by_default else 'off'}.", "success")
    return redirect(url_for("superadmin_controls", tab="features"))

@app.route("/superadmin/features/<string:key>/stores/<int:store_id>", methods=["POST"])
@superadmin_required
def superadmin_set_feature_override(key, store_id):
    """Set or clear a per-store override for a feature flag.

    Form values: action = 'on' | 'off' | 'clear'.
    """
    FeatureFlag.query.filter_by(key=key).first_or_404()
    _store_or_404(store_id)
    action = request.form.get("action", "on")
    existing = StoreFeatureOverride.query.filter_by(store_id=store_id, flag_key=key).first()
    if action == "clear":
        if existing: db.session.delete(existing)
    else:
        enabled = action == "on"
        if existing:
            existing.enabled = enabled
            existing.updated_at = datetime.utcnow()
            existing.updated_by = current_user().id
        else:
            db.session.add(StoreFeatureOverride(
                store_id=store_id, flag_key=key, enabled=enabled,
                updated_by=current_user().id,
            ))
    record_audit("set_feature_override", target_type="feature", target_id=key,
                 details=f"store={store_id} action={action}")
    db.session.commit()
    flash("Override updated.", "success")
    return redirect(url_for("superadmin_controls", tab="features"))

# ── Announcements (superadmin) ───────────────────────────────
@app.route("/superadmin/announcements/new", methods=["POST"])
@superadmin_required
def superadmin_new_announcement():
    """Post a banner shown to every user on every page until it expires."""
    message = request.form.get("message", "").strip()
    if not message:
        flash("Announcement message is required.", "error")
        return redirect(url_for("superadmin_controls", tab="announcements"))
    level = request.form.get("level", "info")
    if level not in ("info", "warning", "error", "success"):
        level = "info"
    try:
        days = int(request.form.get("expires_days") or 0)
    except ValueError:
        days = 0
    expires_at = datetime.utcnow() + timedelta(days=days) if days else None
    a = Announcement(
        message=message[:2000], level=level,
        is_active=True, expires_at=expires_at,
        created_by=current_user().id,
    )
    db.session.add(a); db.session.flush()
    record_audit("create_announcement", target_type="announcement", target_id=a.id,
                 details=f"{level}: {message[:80]}")
    db.session.commit()
    flash("Announcement posted.", "success")
    return redirect(url_for("superadmin_controls", tab="announcements"))

@app.route("/superadmin/announcements/<int:ann_id>/toggle", methods=["POST"])
@superadmin_required
def superadmin_toggle_announcement(ann_id):
    """Enable or disable a posted announcement without deleting it."""
    a = db.session.get(Announcement, ann_id) or abort(404)
    a.is_active = not a.is_active
    record_audit("toggle_announcement", target_type="announcement", target_id=a.id,
                 details=f"active={a.is_active}")
    db.session.commit()
    flash(f"Announcement {'enabled' if a.is_active else 'disabled'}.", "success")
    return redirect(url_for("superadmin_controls", tab="announcements"))

@app.route("/superadmin/announcements/<int:ann_id>/delete", methods=["POST"])
@superadmin_required
def superadmin_delete_announcement(ann_id):
    """Permanently remove an announcement. Toggle first if you might want it back."""
    a = db.session.get(Announcement, ann_id) or abort(404)
    record_audit("delete_announcement", target_type="announcement", target_id=a.id)
    db.session.delete(a); db.session.commit()
    flash("Announcement deleted.", "success")
    return redirect(url_for("superadmin_controls", tab="announcements"))

# ── Audit log CSV export ─────────────────────────────────────
@app.route("/superadmin/controls/audit.csv")
@superadmin_required
def superadmin_audit_export():
    """Stream the full audit log as CSV for spreadsheet review."""
    import csv, io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["timestamp_utc", "admin_id", "admin_name", "action", "target_type", "target_id", "details"])
    rows = SuperadminAuditLog.query.order_by(SuperadminAuditLog.created_at.desc()).all()
    for r in rows:
        w.writerow([
            r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
            r.admin_id or "", r.admin_name or "",
            r.action or "", r.target_type or "", r.target_id or "",
            (r.details or "").replace("\n", " "),
        ])
    record_audit("export_audit_csv", target_type="audit", details=f"rows={len(rows)}")
    db.session.commit()
    filename = f"audit-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.csv"
    return buf.getvalue(), 200, {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": f'attachment; filename="{filename}"',
    }

# ── Stripe webhook ───────────────────────────────────────────
@app.route("/webhooks/stripe", methods=["POST"])
def stripe_webhook():
    """Stripe webhook receiver.

    Handled events:
      checkout.session.completed   — flip the store onto the new plan, store
                                     Stripe IDs, clear any retention timer.
      customer.subscription.deleted — mark the store inactive and start the
                                     6-month data retention countdown.
    Other event types are accepted (200 OK) but ignored.
    """
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature", "")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        return jsonify({"error": "Invalid signature"}), 400

    if event["type"] == "checkout.session.completed":
        obj = event["data"]["object"]
        store_id = obj.get("metadata", {}).get("store_id")
        if store_id:
            store = db.session.get(Store, int(store_id))
            if store:
                sub_id = obj.get("subscription", "")
                customer_id = obj.get("customer", "")
                try:
                    sub = stripe.Subscription.retrieve(sub_id)
                    price_id = sub["items"]["data"][0]["price"]["id"]
                    basic_pid = os.environ.get("STRIPE_BASIC_PRICE_ID", "")
                    store.plan = "basic" if price_id == basic_pid else "pro"
                except Exception as e:
                    app.logger.error(f"Stripe sub retrieve error: {e}")
                    store.plan = "pro"
                store.stripe_customer_id = customer_id
                store.stripe_subscription_id = sub_id
                # Returning customer: clear cancellation + retention timer.
                store.canceled_at = None
                store.data_retention_until = None
                db.session.commit()

    elif event["type"] == "customer.subscription.deleted":
        sub_id = event["data"]["object"].get("id", "")
        store = Store.query.filter_by(stripe_subscription_id=sub_id).first()
        if store:
            now = datetime.utcnow()
            store.plan = "inactive"
            store.stripe_subscription_id = ""
            store.canceled_at = now
            store.data_retention_until = now + timedelta(days=DATA_RETENTION_DAYS)
            db.session.commit()

    return jsonify({"received": True}), 200

# ── Data retention purge ─────────────────────────────────────
# Models that hold per-store data and must be wiped before the store row.
_STORE_OWNED_MODELS = [
    "Transfer", "ACHBatch", "DailyReport", "MoneyTransferSummary",
    "MonthlyFinancial", "SimpleFINConfig", "StoreOwnerLink",
    "OwnerInviteCode", "User",
]

def purge_expired_stores():
    """Hard-delete inactive stores whose retention window has elapsed."""
    now = datetime.utcnow()
    expired = Store.query.filter(
        Store.plan == "inactive",
        Store.data_retention_until.isnot(None),
        Store.data_retention_until <= now,
    ).all()
    purged = 0
    for s in expired:
        for model_name in _STORE_OWNED_MODELS:
            model = globals().get(model_name)
            if model is not None:
                model.query.filter_by(store_id=s.id).delete(synchronize_session=False)
        db.session.delete(s)
        purged += 1
    if purged:
        db.session.commit()
    return purged

@app.cli.command("purge-expired-stores")
def purge_expired_stores_cmd():
    """Delete inactive stores past their retention deadline. Run daily."""
    n = purge_expired_stores()
    print(f"Purged {n} expired store(s).")

# ── Error handlers ───────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return render_template("error.html",user=current_user(),code=404,message="Page not found."),404

@app.errorhandler(500)
def server_error(e):
    import traceback
    app.logger.error(f"500 error: {e}\n{traceback.format_exc()}")
    try:
        u = current_user()
    except Exception:
        u = None
    return render_template("error.html", user=u, code=500,
        message="Something went wrong. Please try again."), 500

# ── Init ─────────────────────────────────────────────────────
_STORE_ADDED_COLUMNS = [
    ("addons",               "VARCHAR(255) DEFAULT ''"),
    ("canceled_at",          "TIMESTAMP NULL"),
    ("data_retention_until", "TIMESTAMP NULL"),
]

def _ensure_subscription_columns():
    """Add new store columns on existing databases. No-op if they exist."""
    try:
        with db.engine.connect() as conn:
            dialect = db.engine.dialect.name
            if dialect == "sqlite":
                cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(store);")]
                for name, ddl in _STORE_ADDED_COLUMNS:
                    if name not in cols:
                        conn.exec_driver_sql(f"ALTER TABLE store ADD COLUMN {name} {ddl}")
            else:
                for name, ddl in _STORE_ADDED_COLUMNS:
                    conn.exec_driver_sql(
                        f"ALTER TABLE store ADD COLUMN IF NOT EXISTS {name} {ddl}"
                    )
                conn.commit()
    except Exception as e:
        app.logger.warning(f"subscription column migration skipped: {e}")

# Feature flags seeded on first boot. Each entry is (key, label, description, enabled).
# Declaring them here means a fresh install has a real starting set for the UI.
_DEFAULT_FEATURE_FLAGS = [
    ("addon_tv_display", "Add-on: TV Display & Rates",
     "Show the TV Display add-on in the subscription page.", True),
    ("bank_sync", "Bank sync (SimpleFIN)",
     "Enable the Pro-tier SimpleFIN bank connection for stores.", True),
    ("multi_store_owner", "Multi-store owner portal",
     "Allow store admins to generate owner invite codes.", True),
]

def _seed_feature_flags():
    for key, label, description, enabled in _DEFAULT_FEATURE_FLAGS:
        if not FeatureFlag.query.filter_by(key=key).first():
            db.session.add(FeatureFlag(
                key=key, label=label, description=description,
                enabled_by_default=enabled,
            ))
    db.session.commit()

def init_db():
    with app.app_context():
        db.create_all()
        _ensure_subscription_columns()
        _seed_feature_flags()
        if not User.query.filter_by(username="superadmin",store_id=None).first():
            sa=User(username="superadmin",full_name="Platform Owner",role="superadmin",store_id=None)
            sa.set_password(os.environ.get("SUPERADMIN_PASSWORD","super2025!")); db.session.add(sa); db.session.commit()
            print("✅ Superadmin: superadmin / super2025!")
        if not Store.query.first():
            s=Store(name="Cambio Express Lamar",slug="cambio-express-lamar",plan="pro"); db.session.add(s); db.session.flush()
            a=User(store_id=s.id,username="admin",full_name="Store Admin",role="admin")
            a.set_password(os.environ.get("ADMIN_PASSWORD","cambio2025!")); db.session.add(a); db.session.commit()
            print("✅ Demo store admin: admin / cambio2025!")

init_db()

if __name__=="__main__":
    port=int(os.environ.get("PORT",5000))
    print(f"🚀 DineroBook → http://0.0.0.0:{port}")
    app.run(host="0.0.0.0",port=port,debug=False)
