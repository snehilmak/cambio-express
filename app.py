from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, abort, send_from_directory, make_response, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
from functools import wraps
from calendar import monthrange
import requests, base64, os, calendar, logging, re, secrets, string, hashlib, hmac, smtplib, json
from email.message import EmailMessage
import stripe
import click
import pyotp
import qrcode
import qrcode.image.svg
import io
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
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dinerobook-dev-secret-change-in-prod")

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

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///dinerobook.db")
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
    # Billing cadence for paid plans. "" for trial / inactive; "monthly"
    # or "yearly" for basic / pro. Set from the Stripe price_id in the
    # checkout webhook. Lets the superadmin overview split paid counts
    # by cycle and compute a precise MRR.
    billing_cycle = db.Column(db.String(10), default="")
    stripe_customer_id     = db.Column(db.String(60), default="")
    stripe_subscription_id = db.Column(db.String(60), default="")
    # Phase 2 bank-transaction sync rate-limit. Each Transaction.list
    # call costs per-account; we cap manual syncs at MAX_BANK_SYNCS_PER_DAY
    # and require BANK_SYNC_COOLDOWN_MINUTES between them.
    bank_sync_last_at      = db.Column(db.DateTime, nullable=True)
    bank_sync_count_today  = db.Column(db.Integer, default=0)
    bank_sync_count_date   = db.Column(db.Date, nullable=True)
    is_active     = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    trial_ends_at = db.Column(db.DateTime, nullable=True)
    grace_ends_at = db.Column(db.DateTime, nullable=True)
    addons        = db.Column(db.String(255), default="")
    canceled_at           = db.Column(db.DateTime, nullable=True)
    data_retention_until  = db.Column(db.DateTime, nullable=True)
    # Trial-reminder dedup. send_trial_reminders() stamps this the
    # first time it sends; cleared on checkout.session.completed so a
    # second trial (post-reactivation) gets its own fresh reminder.
    trial_reminder_sent_at = db.Column(db.DateTime, nullable=True)
    # Comma-separated list of money-transfer companies this store works
    # with. Empty string falls through to DEFAULT_MT_COMPANIES. Resolve
    # via store_mt_companies(store) — never read this column directly.
    companies     = db.Column(db.String(500), default="")
    # Federal tax rate (decimal — 0.01 = 1%) applied to every transfer at
    # save time. The transfer form treats Federal Tax as read-only and the
    # server always recomputes from send_amount × this rate, so employees
    # can't tamper with it. Admins override via Settings → Store if their
    # state or vendor has a different rate.
    federal_tax_rate = db.Column(db.Float, default=0.01, nullable=False)
    # Referral: the ReferralCode this store used when signing up (if any).
    # Set once at signup from ?ref=<code>, never mutated afterwards. We
    # use this on the first paid conversion to apply credits to both
    # sides of the referral. `use_alter=True` breaks the Store↔ReferralCode
    # dependency cycle during create_all / drop_all — the table is created
    # without the FK first, then the FK is added via ALTER TABLE.
    referred_by_code_id = db.Column(db.Integer,
        db.ForeignKey("referral_code.id", use_alter=True,
                      name="fk_store_referred_by_code"),
        nullable=True)
    referee_credit_applied_at = db.Column(db.DateTime, nullable=True)

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
    # TOTP-based 2FA. Mandatory for superadmin (see _needs_totp_enroll /
    # _totp_is_enrolled); other roles ignore these columns today. The secret
    # is base32 and stored plaintext — the DB itself is the trust boundary.
    totp_secret      = db.Column(db.String(64), nullable=True)
    totp_enrolled_at = db.Column(db.DateTime, nullable=True)
    # Profile fields. email is freeform on save (we coerce-strip-lower);
    # validation lives in _update_user_profile.
    email            = db.Column(db.String(255), default="")
    phone            = db.Column(db.String(40), default="")
    timezone         = db.Column(db.String(60), default="")
    last_login_at    = db.Column(db.DateTime, nullable=True)
    # UI theme preference. Dark is the design-system default; users
    # who want light explicitly opt in via /account/profile. Stored
    # per-user (not per-device) so the preference follows the user
    # across browsers / devices. Logged-out pages always render dark.
    theme_preference = db.Column(db.String(8), default="dark")
    # Notification preferences. Opt-out (default True) for the one we
    # ship in v1 — a trial-ending reminder. Adding more toggles is one
    # column per channel here + the matching sender.
    notify_trial_reminders = db.Column(db.Boolean, default=True)
    # Announcement broadcast emails are higher-volume (every superadmin
    # announcement fans out to every opted-in user), so opt-in by default.
    notify_announcement_email = db.Column(db.Boolean, default=False)
    # Deliverability suppression — stamped when Resend reports a hard
    # bounce on this user's email. `_send_email()` skips suppressed
    # recipients.
    email_bounced_at    = db.Column(db.DateTime, nullable=True)
    __table_args__ = (db.UniqueConstraint("store_id","username"),)
    def set_password(self,pw): self.password_hash=generate_password_hash(pw)
    def check_password(self,pw): return check_password_hash(self.password_hash,pw)

class Customer(db.Model):
    """Per-store customer directory used to autofill returning-sender info.

    Unique within a store on (phone_country, phone_number) so the same
    person can be reached the same way twice. Soft fields (address, dob)
    are free to update on each visit — newest values win.
    """
    __tablename__ = "customer"
    id            = db.Column(db.Integer, primary_key=True)
    store_id      = db.Column(db.Integer, db.ForeignKey("store.id"), nullable=False)
    full_name     = db.Column(db.String(120), nullable=False)
    dob           = db.Column(db.Date, nullable=True)
    address       = db.Column(db.String(255), default="")
    phone_country = db.Column(db.String(8),  default="+1")
    phone_number  = db.Column(db.String(40), default="")
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at    = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("store_id", "phone_country", "phone_number",
                            name="uq_customer_store_phone"),
    )

    def to_dict(self, current_store_id=None, home_names=None):
        """JSON payload for the autocomplete.

        When `current_store_id` is passed and doesn't match this customer's
        home store, `home_store_name` is filled from `home_names`
        (id → name map) so the UI can label the row "from Store X".
        """
        d = {
            "id": self.id,
            "full_name": self.full_name,
            "dob": self.dob.isoformat() if self.dob else "",
            "address": self.address or "",
            "phone_country": self.phone_country or "",
            "phone_number": self.phone_number or "",
            "home_store_id": self.store_id,
            "home_store_name": "",
        }
        if current_store_id is not None and self.store_id != current_store_id:
            d["home_store_name"] = (home_names or {}).get(self.store_id, "")
        return d

class Transfer(db.Model):
    __tablename__ = "transfer"
    id             = db.Column(db.Integer, primary_key=True)
    store_id       = db.Column(db.Integer, db.ForeignKey("store.id"), nullable=False)
    created_by     = db.Column(db.Integer, db.ForeignKey("user.id"))
    # Linked to Customer for returning-customer autofill. Nullable so legacy
    # transfers stay valid.
    customer_id    = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=True)
    send_date      = db.Column(db.Date, nullable=False)
    company        = db.Column(db.String(30), nullable=False)
    # Service performed for the customer. Money Transfer is the historical
    # default — we still apply Store.federal_tax_rate to it. Bill Payment,
    # Top Up, and Recharge are non-remittance services that the cashier
    # also runs through the same companies, but the federal tax doesn't
    # apply (no ACH withdrawal that would carry it). Server-side tax math
    # in new_transfer / edit_transfer is the gate, not this column.
    service_type   = db.Column(db.String(30), default="Money Transfer", nullable=False)
    sender_name    = db.Column(db.String(120), nullable=False)
    send_amount    = db.Column(db.Float, nullable=False)
    fee            = db.Column(db.Float, default=0.0)
    # Federal tax (e.g. 1%) the customer pays on the send amount. Tracked
    # separately from `fee` because it leaves the store with the ACH
    # withdrawal — it's not store revenue.
    federal_tax    = db.Column(db.Float, default=0.0)
    commission     = db.Column(db.Float, default=0.0)
    recipient_name = db.Column(db.String(120), default="")
    country        = db.Column(db.String(60), default="")
    recipient_phone= db.Column(db.String(40), default="")
    # Sender snapshot: a copy of Customer fields at transfer time. The
    # canonical source of truth is the linked Customer row so updates flow
    # both ways — we mirror here so old transfers still display even after
    # a customer edits their info or the Customer row is deleted.
    sender_phone        = db.Column(db.String(40), default="")
    sender_phone_country= db.Column(db.String(8),  default="")
    sender_address      = db.Column(db.String(255), default="")
    sender_dob          = db.Column(db.Date, nullable=True)
    confirm_number = db.Column(db.String(60), default="")
    status         = db.Column(db.String(30), default="Sent")
    status_notes   = db.Column(db.String(255), default="")
    batch_id       = db.Column(db.String(60), default="")
    internal_notes = db.Column(db.String(255), default="")
    # Processed-by attribution (separate from the login user under `created_by`):
    # `employee_id` links to the store's named-employee roster for analytics;
    # `employee_name` is the string snapshot captured at save-time so historical
    # transfers display the correct name forever — even if the roster row is
    # later deactivated, renamed, or deleted.
    employee_id    = db.Column(db.Integer, db.ForeignKey("store_employee.id"), nullable=True)
    employee_name  = db.Column(db.String(120), default="")
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at     = db.Column(db.DateTime, default=datetime.utcnow)
    creator        = db.relationship("User", foreign_keys=[created_by])
    employee       = db.relationship("StoreEmployee", foreign_keys=[employee_id])
    @property
    def total_collected(self):
        """What the customer actually handed over: send amount + store fee + federal tax."""
        return (self.send_amount or 0) + (self.fee or 0) + (self.federal_tax or 0)

class StoreEmployee(db.Model):
    """Admin-managed list of employee NAMES per store — not login accounts.

    All in-store employees share a single login (the store's employee User
    account). This table holds the roster of real people whose names can be
    picked from the "Processed by" dropdown on the transfer form. Admins
    deactivate (never delete) entries so historical attribution survives.
    """
    __tablename__ = "store_employee"
    id         = db.Column(db.Integer, primary_key=True)
    store_id   = db.Column(db.Integer, db.ForeignKey("store.id"), nullable=False)
    name       = db.Column(db.String(120), nullable=False)
    is_active  = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class TransferAudit(db.Model):
    """Append-only log of everything that happens to a Transfer.

    Written on create, on edit (with a human-readable summary of which fields
    changed and their before→after values), and on status changes. Shown to
    admins on the transfer edit page so they can see exactly who touched a
    record and when. `user_id` is the logged-in User; `employee_name` is the
    roster name they credited the action to (snapshot string, not FK, so it
    stays valid after the roster row is deactivated).
    """
    __tablename__ = "transfer_audit"
    id             = db.Column(db.Integer, primary_key=True)
    store_id       = db.Column(db.Integer, db.ForeignKey("store.id"), nullable=False)
    transfer_id    = db.Column(db.Integer, db.ForeignKey("transfer.id"), nullable=False)
    user_id        = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    employee_id    = db.Column(db.Integer, db.ForeignKey("store_employee.id"), nullable=True)
    employee_name  = db.Column(db.String(120), default="")
    action         = db.Column(db.String(30), nullable=False)   # created | updated | status_changed
    summary        = db.Column(db.String(500), default="")
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    user           = db.relationship("User", foreign_keys=[user_id])

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
        """Sum of what the ACH actually debits: send amount + federal tax.
        The store fee stays with the store, so it's excluded from this total."""
        v = (db.session.query(
                db.func.coalesce(db.func.sum(Transfer.send_amount), 0.0)
              + db.func.coalesce(db.func.sum(Transfer.federal_tax), 0.0))
             .filter_by(store_id=self.store_id, batch_id=self.batch_ref)
             .scalar())
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
    # Lock state. When locked_at is not None every write to this report
    # (and its line items — drops, check deposits, DailyLineItem rows)
    # is rejected server-side. The user has to explicitly unlock before
    # editing again. locked_by is the admin who set the lock.
    locked_at             = db.Column(db.DateTime, nullable=True)
    locked_by             = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
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

class DailyDrop(db.Model):
    """Individual "Outside Cash & Drop" entry — logged as they happen by time
    and amount, then summed into DailyReport.outside_cash_drops.

    Mirrors the Drops section of the master spreadsheet: the main daily-book
    field becomes read-only, recomputed from these line items on every add /
    delete / daily-report save so the two always agree.
    """
    __tablename__ = "daily_drop"
    id          = db.Column(db.Integer, primary_key=True)
    store_id    = db.Column(db.Integer, db.ForeignKey("store.id"), nullable=False)
    report_date = db.Column(db.Date, nullable=False)
    drop_time   = db.Column(db.Time, nullable=False)
    amount      = db.Column(db.Float, nullable=False)
    note        = db.Column(db.String(120), default="")
    created_by  = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "time": self.drop_time.strftime("%H:%M") if self.drop_time else "",
            "amount": float(self.amount or 0),
            "note": self.note or "",
        }

class CheckDeposit(db.Model):
    """Individual check-deposit entry — logged as it happens by time and
    amount, then summed into DailyReport.checks_deposit.

    Same shape as DailyDrop: a store can record multiple check deposits
    across a single day (e.g. morning run + afternoon run), and the
    daily-book's Checks Deposit line becomes a read-only sum of these
    rows. The server recomputes from CheckDeposit on every add / delete
    / daily-report save so the two can never drift.
    """
    __tablename__ = "check_deposit"
    id           = db.Column(db.Integer, primary_key=True)
    store_id     = db.Column(db.Integer, db.ForeignKey("store.id"), nullable=False)
    report_date  = db.Column(db.Date, nullable=False)
    deposit_time = db.Column(db.Time, nullable=False)
    amount       = db.Column(db.Float, nullable=False)
    note         = db.Column(db.String(120), default="")
    created_by   = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "time": self.deposit_time.strftime("%H:%M") if self.deposit_time else "",
            "amount": float(self.amount or 0),
            "note": self.note or "",
        }

# Status values for ReturnCheck.status. Kept as module-level constants
# so the route handlers, P&L aggregator, and tests all reference the
# same vocabulary.
RETURN_CHECK_STATUSES = ("pending", "recovered", "loss", "fraud")
RETURN_CHECK_BOOKED   = ("recovered", "loss", "fraud")  # i.e. closed; affect P&L


class ReturnCheck(db.Model):
    """A bounced customer check — the workflow lives entirely on this
    row, not split across multiple events.

    Why this exists: cashiers used to track bounced checks in a
    separate Excel tab, manually carrying pending items forward each
    month and writing the eventual gain or loss into the monthly P&L's
    "Return Check (G/L)" line by hand. We model the exact same
    workflow here:

      bounced_on   the date the check came back from the bank. Never
                   moves once set; it's the historical fact.

      status       'pending'   — sitting on the books, owner is
                                  still trying to recover
                   'recovered' — fully or partially repaid; the gain
                                  is the recovered_amount
                   'loss'      — written off; the entire `amount` is
                                  the loss
                   'fraud'     — same accounting as 'loss', kept as a
                                  distinct status for reporting (repeat
                                  offender lists, fraud KPIs)

      status_changed_on
                   the date status moved out of `pending`. This is
                   what drives which month's P&L the gain/loss lands
                   on. A pending row never touches any month's P&L —
                   only marking it (recovered / loss / fraud) does.

      recovered_amount
                   only meaningful when status='recovered'. May be
                   less than `amount` (partial recovery); the
                   difference is the implicit shortfall the cashier
                   chose to accept. If they later mark the row 'loss'
                   instead, the FULL `amount` becomes the loss
                   (recovered_amount is reset).

    P&L formula for a given month (locked field on monthly_report):

        Σ recovered_amount where status='recovered'
                                AND status_changed_on in the month
      − Σ amount             where status in ('loss','fraud')
                                AND status_changed_on in the month

    Positive = net gain (recoveries beat write-offs); negative = net
    loss. Pending balance does NOT enter the P&L — it's a separate
    KPI on the list page and owner dashboard.
    """
    __tablename__ = "return_check"
    id              = db.Column(db.Integer, primary_key=True)
    store_id        = db.Column(db.Integer, db.ForeignKey("store.id"), nullable=False)
    bounced_on      = db.Column(db.Date, nullable=False)
    customer_name   = db.Column(db.String(120), nullable=False)
    check_number    = db.Column(db.String(40),  default="")
    payer_bank      = db.Column(db.String(120), default="")
    amount          = db.Column(db.Float,       nullable=False)
    status          = db.Column(db.String(16),  default="pending", nullable=False)
    status_changed_on = db.Column(db.Date,      nullable=True)
    notes           = db.Column(db.Text,        default="")
    created_by      = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at      = db.Column(db.DateTime, default=datetime.utcnow,
                                onupdate=datetime.utcnow)

    payments = db.relationship(
        "ReturnCheckPayment",
        backref="return_check",
        cascade="all, delete-orphan",
        order_by="ReturnCheckPayment.paid_on, ReturnCheckPayment.id",
    )

    @property
    def recovered_total(self):
        """Sum of all installment payments. Source of truth for
        'how much have we got back so far'."""
        return float(sum((p.amount or 0.0) for p in (self.payments or [])))

    @property
    def remaining(self):
        """Outstanding balance. When status='loss' / 'fraud' the
        write-off equals this value. Never goes negative because the
        payment endpoint caps each installment at remaining."""
        return max(0.0, float(self.amount or 0.0) - self.recovered_total)

    @property
    def days_outstanding(self):
        """Calendar days since the check bounced. Used for aging
        buckets on the list and owner dashboard. Closed rows freeze
        at the days-to-close so the value is meaningful for fraud /
        write-off reporting too."""
        end = self.status_changed_on if self.status != "pending" else date.today()
        if not self.bounced_on or not end:
            return 0
        return (end - self.bounced_on).days


class ReturnCheckPayment(db.Model):
    """One installment of repayment against a ReturnCheck.

    Splitting payments off into their own table is what lets the
    workflow handle the realistic case the user described: a customer
    bounces a $1,000 check, brings $300 in cash on April 15, $400 by
    Zelle on May 10, then the rest in June. Each row here represents
    one of those events, posts to its own day's daily book + P&L, and
    independently rolls up into the parent ReturnCheck's
    `recovered_total`.

    Auto-creates a matching `DailyLineItem(kind='return_payback')` on
    `paid_on` when inserted via the route handler — that's how the
    daily-book "Return Check Paid Back" line stays in sync without
    double-entry.
    """
    __tablename__ = "return_check_payment"
    id                 = db.Column(db.Integer, primary_key=True)
    return_check_id    = db.Column(db.Integer,
                                   db.ForeignKey("return_check.id"),
                                   nullable=False, index=True)
    amount             = db.Column(db.Float, nullable=False)
    paid_on            = db.Column(db.Date,  nullable=False)
    # cash / check / zelle / wire / money_order / other — see
    # _PAYMENT_METHODS for the canonical set. Free-form on save so a
    # future method can be added by widening the form's <select>
    # without a migration.
    payment_method     = db.Column(db.String(20), default="")
    note               = db.Column(db.String(200), default="")
    created_by         = db.Column(db.Integer, db.ForeignKey("user.id"),
                                   nullable=True)
    created_at         = db.Column(db.DateTime, default=datetime.utcnow)


class DailyLineItem(db.Model):
    """Generic time-amount-note line item that rolls up into a single
    DailyReport field, discriminated by `kind`.

    Covers the daily-book lines that a real store may log multiple
    times per day (e.g. cash purchases, cash expenses, check
    purchases, check expenses, return-check paybacks). Each kind maps
    to exactly one DailyReport field (see _LINE_ITEM_KINDS below), and
    the field becomes read-only — the server always re-derives the
    total from these rows on save so a stale form can't overwrite it.

    DailyDrop and CheckDeposit kept their bespoke tables from before
    this was introduced; they behave identically but predate the
    generic model.
    """
    __tablename__ = "daily_line_item"
    id          = db.Column(db.Integer, primary_key=True)
    store_id    = db.Column(db.Integer, db.ForeignKey("store.id"), nullable=False)
    report_date = db.Column(db.Date, nullable=False)
    # One of the keys in _LINE_ITEM_KINDS. Not a DB enum so new kinds
    # can be introduced with zero migration.
    kind        = db.Column(db.String(40), nullable=False, index=True)
    at_time     = db.Column(db.Time, nullable=False)
    amount      = db.Column(db.Float, nullable=False)
    note        = db.Column(db.String(120), default="")
    # When this line item was auto-created by marking a ReturnCheck as
    # recovered, this FK links back to the source ReturnCheck. Lets us
    # find + update + delete the shadow line item when the return
    # check is edited or reopened, instead of leaving stale rows
    # behind. NULL for line items the cashier added manually.
    return_check_id = db.Column(db.Integer, db.ForeignKey("return_check.id"),
                                nullable=True)
    created_by  = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "time": self.at_time.strftime("%H:%M") if self.at_time else "",
            "amount": float(self.amount or 0),
            "note": self.note or "",
        }

class MoneyTransferSummary(db.Model):
    __tablename__ = "mt_summary"
    id           = db.Column(db.Integer, primary_key=True)
    store_id     = db.Column(db.Integer, db.ForeignKey("store.id"), nullable=False)
    report_date  = db.Column(db.Date, nullable=False)
    company      = db.Column(db.String(40), nullable=False)
    amount       = db.Column(db.Float, default=0.0)
    fees         = db.Column(db.Float, default=0.0)
    commission   = db.Column(db.Float, default=0.0)
    # Federal tax collected from the customer on this company's transfers
    # for the day. Tracked separately from fees because tax leaves with
    # the ACH withdrawal, not store revenue.
    federal_tax  = db.Column(db.Float, default=0.0)
    __table_args__ = (db.UniqueConstraint("store_id","report_date","company"),)
    @property
    def individual_total(self):
        return (self.amount or 0) + (self.fees or 0) + (self.commission or 0) + (self.federal_tax or 0)

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
    # Single consolidated bank-charges line, fed by the bank-sync
    # registry. The 210/230 split above is preserved for historic
    # rows but no longer rendered separately on the P&L UI.
    bank_charges_total    = db.Column(db.Float, default=0.0)
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

class StripeBankAccount(db.Model):
    """A bank account connected via Stripe Financial Connections.

    One row per connected account (a store may link several). We cache just
    enough metadata to render the UI — the institution name, last4, account
    type, and the last-known balance + timestamp. Balances refresh on
    demand (user clicks Refresh, or we pull in Account.refresh on page load
    when stale). Credentials are never held here — Stripe is the custodian.
    """
    __tablename__ = "stripe_bank_account"
    id                   = db.Column(db.Integer, primary_key=True)
    store_id             = db.Column(db.Integer, db.ForeignKey("store.id"), nullable=False)
    stripe_account_id    = db.Column(db.String(60), unique=True, nullable=False)
    institution_name     = db.Column(db.String(120), default="")
    display_name         = db.Column(db.String(120), default="")
    last4                = db.Column(db.String(8), default="")
    category             = db.Column(db.String(30), default="")   # checking / savings / credit / other
    subcategory          = db.Column(db.String(30), default="")
    currency             = db.Column(db.String(8), default="usd")
    last_balance_cents   = db.Column(db.BigInteger, default=0)
    last_balance_as_of   = db.Column(db.DateTime, nullable=True)
    connected_at         = db.Column(db.DateTime, default=datetime.utcnow)
    disconnected_at      = db.Column(db.DateTime, nullable=True)
    enabled              = db.Column(db.Boolean, default=True)
    # Operator-set nickname. When non-empty the transactions list +
    # P&L breakdown show this instead of "••<last4>".
    nickname             = db.Column(db.String(60), default="")

    @property
    def label(self):
        """Display label: nickname when set, else ••last4, else 'Account'."""
        if self.nickname:
            return self.nickname
        if self.last4:
            return f"••{self.last4}"
        return "Account"

    @property
    def last_balance(self):
        return (self.last_balance_cents or 0) / 100.0

class BankTransaction(db.Model):
    """A transaction pulled from Stripe Financial Connections.

    Cached locally so we can render the daily list without re-hitting
    Stripe (each Transaction.list call is billed). Idempotent on
    `stripe_transaction_id` — re-syncing the same window safely no-ops
    rows we've already seen.

    The status field tracks Stripe's transaction lifecycle:
      pending  — visible but not yet posted to the bank ledger
      posted   — settled
      void     — reversed before posting

    `category_slug` is the daily-book line-item kind (one of
    _LINE_ITEM_KINDS) OR a non-posting tag from
    BANK_CATEGORIES_NON_POSTING. `matched_rule_id` is the BankRule that
    auto-categorized this row (null when set manually). When the
    category is a daily-book kind, `daily_line_item_id` links to the
    DailyLineItem we created — un-reconcile deletes it.
    """
    __tablename__ = "bank_transaction"
    id                       = db.Column(db.Integer, primary_key=True)
    store_id                 = db.Column(db.Integer, db.ForeignKey("store.id"), nullable=False)
    stripe_bank_account_id   = db.Column(db.Integer, db.ForeignKey("stripe_bank_account.id"), nullable=False)
    stripe_transaction_id    = db.Column(db.String(80), unique=True, nullable=False)
    amount_cents             = db.Column(db.BigInteger, nullable=False)  # signed: + credit, - debit
    currency                 = db.Column(db.String(8), default="usd")
    description              = db.Column(db.String(500), default="")
    posted_at                = db.Column(db.DateTime, nullable=True)
    status                   = db.Column(db.String(20), default="posted")
    category_slug            = db.Column(db.String(60), default="")
    matched_rule_id          = db.Column(db.Integer, nullable=True)
    daily_line_item_id       = db.Column(db.Integer,
                                          db.ForeignKey("daily_line_item.id"),
                                          nullable=True)
    created_at               = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.Index("ix_bank_transaction_store_posted",
                 "store_id", "posted_at"),
    )

    @property
    def amount(self):
        return (self.amount_cents or 0) / 100.0

class BankRule(db.Model):
    """Operator-managed rule that auto-categorizes BankTransactions on sync.

    All match conditions are independently optional — a rule may be as
    minimal as "description contains EmagineNet" or as specific as
    "description contains EmagineNet AND amount = $180.00 AND debit on
    account ••0210". Lower priority numbers match first; the first
    matching enabled rule wins and stops further evaluation.

    Manual categorization on a transaction (via the UI) sets
    matched_rule_id=NULL — the rule is only credited when sync auto-
    applies it. This lets us count true automations.
    """
    __tablename__ = "bank_rule"
    id                  = db.Column(db.Integer, primary_key=True)
    store_id            = db.Column(db.Integer, db.ForeignKey("store.id"),
                                    nullable=False, index=True)
    enabled             = db.Column(db.Boolean, default=True)
    priority            = db.Column(db.Integer, default=100)

    # All four conditions optional. desc_match_type "" means "skip
    # description match"; if non-empty, desc_match_value is required.
    desc_match_type     = db.Column(db.String(20), default="")  # "" | contains | starts_with | equals | regex
    desc_match_value    = db.Column(db.String(500), default="")
    sign_filter         = db.Column(db.String(10), default="")  # "" | credit | debit
    amount_min_cents    = db.Column(db.Integer, nullable=True)  # absolute cents; None = unbounded
    amount_max_cents    = db.Column(db.Integer, nullable=True)
    account_filter_id   = db.Column(db.Integer,
                                     db.ForeignKey("stripe_bank_account.id"),
                                     nullable=True)

    # Output: a daily-book line-item kind from _LINE_ITEM_KINDS, OR a
    # non-posting tag from BANK_CATEGORIES_NON_POSTING.
    target_kind         = db.Column(db.String(40), nullable=False)
    auto_post           = db.Column(db.Boolean, default=True)

    description         = db.Column(db.String(200), default="")  # operator note
    match_count         = db.Column(db.Integer, default=0)
    last_matched_at     = db.Column(db.DateTime, nullable=True)
    created_at          = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at          = db.Column(db.DateTime, default=datetime.utcnow,
                                     onupdate=datetime.utcnow)

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

class PasswordResetToken(db.Model):
    """Short-lived, one-time-use token for the self-service password reset flow.

    Storing only the sha256 hash of the token (never the raw value) means the
    DB alone isn't enough for an attacker to reset an account — they'd need
    to have intercepted the email too.
    """
    __tablename__ = "password_reset_token"
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    token_hash = db.Column(db.String(128), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at    = db.Column(db.DateTime, nullable=True)

class EmailEvent(db.Model):
    """A delivery-status event posted to us by Resend's webhook.

    One row per event — Resend sends one-per-recipient events even for
    multipart sends, so a single `_send_email()` call that goes to N
    addresses produces N email.delivered events (or .bounced, .complained,
    .opened, .clicked).

    `user_id` is best-effort — we match the recipient address against
    User.email at webhook time. It can be NULL for addresses we've
    removed (purged user) or never matched (superadmin test email to a
    personal address, for example).

    `payload` is the raw JSON Resend sent us, in case we want to mine it
    later for fields we didn't parse out (the provider adds fields over
    time). Size-bounded to 8KB to keep runaway events from ballooning
    the table.
    """
    __tablename__ = "email_event"
    id           = db.Column(db.Integer, primary_key=True)
    # Resend's provider-side message id. Same message_id will have multiple
    # events over its lifecycle (sent → delivered → opened → …).
    message_id   = db.Column(db.String(80), default="", index=True)
    # The normalized to-address (lowercased, trimmed) the event is about.
    to_addr      = db.Column(db.String(255), default="", index=True)
    user_id      = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    # "email.sent" | "email.delivered" | "email.bounced" | "email.complained"
    # | "email.opened" | "email.clicked" | "email.delivery_delayed"
    event_type   = db.Column(db.String(40), nullable=False, index=True)
    # For bounces: "hard" | "soft". Empty string for non-bounce events.
    bounce_type  = db.Column(db.String(16), default="")
    payload      = db.Column(db.Text, default="")
    created_at   = db.Column(db.DateTime, default=datetime.utcnow, index=True)

class RecoveryCode(db.Model):
    """One-time-use 2FA recovery code for a user.

    Shown in plaintext exactly once at enrollment time; only the sha256 hash
    is persisted. Consumed on use (used_at set) — a consumed code stays in
    the table so we can show the user how many remain. Regenerate via the
    account-security page wipes all rows for that user and mints a fresh
    batch.
    """
    __tablename__ = "recovery_code"
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    code_hash  = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    used_at    = db.Column(db.DateTime, nullable=True)
    __table_args__ = (db.UniqueConstraint("user_id", "code_hash",
                                          name="uq_recovery_user_code"),)

class Passkey(db.Model):
    """A WebAuthn credential (passkey) registered to a user.

    One user can have many passkeys (laptop Touch ID, phone, hardware key).
    credential_id is the unique identifier the browser presents at login;
    public_key is the CBOR-encoded COSE key we use to verify assertions.
    sign_count is the authenticator-reported counter — we accept
    equal-or-greater values and reject resets to protect against cloned
    authenticators. name is the user-supplied nickname shown in the UI.

    A passkey login is treated as MFA-sufficient for every role including
    superadmin — the credential is phishing-resistant and device-bound by
    construction, so requiring TOTP on top would be redundant friction
    without adding security.
    """
    __tablename__ = "passkey"
    id             = db.Column(db.Integer, primary_key=True)
    user_id        = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    # credential_id is up to 1023 bytes per spec; we store the raw bytes
    # so the server-side verifier doesn't have to re-decode on every use.
    credential_id  = db.Column(db.LargeBinary, unique=True, nullable=False)
    public_key     = db.Column(db.LargeBinary, nullable=False)
    sign_count     = db.Column(db.Integer, default=0, nullable=False)
    name           = db.Column(db.String(120), default="")
    aaguid         = db.Column(db.String(36), default="")
    transports     = db.Column(db.String(120), default="")
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    last_used_at   = db.Column(db.DateTime, nullable=True)

class ReferralCode(db.Model):
    """One code per store, minted the first time the store goes onto a
    paid plan. The owner shares this code; every time a new store signs
    up with it and then converts to paid:
      - the owner gets `reward_self_cents` credited to their Stripe customer balance
      - the referee gets `reward_referee_cents` credited to theirs
    Credits only apply on the referee's *paid* conversion, not at trial —
    keeps us from paying for signups that churn.
    """
    __tablename__ = "referral_code"
    id                    = db.Column(db.Integer, primary_key=True)
    code                  = db.Column(db.String(12), unique=True, nullable=False)
    owner_store_id        = db.Column(db.Integer, db.ForeignKey("store.id"),
                                      unique=True, nullable=False)
    reward_self_cents     = db.Column(db.Integer, default=10000)  # $100
    reward_referee_cents  = db.Column(db.Integer, default=5000)   # $50
    is_active             = db.Column(db.Boolean, default=True)
    redeemed_count        = db.Column(db.Integer, default=0)
    created_at            = db.Column(db.DateTime, default=datetime.utcnow)

class ReferralRedemption(db.Model):
    """One row per new store that signed up with a referral code.
    Flags track whether the Stripe customer-balance credit on each side
    has been applied — so a webhook retry can't double-credit.
    """
    __tablename__ = "referral_redemption"
    id                      = db.Column(db.Integer, primary_key=True)
    referral_code_id        = db.Column(db.Integer, db.ForeignKey("referral_code.id"), nullable=False)
    referee_store_id        = db.Column(db.Integer, db.ForeignKey("store.id"),
                                        unique=True, nullable=False)
    redeemed_at             = db.Column(db.DateTime, default=datetime.utcnow)
    self_credit_applied_at  = db.Column(db.DateTime, nullable=True)
    referee_credit_applied_at = db.Column(db.DateTime, nullable=True)
    stripe_self_txn_id      = db.Column(db.String(60), default="")
    stripe_referee_txn_id   = db.Column(db.String(60), default="")

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

# ── TV display add-on ────────────────────────────────────────
#
# Per the screenshot we're targeting, the display is a stack of
# country sections. Each section is a matrix where rows are payout
# banks ("Banco Industrial", "Coppel", …) and columns are the
# money-transfer companies the store offers ("Maxi", "Cibao", "Vigo",
# …). Each cell is the dollar rate that bank pays via that company.
#
# Modeled normalized across four tables so the admin can reorder /
# add / remove banks and MT companies without manual CSV editing
# on every save:
#
#   TVDisplay         per-store config + the public-facing token
#   TVDisplayCountry  one section on the board (Mexico, Guatemala…)
#   TVDisplayPayoutBank  one row inside a country
#   TVDisplayRate     the cell at (bank, mt_company)
#
# `mt_companies` lives on Country as a CSV string — adding /
# reordering MT-company columns is a frequent edit, and a column on
# the parent is simpler than a fifth join table for "ordering of
# columns within a country."

class TVDisplay(db.Model):
    """One row per store that owns the tv_display add-on. Created
    lazily on first visit to /admin/tv-display."""
    __tablename__ = "tv_display"
    id              = db.Column(db.Integer, primary_key=True)
    store_id        = db.Column(db.Integer, db.ForeignKey("store.id"),
                                 unique=True, nullable=False)
    # 32-char URL-safe random token. Anyone with the URL can view —
    # rotation is a one-click action on the admin page.
    public_token    = db.Column(db.String(48), unique=True, nullable=False)
    # Bilingual title bar. Defaults match the screenshot the pilot
    # store provided ("Cheapest Money Transfer / Mejor Tipo de Cambio").
    title           = db.Column(db.String(120), default="Cheapest Money Transfer")
    subtitle        = db.Column(db.String(120), default="Mejor Tipo de Cambio")
    # Display orientation: "landscape" / "portrait" / "auto" (auto =
    # respect the device's screen orientation). The TV-side CSS
    # adapts via media queries; this is the explicit override.
    orientation     = db.Column(db.String(16), default="auto")
    # Light / dark theme override for the BOARD. Independent of
    # admin theme_preference (the operator likes dark mode in their
    # office, the TV needs the high-contrast light board).
    theme           = db.Column(db.String(16), default="light")
    last_updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    # DEPRECATED — left in the schema only because CLAUDE.md
    # forbids dropping columns from a running DB. The pair-code
    # state lives in TVPendingPair now (TV-initiated flow). These
    # columns can be backfill-renamed in a follow-up deploy.
    pair_code             = db.Column(db.String(8), default="")
    pair_code_expires_at  = db.Column(db.DateTime, nullable=True)

class TVDisplayCountry(db.Model):
    """One section on the board (Mexico, Guatemala, …)."""
    __tablename__ = "tv_display_country"
    id            = db.Column(db.Integer, primary_key=True)
    display_id    = db.Column(db.Integer, db.ForeignKey("tv_display.id"),
                               nullable=False, index=True)
    country_code  = db.Column(db.String(4), default="")  # ISO-2 — drives the flag emoji
    country_name  = db.Column(db.String(80), nullable=False)
    sort_order    = db.Column(db.Integer, default=0)
    # CSV of MT-company column headers shown for this country. Order
    # matters (defines column order). Example: "Maxi,Cibao,Vigo".
    mt_companies  = db.Column(db.String(500), default="")

class TVDisplayPayoutBank(db.Model):
    """One row in a country's matrix — "Bancomer", "Banorte", etc."""
    __tablename__ = "tv_display_payout_bank"
    id          = db.Column(db.Integer, primary_key=True)
    country_id  = db.Column(db.Integer, db.ForeignKey("tv_display_country.id"),
                             nullable=False, index=True)
    bank_name   = db.Column(db.String(120), nullable=False)
    sort_order  = db.Column(db.Integer, default=0)

class TVDisplayRate(db.Model):
    """The cell value at (bank, mt_company). Sparse — a cell with no
    rate set is rendered as "—" on the board."""
    __tablename__ = "tv_display_rate"
    id          = db.Column(db.Integer, primary_key=True)
    bank_id     = db.Column(db.Integer, db.ForeignKey("tv_display_payout_bank.id"),
                             nullable=False, index=True)
    # The MT company column header — must match one of the strings
    # in the parent country's mt_companies CSV. Not FK'd because the
    # column list is a free-form list per country, not a global table.
    mt_company  = db.Column(db.String(80), nullable=False)
    rate        = db.Column(db.Float, nullable=False)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow,
                             onupdate=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("bank_id", "mt_company",
                                            name="uq_tvrate_bank_company"),)

class TVPairing(db.Model):
    """One row per paired companion-app device (Fire TV, Google TV).
    The redeem endpoint mints a device_token here and returns the
    per-device URL /tv/device/<device_token> — never the shared
    public_token, so the Fire TV app can't sideload its credential
    into other devices.

    Single-active-pairing per display: a fresh redeem revokes any
    prior unrevoked TVPairing for the same display. That enforces
    'one $5 subscription = one Fire TV at a time' without affecting
    legacy /tv/<public_token> tablet/Chromecast users.
    """
    __tablename__ = "tv_pairing"
    id            = db.Column(db.Integer, primary_key=True)
    display_id    = db.Column(db.Integer, db.ForeignKey("tv_display.id"),
                                nullable=False, index=True)
    # 32-byte URL-safe random; same generator as public_token.
    device_token  = db.Column(db.String(48), unique=True, nullable=False)
    # Free-form label the app may submit ("Fire TV — Counter 1").
    # Empty string until the operator names it from the admin UI.
    device_label  = db.Column(db.String(80), default="")
    paired_at     = db.Column(db.DateTime, default=datetime.utcnow)
    # Bumped on every successful /tv/device/<token> render so the
    # admin UI can show "last seen 2 min ago".
    last_seen_at  = db.Column(db.DateTime, default=datetime.utcnow)
    # Set when superseded by a new pairing or manually revoked. A row
    # with revoked_at IS NOT NULL serves 404 on its device URL.
    revoked_at    = db.Column(db.DateTime, nullable=True)

class TVPendingPair(db.Model):
    """Pending pair attempt — created when a Fire TV opens the app
    and asks for a code. Lives in this table until either:
      (a) An admin claims the code from /tv-display → we revoke any
          prior active TVPairing on their display and create a fresh
          TVPairing tied to this row's device_token. The Fire TV's
          poll then transitions to "claimed" and starts loading the
          rate board. claimed_at + claimed_pairing_id are set.
      (b) The 10-minute window elapses → /api/tv-pair/status returns
          "expired" and the Fire TV app calls /init for a new code.

    Why a separate table from TVPairing:
      - Pending rows don't yet have a display_id (the operator
        hasn't entered their account yet to claim the code).
        Keeping TVPairing.display_id NOT NULL avoids loose semantics
        and lets the existing render path stay simple.
      - The device_token in this row is REUSED on claim — copied
        into the new TVPairing — so the Fire TV app stores its
        token once at /init time and never sees a rotation.

    Single-claim is enforced by claimed_at + claimed_pairing_id +
    a uniqueness check at claim time; no two pending rows can
    redeem to a TVPairing.
    """
    __tablename__ = "tv_pending_pair"
    id            = db.Column(db.Integer, primary_key=True)
    # 6-char alphanumeric (same alphabet as PAIR_CODE_ALPHABET).
    # Indexed because /api/tv-pair/status does the lookup by code
    # via a join, and so does /tv-display/claim.
    code          = db.Column(db.String(8), unique=True, nullable=False, index=True)
    # Stable from /init through claim. The Fire TV stores this and
    # never receives a different one.
    device_token  = db.Column(db.String(48), unique=True, nullable=False, index=True)
    # Free-form label the app may submit ("Fire TV — Stick 4K Max"),
    # carried over to TVPairing.device_label on claim.
    device_label  = db.Column(db.String(80), default="")
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at    = db.Column(db.DateTime, nullable=False)
    # Set on successful admin claim. Once set, this row is "spent"
    # and the Fire TV polls find the resulting TVPairing instead.
    claimed_at         = db.Column(db.DateTime, nullable=True)
    claimed_pairing_id = db.Column(db.Integer,
                                     db.ForeignKey("tv_pairing.id"),
                                     nullable=True)

class TVCompanyCatalog(db.Model):
    """Curated MT companies (Intermex, Maxi, Barri, etc.) selectable
    from the column-header picker on the TV display country editor.

    Why a global catalog instead of free-text per store:
      - Two stores both type "Maxi" / "MaxiTransfer" / "Maxi Money"
        otherwise; cross-store fraud detection and chain-wide
        consistency need a canonical name.
      - Eventually each row carries a logo_url (Phase 2). Decoupling
        the slug (immutable identifier) from display_name (mutable
        label) means we can rename / re-logo without breaking
        existing references on TVDisplayCountry.mt_companies.

    is_active=False hides the entry from the picker without losing
    references — older country sections still resolve the slug to
    display_name for rendering.
    """
    __tablename__ = "tv_company_catalog"
    id           = db.Column(db.Integer, primary_key=True)
    # URL-safe lowercase identifier (e.g. "maxi", "intermex"). The
    # column header CSV on TVDisplayCountry.mt_companies stores
    # these slugs. Immutable after creation.
    slug         = db.Column(db.String(40), unique=True, nullable=False, index=True)
    # Human-friendly label rendered on the public board. Editable.
    display_name = db.Column(db.String(80), nullable=False)
    # Future: nominative-use logo (Phase 2 of the catalog rollout).
    # Defaults to empty so Phase 1 ships without legal/asset
    # acquisition blocking the picker UI.
    logo_url     = db.Column(db.String(255), default="")
    sort_order   = db.Column(db.Integer, default=0)
    is_active    = db.Column(db.Boolean, default=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

class TVBankCatalog(db.Model):
    """Curated payout banks (BBVA Bancomer, Banco Industrial, etc.)
    selectable from the row-name picker on the country editor. Same
    slug + display_name pattern as TVCompanyCatalog, plus a
    country_code so the editor's bank picker can scope to "banks
    for Mexico" vs "banks for Guatemala."
    """
    __tablename__ = "tv_bank_catalog"
    id           = db.Column(db.Integer, primary_key=True)
    slug         = db.Column(db.String(60), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(80), nullable=False)
    # ISO-2; country_code IS NOT a FK to anything (countries are
    # picked from a flat list). Indexed because the picker filters
    # by it on every editor render.
    country_code = db.Column(db.String(4), default="", index=True)
    logo_url     = db.Column(db.String(255), default="")
    sort_order   = db.Column(db.Integer, default=0)
    is_active    = db.Column(db.Boolean, default=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

class TVCatalogLogo(db.Model):
    """Logo image bytes for a catalog entry. Stored as a BLOB so the
    feature works on every deploy target (Render free tier wipes the
    filesystem on every redeploy; a persistent disk works but adds
    infra config we'd rather avoid).

    Lookup is by (catalog_type, slug) — single shared table for both
    TVCompanyCatalog and TVBankCatalog. Discriminator is "company" or
    "bank"; slug matches the parent catalog row.

    Served via GET /tv/logo/<type>/<slug> with a year-long
    Cache-Control. Templates bust the cache by appending
    ?v=<updated_at_unix> when they emit the URL — re-uploads
    invalidate downstream caches without an HTTP-level mechanism.

    Size + total bytes
    - Per file: capped at 200 KiB on upload (validated server-side).
    - Worst case: 46 catalog rows × 200 KB ≈ 9 MB. Negligible for
      Postgres; the BLOB column on SQLite handles it just as well.
    """
    __tablename__ = "tv_catalog_logo"
    id           = db.Column(db.Integer, primary_key=True)
    # "company" | "bank" — keep the values short, the URL embeds them.
    catalog_type = db.Column(db.String(8), nullable=False, index=True)
    # Matches TVCompanyCatalog.slug or TVBankCatalog.slug — NOT a
    # foreign key, since both parent tables have their own slug
    # constraints and we want the logo row to outlive a soft-delete.
    slug         = db.Column(db.String(60), nullable=False, index=True)
    # Whitelisted by the upload endpoint: image/png | image/jpeg |
    # image/webp | image/svg+xml. SVG is allowed because it's the
    # ideal asset for the public TV board (scales to any density).
    mime_type    = db.Column(db.String(40), nullable=False)
    blob         = db.Column(db.LargeBinary, nullable=False)
    file_size    = db.Column(db.Integer, default=0)
    updated_at   = db.Column(db.DateTime, default=datetime.utcnow,
                              onupdate=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint("catalog_type", "slug",
                              name="uq_tv_catalog_logo_type_slug"),
    )

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
    # Broadcast-email flags. `broadcast_requested` is set when the
    # superadmin ticks the "Also email all users" checkbox at create
    # time. `broadcast_sent_at` is stamped the first time
    # broadcast_announcement() actually sends; used to dedup if the
    # announcement is edited later or the sender is run manually.
    broadcast_requested  = db.Column(db.Boolean, default=False)
    broadcast_sent_at    = db.Column(db.DateTime, nullable=True)

class PushSubscription(db.Model):
    """Web Push endpoint for a user — one row per browser/device they
    opted in on. Deleted on unsubscribe or when the endpoint starts
    returning 404/410 from the push provider."""
    __tablename__ = "push_subscription"
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    endpoint   = db.Column(db.Text, nullable=False)
    p256dh     = db.Column(db.String(200), nullable=False)
    auth       = db.Column(db.String(80), nullable=False)
    user_agent = db.Column(db.String(255), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("user_id", "endpoint"),)

# ── Auth ─────────────────────────────────────────────────────
def current_user():  return db.session.get(User,  session["user_id"])  if "user_id"  in session else None
def current_store(): return db.session.get(Store, session["store_id"]) if session.get("store_id") else None

_TRIAL_EXEMPT = {"subscribe", "subscribe_checkout", "subscribe_success", "logout",
                 "owner_dashboard", "owner_locations", "owner_store_detail",
                 "owner_link_store", "owner_unlink_store",
                 "admin_subscription", "admin_subscription_billing_portal",
                 "admin_subscription_toggle_addon", "admin_subscription_cancel",
                 "account_theme"}

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
def _compute_mrr(basic_monthly, basic_yearly, pro_monthly, pro_yearly):
    """Return MRR components and total from subscriber counts.

    Yearly subscribers are amortised to /12. Prices: Basic $35/mo or
    $350/yr; Pro $45/mo or $420/yr.
    """
    bm = basic_monthly * 35
    by_ = round(basic_yearly * 350 / 12)
    pm = pro_monthly * 45
    py_ = round(pro_yearly * 420 / 12)
    return bm, by_, pm, py_, bm + by_ + pm + py_

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
        "secret_key":            bool(os.environ.get("STRIPE_SECRET_KEY")),
        "publishable_key":       bool(os.environ.get("STRIPE_PUBLISHABLE_KEY")),
        "webhook_secret":        bool(os.environ.get("STRIPE_WEBHOOK_SECRET")),
    }
    prices = _stripe_price_ids()
    env["basic_price_id"]        = bool(prices["basic"])
    env["basic_yearly_price_id"] = bool(prices["basic_yearly"])
    env["pro_price_id"]          = bool(prices["pro"])
    env["pro_yearly_price_id"]   = bool(prices["pro_yearly"])
    result = {"env": env, "ok": False, "error": "",
              "price_ok": {"basic": False, "basic_yearly": False,
                           "pro": False, "pro_yearly": False},
              # Per-price error string from the Stripe API. Lets the
              # superadmin overview show "No such price …" or "test/live
              # mismatch" without us having to guess at the cause.
              "price_errors": {"basic": "", "basic_yearly": "",
                               "pro": "", "pro_yearly": ""},
              "fc_ok": False, "fc_error": "",
              "key_pair_match": True}
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
    for plan, pid in prices.items():
        if not pid:
            continue
        try:
            stripe.Price.retrieve(pid)
            result["price_ok"][plan] = True
        except Exception as e:
            # Capture the message so the superadmin overview can show why
            # the price didn't validate (most often: the price was made
            # in live mode but the secret key is from test mode, or vice
            # versa). Truncate to keep the badge readable.
            msg = str(e)
            result["price_errors"][plan] = msg[:160]
    # Publishable / secret key pairing: pk_test_ must go with sk_test_
    # and pk_live_ with sk_live_. Mismatched keys make Stripe.js fail
    # silently in the browser ("No such session") which is hard to
    # diagnose without this hint.
    pk = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
    if pk:
        pk_mode = "live" if pk.startswith("pk_live_") else "test"
        result["key_pair_match"] = (pk_mode == result.get("mode", ""))
    # FC dry probe: try to create + immediately discard a Financial
    # Connections session. Confirms the secret key has FC enabled and
    # is paired correctly with the rest of the account.
    if env["secret_key"]:
        try:
            stripe.financial_connections.Session.create(
                account_holder={"type": "customer", "customer": "cus_test_invalid"},
                permissions=["balances"],
                filters={"countries": ["US"]},
            )
            # We don't actually expect this to succeed — the customer
            # is fake. We're testing whether the API is reachable and
            # the FC product is enabled on this account.
            result["fc_ok"] = True
        except stripe.error.InvalidRequestError as e:
            # "No such customer" is the expected branch here — it means
            # FC is enabled and our key is good; only the placeholder
            # customer was rejected. Anything else is a real problem.
            msg = str(e)
            if "No such customer" in msg or "resource_missing" in msg:
                result["fc_ok"] = True
            else:
                result["fc_error"] = msg[:160]
        except Exception as e:
            result["fc_error"] = f"{type(e).__name__}: {e}"[:160]
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


def _superadmin_dashboard_context():
    """Platform-wide BI metrics for the superadmin Dashboard.

    Returns the kwargs dict that dashboard_superadmin.html expects: KPI
    counters (with 30d deltas), 90-day signup trend split by direct vs
    referral, plan distribution, MRR breakdown, referral leaderboard,
    30-day transfer volume by company, and a merged activity feed.

    MRR math is delegated to `_compute_mrr` so both pages stay in sync.
    """
    now = datetime.utcnow()
    today_d = date.today()
    d30_ago = now - timedelta(days=30)
    d60_ago = now - timedelta(days=60)
    d90_ago = now - timedelta(days=90)

    plan_rows = db.session.query(
        Store.plan, Store.billing_cycle, db.func.count(Store.id)
    ).group_by(Store.plan, Store.billing_cycle).all()

    basic_monthly = basic_yearly = pro_monthly = pro_yearly = 0
    trial_count = inactive_count = 0
    for p, cycle, n in plan_rows:
        if p == "basic":
            if cycle == "yearly": basic_yearly += n
            else:                 basic_monthly += n
        elif p == "pro":
            if cycle == "yearly": pro_yearly += n
            else:                 pro_monthly += n
        elif p == "trial":
            trial_count += n
        elif p == "inactive":
            inactive_count += n

    basic_count = basic_monthly + basic_yearly
    pro_count   = pro_monthly + pro_yearly
    paid_count  = basic_count + pro_count
    total_stores = Store.query.count()
    active_count = Store.query.filter_by(is_active=True).count()

    (basic_monthly_mrr, basic_yearly_mrr,
     pro_monthly_mrr,   pro_yearly_mrr,
     estimated_mrr) = _compute_mrr(basic_monthly, basic_yearly, pro_monthly, pro_yearly)

    new_stores_30d = Store.query.filter(Store.created_at >= d30_ago).count()
    new_stores_prev30 = Store.query.filter(
        Store.created_at >= d60_ago, Store.created_at < d30_ago
    ).count()
    new_stores_delta = new_stores_30d - new_stores_prev30

    churn_30d = Store.query.filter(
        Store.canceled_at.isnot(None), Store.canceled_at >= d30_ago
    ).count()
    churn_prev30 = Store.query.filter(
        Store.canceled_at.isnot(None),
        Store.canceled_at >= d60_ago, Store.canceled_at < d30_ago
    ).count()
    churn_delta = churn_30d - churn_prev30

    # 90-day daily signup series, split by direct vs referral. SQLite's
    # date(col) returns an ISO string, Postgres' returns a date — normalize.
    signup_rows = db.session.query(
        db.func.date(Store.created_at).label("d"),
        db.func.sum(case((Store.referred_by_code_id.is_(None), 1), else_=0)).label("direct"),
        db.func.sum(case((Store.referred_by_code_id.isnot(None), 1), else_=0)).label("referral"),
    ).filter(Store.created_at >= d90_ago).group_by("d").all()

    by_day = {}
    for d_val, direct, referral in signup_rows:
        key = d_val.isoformat() if hasattr(d_val, "isoformat") else str(d_val)
        by_day[key] = (int(direct or 0), int(referral or 0))

    signup_labels, signup_direct, signup_referral = [], [], []
    for i in range(89, -1, -1):
        d = today_d - timedelta(days=i)
        key = d.isoformat()
        direct, referral = by_day.get(key, (0, 0))
        signup_labels.append(key)
        signup_direct.append(direct)
        signup_referral.append(referral)

    plan_dist = [
        {"label": "Trial",    "count": trial_count},
        {"label": "Basic",    "count": basic_count},
        {"label": "Pro",      "count": pro_count},
        {"label": "Inactive", "count": inactive_count},
    ]

    top_referrers_raw = (
        db.session.query(ReferralCode, Store)
        .join(Store, ReferralCode.owner_store_id == Store.id)
        .filter(ReferralCode.redeemed_count > 0)
        .order_by(ReferralCode.redeemed_count.desc())
        .limit(5).all()
    )
    top_referrers = [
        {
            "store_name": s.name,
            "slug": s.slug,
            "code": rc.code,
            "redeemed": rc.redeemed_count,
            "reward_total_cents": rc.redeemed_count * rc.reward_self_cents,
        }
        for rc, s in top_referrers_raw
    ]
    referral_signups = Store.query.filter(Store.referred_by_code_id.isnot(None)).count()
    direct_signups = total_stores - referral_signups

    volume_rows = (
        db.session.query(
            Transfer.company,
            db.func.count(Transfer.id),
            db.func.coalesce(db.func.sum(Transfer.send_amount), 0.0),
        )
        .filter(Transfer.created_at >= d30_ago,
                Transfer.status.notin_(["Canceled", "Rejected"]))
        .group_by(Transfer.company)
        .order_by(db.func.coalesce(db.func.sum(Transfer.send_amount), 0.0).desc())
        .limit(6).all()
    )
    volume_by_company = [
        {"company": co or "—", "count": int(cnt), "total": float(tot or 0)}
        for co, cnt, tot in volume_rows
    ]
    total_volume_30d = sum(v["total"] for v in volume_by_company)
    total_transfers_30d = sum(v["count"] for v in volume_by_company)

    recent_signups = Store.query.order_by(Store.created_at.desc()).limit(10).all()
    recent_cancels = (Store.query
        .filter(Store.canceled_at.isnot(None))
        .order_by(Store.canceled_at.desc()).limit(10).all())
    activity = []
    for s in recent_signups:
        activity.append({
            "when": s.created_at,
            "kind": "signup",
            "store_name": s.name,
            "detail": "via referral" if s.referred_by_code_id else "direct signup",
            "plan": s.plan,
        })
    for s in recent_cancels:
        activity.append({
            "when": s.canceled_at,
            "kind": "cancel",
            "store_name": s.name,
            "detail": "canceled subscription",
            "plan": s.plan,
        })
    activity.sort(key=lambda a: a["when"] or datetime.min, reverse=True)
    activity = activity[:12]

    stores = Store.query.order_by(Store.created_at.desc()).all()

    return dict(
        total_stores=total_stores, active_count=active_count,
        trial_count=trial_count, paid_count=paid_count,
        estimated_mrr=estimated_mrr, inactive_count=inactive_count,
        new_stores_30d=new_stores_30d, new_stores_delta=new_stores_delta,
        churn_30d=churn_30d, churn_delta=churn_delta,
        basic_monthly=basic_monthly, basic_yearly=basic_yearly,
        pro_monthly=pro_monthly, pro_yearly=pro_yearly,
        basic_monthly_mrr=basic_monthly_mrr, basic_yearly_mrr=basic_yearly_mrr,
        pro_monthly_mrr=pro_monthly_mrr, pro_yearly_mrr=pro_yearly_mrr,
        basic_count=basic_count, pro_count=pro_count,
        signup_labels=signup_labels, signup_direct=signup_direct,
        signup_referral=signup_referral,
        plan_dist=plan_dist,
        volume_by_company=volume_by_company,
        total_volume_30d=total_volume_30d,
        total_transfers_30d=total_transfers_30d,
        top_referrers=top_referrers,
        direct_signups=direct_signups, referral_signups=referral_signups,
        activity=activity,
        stores=stores,
    )

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

def pro_required(f):
    """Admin-required + the store must have Pro-tier feature access.

    Bank sync (Stripe Financial Connections, transaction sync, rules,
    reconcile) is gated behind:
      - plan == "pro"      — paid Pro subscriber
      - plan == "trial"    — 7-day trial grants Pro features by default
                             (until get_trial_status reports "expired")
    Stores on plan == "basic" or "inactive" are bounced to /subscribe
    with a flash. Superadmin bypasses the gate so platform debugging
    works regardless of impersonation context.
    """
    @wraps(f)
    def d(*a, **k):
        if "user_id" not in session:
            return redirect(url_for("login"))
        u = current_user()
        if not u or u.role not in ("admin", "superadmin"):
            flash("Admin access required.", "error")
            return redirect(url_for("dashboard"))
        if u.role == "superadmin":
            return f(*a, **k)
        store = current_store()
        if not store:
            flash("Bank sync requires a store context.", "error")
            return redirect(url_for("dashboard"))
        if store.plan == "pro":
            return f(*a, **k)
        if store.plan == "trial" and get_trial_status(store) != "expired":
            return f(*a, **k)
        flash("Bank sync is a Pro plan feature. Upgrade to enable it.", "error")
        return redirect(url_for("subscribe"))
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
    # The topbar crown reads `my_referral_code` directly — only filled in
    # for admins on a paid plan so the button hides itself for trials and
    # employees without any template-level conditional.
    my_referral_code = ""
    if (user.role == "admin"
        and store is not None
        and store.plan in ("basic", "pro")):
        try:
            rc = ReferralCode.query.filter_by(owner_store_id=store.id).first()
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
# any same-day deposits that haven't been entered into the daily book.
INITIAL_SYNC_DAYS_BACK = 1

def stripe_is_configured():
    """We can only start an FC session if Stripe is wired up."""
    return bool(os.environ.get("STRIPE_SECRET_KEY"))

def stripe_publishable_key():
    """The pk_test_/pk_live_ key the browser uses to load Stripe.js.
    Required for the FC connect modal — Stripe.js can't initialize
    without it."""
    return os.environ.get("STRIPE_PUBLISHABLE_KEY", "")

def stripe_mode():
    """'live' if STRIPE_SECRET_KEY starts with sk_live_, else 'test'.
    Empty string if no key is set."""
    sk = os.environ.get("STRIPE_SECRET_KEY", "")
    if not sk:
        return ""
    return "live" if sk.startswith("sk_live_") else "test"

def _stripe_price_ids():
    """Resolve {plan_key: price_id} for all four plan tiers.

    Reads the four STRIPE_*_PRICE_ID env vars and returns a dict keyed
    by the internal plan slug (basic / basic_yearly / pro / pro_yearly).
    Empty string for unset env vars matches the get-or-default pattern
    used at every prior call site. Centralised here so a future tier
    change touches the env list once instead of grep-replacing across
    health-check, subscribe, and webhook handlers.
    """
    return {
        "basic":        os.environ.get("STRIPE_BASIC_PRICE_ID", ""),
        "basic_yearly": os.environ.get("STRIPE_BASIC_YEARLY_PRICE_ID", ""),
        "pro":          os.environ.get("STRIPE_PRO_PRICE_ID", ""),
        "pro_yearly":   os.environ.get("STRIPE_PRO_YEARLY_PRICE_ID", ""),
    }

def ensure_stripe_customer(store):
    """Return a Stripe customer id for this store, creating one if needed.

    Stripe FC requires an `account_holder={"type":"customer", ...}` on
    every Financial Connections session — so even trial / inactive stores
    that haven't paid yet need a customer record to link a bank account.
    We reuse the existing billing customer when present.

    Self-heals when the cached id was created in a different Stripe mode
    (e.g. test → live migration). On "No such customer" the cached id is
    cleared and a fresh customer is minted in the current mode. Customer
    retrieves are not metered, so the verify-then-use cost is effectively
    zero per connect attempt.
    """
    if store.stripe_customer_id:
        try:
            stripe.Customer.retrieve(store.stripe_customer_id)
            return store.stripe_customer_id
        except stripe.error.InvalidRequestError as e:
            msg = str(e)
            if "No such customer" in msg or "resource_missing" in msg:
                app.logger.warning(
                    f"Stripe customer {store.stripe_customer_id} not found "
                    f"in current mode for store {store.id}; minting fresh.")
                store.stripe_customer_id = ""
            else:
                raise
    try:
        cust = stripe.Customer.create(
            email=(store.email or None),
            name=store.name,
            metadata={"store_id": str(store.id)},
        )
    except stripe.error.StripeError as e:
        app.logger.error(f"Stripe customer create failed for store {store.id}: {e}")
        raise
    store.stripe_customer_id = cust.id
    db.session.commit()
    return cust.id

def _upsert_fc_account(store_id, api_obj):
    """Persist (or refresh) a FinancialConnectionsAccount into our cache."""
    acct_id = api_obj.get("id") if isinstance(api_obj, dict) else api_obj.id
    existing = StripeBankAccount.query.filter_by(stripe_account_id=acct_id).first()
    row = existing or StripeBankAccount(store_id=store_id, stripe_account_id=acct_id)
    institution = api_obj.get("institution_name") if isinstance(api_obj, dict) else getattr(api_obj, "institution_name", "")
    display     = api_obj.get("display_name")     if isinstance(api_obj, dict) else getattr(api_obj, "display_name", "")
    last4       = api_obj.get("last4")            if isinstance(api_obj, dict) else getattr(api_obj, "last4", "")
    category    = api_obj.get("category")         if isinstance(api_obj, dict) else getattr(api_obj, "category", "")
    subcategory = api_obj.get("subcategory")      if isinstance(api_obj, dict) else getattr(api_obj, "subcategory", "")
    row.institution_name = institution or row.institution_name or ""
    row.display_name     = display or row.display_name or ""
    row.last4            = last4 or row.last4 or ""
    row.category         = category or row.category or ""
    row.subcategory      = subcategory or row.subcategory or ""
    # Balance payload lives inside the "balance" field; may be missing if
    # the "balances" permission wasn't granted, or null if Stripe's
    # async balance fetch hasn't completed yet (common right after
    # connect when prefetch wasn't requested).
    bal = api_obj.get("balance") if isinstance(api_obj, dict) else getattr(api_obj, "balance", None)
    if bal:
        current = bal.get("current") if isinstance(bal, dict) else getattr(bal, "current", None)
        as_of   = bal.get("as_of")   if isinstance(bal, dict) else getattr(bal, "as_of", None)
        # Stripe returns balances as a dict {"usd": <cents>}; we pick
        # whatever matches the account currency, falling back to the
        # first value. Guard against a missing/empty `current` so we
        # don't crash with StopIteration / TypeError on partial responses.
        cents = 0
        if isinstance(current, dict) and current:
            cents = current.get(row.currency or "usd") or next(iter(current.values()), 0)
        elif current is not None:
            cents = current
        try:
            row.last_balance_cents = int(cents or 0)
        except (TypeError, ValueError):
            row.last_balance_cents = 0
        if as_of:
            try:
                row.last_balance_as_of = datetime.utcfromtimestamp(int(as_of))
            except (TypeError, ValueError):
                pass
    row.enabled = True
    row.disconnected_at = None
    if existing is None:
        db.session.add(row)
    db.session.flush()
    return row

def refresh_bank_balances(store):
    """Pull fresh balances for every enabled account on the store.

    Stripe requires the `balances` feature to be refreshed explicitly when
    the cached value is stale; we call Account.refresh_account(
    features=["balance"]) and then retrieve to capture the new snapshot.

    Returns (updated_count, error_message_or_empty). The caller can
    surface error_message in a flash so the operator sees *why* a
    refresh failed without grepping the server log.
    """
    if not stripe_is_configured():
        return 0, "Stripe is not configured."
    updated = 0
    last_error = ""
    for acct in StripeBankAccount.query.filter_by(store_id=store.id, enabled=True).all():
        try:
            # SDK note: the operation is `refresh_account` (not `refresh`).
            # `refresh` is the inherited APIResource instance method that
            # only re-fetches local state; calling it with kwargs raises
            # "got an unexpected keyword argument 'features'".
            stripe.financial_connections.Account.refresh_account(
                acct.stripe_account_id, features=["balance"],
            )
            api_obj = stripe.financial_connections.Account.retrieve(acct.stripe_account_id)
            _upsert_fc_account(store.id, api_obj)
            updated += 1
        except stripe.error.StripeError as e:
            msg = e.user_message or str(e)
            last_error = f"{acct.display_name or acct.stripe_account_id}: {msg}"
            app.logger.warning(f"FC refresh failed for {acct.stripe_account_id}: {e}")
        except Exception as e:
            # Anything not a StripeError — usually a response-shape mismatch
            # in _upsert_fc_account or a network blip. Logged with full
            # traceback so the cause is visible in Render logs.
            last_error = f"{acct.display_name or acct.stripe_account_id}: {type(e).__name__}: {e}"
            app.logger.exception(f"FC refresh crashed for {acct.stripe_account_id}")
    if updated:
        db.session.commit()
    return updated, last_error

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
    Idempotent on stripe_transaction_id."""
    txn_id = api_obj.get("id") if isinstance(api_obj, dict) else api_obj.id
    existing = BankTransaction.query.filter_by(stripe_transaction_id=txn_id).first()
    row = existing or BankTransaction(
        store_id=store_id,
        stripe_bank_account_id=account_row.id,
        stripe_transaction_id=txn_id,
        amount_cents=0,
    )
    amt = api_obj.get("amount") if isinstance(api_obj, dict) else getattr(api_obj, "amount", 0)
    cur = api_obj.get("currency") if isinstance(api_obj, dict) else getattr(api_obj, "currency", "usd")
    desc = api_obj.get("description") if isinstance(api_obj, dict) else getattr(api_obj, "description", "")
    status = api_obj.get("status") if isinstance(api_obj, dict) else getattr(api_obj, "status", "posted")
    transacted_at = (api_obj.get("transacted_at") if isinstance(api_obj, dict)
                     else getattr(api_obj, "transacted_at", None))
    try:
        row.amount_cents = int(amt or 0)
    except (TypeError, ValueError):
        row.amount_cents = 0
    row.currency = (cur or "usd").lower()
    row.description = (desc or "")[:500]
    row.status = status or "posted"
    if transacted_at:
        try:
            row.posted_at = datetime.utcfromtimestamp(int(transacted_at))
        except (TypeError, ValueError):
            pass
    if existing is None:
        db.session.add(row)
    db.session.flush()
    return row, (existing is None)

# ── Bank reconcile + rules ──────────────────────────────────
# Categories that can appear on a BankTransaction.category_slug. The
# canonical set is _LINE_ITEM_KINDS (which auto-creates a DailyLineItem
# on the transaction's date) plus these non-posting tags for cases
# where the transaction is reconciled but shouldn't double-count in
# the daily book — internal transfers between own accounts, MT ACH
# withdrawals that already match an ACHBatch, or "ignore" for noise.
BANK_CATEGORIES_NON_POSTING = {
    "internal_transfer":  "Internal transfer",
    "mt_ach_intermex":    "MT ACH — Intermex",
    "mt_ach_maxi":        "MT ACH — Maxi",
    "mt_ach_barri":       "MT ACH — Barri",
    # Bank charges flow into the MonthlyFinancial P&L's
    # bank_charges_total field (single consolidated line). Historic
    # 210/230-suffixed slugs are kept so already-tagged transactions
    # still feed the P&L; new tagging uses the generic slug.
    "bank_charge":        "Bank charge",
    "bank_charge_210":    "Bank charge — ••0210",
    "bank_charge_230":    "Bank charge — ••0230 (MSB)",
    "ignore":             "Ignore (don't reconcile)",
}

# Built-in (platform-managed) rules that fire after user-defined rules
# don't match. Used for transaction descriptions that are STANDARD across
# all customers of a given bank — e.g. Nizari Progressive's RDC fee
# always appears as "REMOTE DEPOSIT FEE" on the MSB ••0230 account.
# Operators don't need to set up their own rule for these, and they
# can't be edited via /bank/rules.
#
# Each entry: (description_substring, account_last4_or_None, target_kind).
# An empty `account_last4` matches any account.
_BUILTIN_BANK_RULES = [
    # Nizari Progressive Federal Credit Union
    ("REMOTE DEPOSIT FEE", "0230", "bank_charge_230"),
    # Below-average-balance fee can hit either Nizari account when a
    # balance dips below their threshold; account-agnostic match.
    ("BELOW AVG BAL FEE",  "",     "bank_charge"),
    # Per-deposit fee on the MSB account when paper checks are
    # deposited. Account-agnostic — Nizari has applied this to either
    # account historically.
    ("CHECK DEPOSIT FEE",  "",     "bank_charge"),
    # Monthly MSB account maintenance fee. Hits the ••0230 MSB
    # account; we still match account-agnostic in case Nizari ever
    # bills it on a different account.
    ("MSB MONTHLY FEE",    "",     "bank_charge"),
]

# Registry: bank-transaction category_slug → MonthlyFinancial column.
# Any category listed here flows automatically into the named P&L
# column at month-end (the absolute monthly sum), and the field on
# /monthly/<year>/<month> conditionally locks when auto > 0. Adding a
# new automation = (1) add a rule to _BUILTIN_BANK_RULES OR let the
# operator categorise manually, (2) add a row here so the auto-feed
# picks it up. If the target column doesn't exist on MonthlyFinancial
# yet, also add it to the model + _ADDED_COLUMNS.
#
# This is the single point of truth for "auto-tagged → P&L" — every
# new category goes through here so future automations don't need
# bespoke wiring in monthly_report().
_BANK_CATEGORY_PL_FIELD = {
    # Both Nizari-account slugs (kept for historic transaction tags)
    # plus the generic slug all flow into the single consolidated
    # bank_charges_total column. The auto-feed loop in monthly_report
    # sums per-slug into the field, so multiple slugs sharing one
    # column is supported by design.
    "bank_charge_210": "bank_charges_total",
    "bank_charge_230": "bank_charges_total",
    "bank_charge":     "bank_charges_total",
}

def _match_builtin_bank_rule(txn, account):
    """Return target_kind from _BUILTIN_BANK_RULES that matches the
    transaction, or None if nothing matches."""
    desc = (txn.description or "").upper()
    last4 = (account.last4 or "") if account else ""
    for substring, want_last4, target in _BUILTIN_BANK_RULES:
        if substring not in desc:
            continue
        if want_last4 and last4 != want_last4:
            continue
        return target
    return None

def _bank_category_label(slug):
    """Operator-friendly label for a category slug."""
    if not slug:
        return "Uncategorized"
    if slug in BANK_CATEGORIES_NON_POSTING:
        return BANK_CATEGORIES_NON_POSTING[slug]
    if slug in _LINE_ITEM_KINDS:
        return _LINE_ITEM_KINDS[slug][1].title()
    return slug

def _bank_category_groups():
    """Grouped (group_label, [(slug, label), ...]) tuples for dropdowns.

    The two groups stay separate in the UI so operators don't confuse
    auto-posting kinds with non-posting tags.
    """
    daily = [(slug, meta[1].title()) for slug, meta in _LINE_ITEM_KINDS.items()]
    other = list(BANK_CATEGORIES_NON_POSTING.items())
    return [
        ("Daily-book line items", daily),
        ("Other (no daily-book impact)", other),
    ]

def _is_daily_book_kind(slug):
    return slug in _LINE_ITEM_KINDS

def _bank_rule_matches(rule, txn):
    """True if every set condition on the rule matches the transaction.
    Conditions left unset are treated as 'any'.

    `rule.enabled` is None on a transient (un-persisted) row because
    SQLAlchemy column defaults only fire on insert; treat None as True
    so callers can match against a freshly-constructed rule.
    """
    if rule.enabled is False:
        return False
    # Description match
    if rule.desc_match_type and rule.desc_match_value:
        desc = (txn.description or "")
        val = rule.desc_match_value
        mt = rule.desc_match_type
        if mt == "regex":
            try:
                if not re.search(val, desc, re.IGNORECASE):
                    return False
            except re.error:
                return False
        else:
            d = desc.lower()
            v = val.lower()
            if mt == "contains" and v not in d:
                return False
            if mt == "starts_with" and not d.startswith(v):
                return False
            if mt == "equals" and d != v:
                return False
    # Sign filter
    if rule.sign_filter == "credit" and (txn.amount_cents or 0) < 0:
        return False
    if rule.sign_filter == "debit" and (txn.amount_cents or 0) >= 0:
        return False
    # Amount range — both bounds use absolute cents
    abs_cents = abs(txn.amount_cents or 0)
    if rule.amount_min_cents is not None and abs_cents < rule.amount_min_cents:
        return False
    if rule.amount_max_cents is not None and abs_cents > rule.amount_max_cents:
        return False
    # Account filter
    if rule.account_filter_id and rule.account_filter_id != txn.stripe_bank_account_id:
        return False
    return True

def _find_matching_rule(store_id, txn):
    """First enabled rule (lowest priority first) that matches the
    transaction. None if no rule applies."""
    rules = (BankRule.query
             .filter_by(store_id=store_id, enabled=True)
             .order_by(BankRule.priority.asc(), BankRule.id.asc()).all())
    for rule in rules:
        if _bank_rule_matches(rule, txn):
            return rule
    return None

def _apply_rules_to_uncategorized_row(row, account, *, allow_auto_post):
    """Run the rule chain (operator BankRule → built-in) against an
    uncategorised bank transaction and tag it. Returns True if the
    row was tagged.

    Idempotent: rows that already have a category_slug are left
    untouched, so operator overrides survive.

    `allow_auto_post` controls whether a matched operator rule with
    auto_post=True also creates a DailyLineItem. Pass True for
    freshly-inserted rows (operator's expressed intent on new data),
    False when backfilling historical rows (the daily book may
    already be reconciled — let the operator post manually).
    Built-in rules never post to the daily book regardless.

    Caller commits.
    """
    if row.category_slug:
        return False
    rule = _find_matching_rule(row.store_id, row)
    if rule is not None:
        _categorize_bank_transaction(
            row, rule.target_kind, rule=rule,
            post_to_daily=(rule.auto_post and allow_auto_post))
        return True
    builtin = _match_builtin_bank_rule(row, account)
    if builtin:
        _categorize_bank_transaction(
            row, builtin, rule=None, post_to_daily=False)
        return True
    return False


def _categorize_bank_transaction(txn, target_kind, rule=None,
                                  post_to_daily=True, report_date=None):
    """Set the transaction's category. If target_kind is a daily-book
    kind AND post_to_daily is True, also create a linked DailyLineItem.
    Caller commits.

    `report_date` (optional, datetime.date) overrides the daily-book
    line's date. Used for the RDC case where the bank posts the
    transaction next morning but the cash-handling event belongs on
    the previous day's book. When None, defaults to the transaction's
    posted_at date.

    Idempotent: re-categorizing removes the previously-linked
    DailyLineItem (if any) before creating a fresh one.
    """
    # Drop any prior auto-created DailyLineItem.
    if txn.daily_line_item_id:
        old = db.session.get(DailyLineItem, txn.daily_line_item_id)
        if old is not None:
            db.session.delete(old)
        txn.daily_line_item_id = None

    txn.category_slug = target_kind or ""
    txn.matched_rule_id = rule.id if rule else None

    if rule is not None:
        rule.match_count = (rule.match_count or 0) + 1
        rule.last_matched_at = datetime.utcnow()

    if post_to_daily and target_kind and _is_daily_book_kind(target_kind):
        when = txn.posted_at or datetime.utcnow()
        line_date = report_date if report_date is not None else when.date()
        line = DailyLineItem(
            store_id=txn.store_id,
            report_date=line_date,
            kind=target_kind,
            at_time=when.time(),
            # The daily-book model expects positive amounts. We store
            # the absolute value; the kind itself encodes whether it's
            # an inflow or outflow for the daily report.
            amount=abs(float(txn.amount_cents or 0) / 100.0),
            note=(txn.description or "")[:120],
        )
        db.session.add(line)
        db.session.flush()
        txn.daily_line_item_id = line.id

def _uncategorize_bank_transaction(txn):
    """Clear category + delete linked DailyLineItem if any. Caller commits."""
    if txn.daily_line_item_id:
        old = db.session.get(DailyLineItem, txn.daily_line_item_id)
        if old is not None:
            db.session.delete(old)
        txn.daily_line_item_id = None
    txn.category_slug = ""
    txn.matched_rule_id = None

def sync_bank_transactions(store, since=None, until=None):
    """Pull transactions from every enabled FC account on the store.

    `since` / `until` are datetimes mapped to Stripe's
    transacted_at[gte] / transacted_at[lte] filters (Stripe expects unix
    seconds). When `since` is None, we use the latest posted_at we've
    already cached for that account, falling back to the
    INITIAL_SYNC_DAYS_BACK window. Stripe Transaction.list paginates
    in 100s; we use auto_paging_iter to walk every page.

    Returns (new_rows, total_seen, last_error). new_rows is the count
    of rows we inserted (vs updated); total_seen counts every row
    we touched. last_error is empty unless one or more accounts errored.
    """
    if not stripe_is_configured():
        return 0, 0, "Stripe is not configured."
    new_rows = 0
    total = 0
    last_error = ""
    now = datetime.utcnow()
    fallback_since = datetime.combine(
        (now - timedelta(days=INITIAL_SYNC_DAYS_BACK)).date(),
        datetime.min.time())
    for acct in StripeBankAccount.query.filter_by(
            store_id=store.id, enabled=True).all():
        try:
            # Idempotent self-heal: ensure this account is subscribed to
            # the transactions feature. Accounts connected before the
            # subscribe step was added to bank_stripe_return won't have
            # any transactions otherwise. Stripe accepts the call on
            # already-subscribed accounts without error.
            try:
                stripe.financial_connections.Account.subscribe(
                    acct.stripe_account_id, features=["transactions"])
            except stripe.error.StripeError as e:
                app.logger.warning(
                    f"FC transactions subscribe (sync) failed for "
                    f"{acct.stripe_account_id}: {e}")
            # Trigger an explicit refresh so Stripe pulls fresh data
            # from the bank before we list. The refresh is async — this
            # call may return stale data, but the NEXT manual sync will
            # see whatever the bank has now. Best-effort; failure is
            # logged but doesn't abort the sync.
            try:
                stripe.financial_connections.Account.refresh_account(
                    acct.stripe_account_id, features=["transactions"])
            except stripe.error.StripeError as e:
                app.logger.warning(
                    f"FC transactions refresh (sync) failed for "
                    f"{acct.stripe_account_id}: {e}")
            # Resolve the lower bound. Two paths:
            # - Caller-provided `since` (initial connect uses this to
            #   request yesterday + today only).
            # - Otherwise: rolling 7-day lookback. Stripe FC surfaces
            #   transactions retroactively — a transaction posted on
            #   May 1 may not appear in Stripe's feed until May 3 — so
            #   filtering strictly by `max(posted_at) we already have`
            #   would skip late-arriving rows. Re-fetching old rows is
            #   free (Transaction.list is billed per call, not per row,
            #   and _upsert_bank_transaction dedupes on
            #   stripe_transaction_id). 7 days covers Stripe's typical
            #   retroactive window with margin.
            if since is not None:
                lo = since
            else:
                lo = max(datetime.utcnow() - timedelta(days=7),
                          fallback_since)
            params = {
                "account": acct.stripe_account_id,
                "limit": 100,
                "transacted_at": {"gte": int(lo.timestamp())},
            }
            if until is not None:
                params["transacted_at"]["lte"] = int(until.timestamp())
            for txn in stripe.financial_connections.Transaction.list(
                    **params).auto_paging_iter():
                row, inserted = _upsert_bank_transaction(store.id, acct, txn)
                if inserted:
                    new_rows += 1
                # Apply rules whenever the row is uncategorised — both
                # fresh inserts AND backfill of older rows that landed
                # before a matching rule existed. Operator overrides
                # (any non-empty category_slug) survive untouched.
                # auto_post is suppressed during backfill so we don't
                # surprise-post into an already-reconciled daily book.
                _apply_rules_to_uncategorized_row(
                    row, acct, allow_auto_post=inserted)
                total += 1
        except stripe.error.StripeError as e:
            msg = e.user_message or str(e)
            last_error = f"{acct.display_name or acct.stripe_account_id}: {msg}"
            app.logger.warning(f"FC txn sync failed for {acct.stripe_account_id}: {e}")
        except Exception as e:
            last_error = f"{acct.display_name or acct.stripe_account_id}: {type(e).__name__}: {e}"
            app.logger.exception(f"FC txn sync crashed for {acct.stripe_account_id}")
    if total:
        db.session.commit()
    return new_rows, total, last_error

# ── PWA ──────────────────────────────────────────────────────
# Service worker must be served from root so its default scope covers
# every path. The file lives in /static/ but is routed here.
@app.route("/sw.js")
def service_worker():
    resp = send_from_directory("static", "sw.js", mimetype="application/javascript")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp

@app.route("/offline")
def offline():
    """Plain offline page. Precached by the service worker so it
    renders even when the network is completely unavailable."""
    return render_template("offline.html")

# ── Push notifications ───────────────────────────────────────
# Operators generate a VAPID keypair once (see docs/push-keys.md)
# and set the three env vars below. When they're not set, push
# endpoints return 501 and the opt-in UI stays hidden.
VAPID_PUBLIC_KEY  = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT     = os.environ.get("VAPID_SUBJECT", "mailto:admin@example.com")

def push_enabled() -> bool:
    return bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY)

def send_push(user_id: int, title: str, body: str = "", url: str = "/", tag: str | None = None) -> int:
    """Deliver a push notification to every device the user has
    subscribed. Returns the number of successful sends. Dead
    subscriptions (404/410 from the push provider) are cleaned up."""
    if not push_enabled():
        return 0
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        app.logger.warning("pywebpush not installed; skipping send_push")
        return 0
    payload = json.dumps({k: v for k, v in {"title": title, "body": body, "url": url, "tag": tag}.items() if v is not None})
    sent = 0
    subs = PushSubscription.query.filter_by(user_id=user_id).all()
    for s in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": s.endpoint,
                    "keys": {"p256dh": s.p256dh, "auth": s.auth},
                },
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_SUBJECT},
            )
            sent += 1
        except WebPushException as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (404, 410):
                # Subscription gone — drop it.
                db.session.delete(s)
            else:
                app.logger.warning(f"push send failed ({status}): {e}")
    db.session.commit()
    return sent

@app.route("/api/push/public-key")
def push_public_key():
    """Frontend reads this to build a PushManager subscription.

    Returns 200 with key=null when VAPID isn't configured so deployments
    without push don't fill every user's console with a red 501 on page
    load. The client treats null as "feature unavailable" and hides the
    opt-in button.
    """
    return jsonify({"key": VAPID_PUBLIC_KEY if push_enabled() else None})

@app.route("/api/push/subscribe", methods=["POST"])
def push_subscribe():
    u = current_user()
    if not u:
        return jsonify({"error": "auth"}), 401
    if not push_enabled():
        return jsonify({"error": "push not configured"}), 501
    data = request.get_json(silent=True) or {}
    endpoint = (data.get("endpoint") or "").strip()
    keys = data.get("keys") or {}
    p256dh = (keys.get("p256dh") or "").strip()
    auth   = (keys.get("auth") or "").strip()
    if not endpoint or not p256dh or not auth:
        return jsonify({"error": "missing fields"}), 400
    existing = PushSubscription.query.filter_by(user_id=u.id, endpoint=endpoint).first()
    if not existing:
        db.session.add(PushSubscription(
            user_id=u.id, endpoint=endpoint, p256dh=p256dh, auth=auth,
            user_agent=(request.headers.get("User-Agent") or "")[:255],
        ))
        db.session.commit()
    return jsonify({"ok": True})

@app.route("/api/push/unsubscribe", methods=["POST"])
def push_unsubscribe():
    u = current_user()
    if not u:
        return jsonify({"error": "auth"}), 401
    endpoint = (request.get_json(silent=True) or {}).get("endpoint", "")
    if endpoint:
        PushSubscription.query.filter_by(user_id=u.id, endpoint=endpoint).delete()
        db.session.commit()
    return jsonify({"ok": True})

@app.route("/api/push/test", methods=["POST"])
def push_test():
    """Send a test notification to the caller's own devices."""
    u = current_user()
    if not u:
        return jsonify({"error": "auth"}), 401
    n = send_push(u.id, "DineroBook", "Push notifications are working on this device.", url="/")
    return jsonify({"sent": n})

# ── Referrals ────────────────────────────────────────────────
REFERRAL_SELF_CENTS    = 10000   # $100 for the referrer
REFERRAL_REFEREE_CENTS = 5000    # $50 for the new store

def _new_referral_code():
    """Mint an 8-char uppercase alphanumeric referral code, checking uniqueness.
    Tries up to 12 times before giving up — that ceiling is effectively
    unreachable at any realistic volume."""
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(12):
        code = "".join(secrets.choice(alphabet) for _ in range(8))
        if not ReferralCode.query.filter_by(code=code).first():
            return code
    raise RuntimeError("Could not mint a unique referral code")

def ensure_referral_code(store):
    """Return the store's ReferralCode, creating it on demand.

    Admins only see the crown once they're on a paid plan, so call sites
    should already have checked `store.plan in {basic, pro}` — we don't
    enforce here (the superadmin / testing flows may want to pre-mint).
    """
    if not store:
        return None
    rc = ReferralCode.query.filter_by(owner_store_id=store.id).first()
    if rc is not None:
        return rc
    rc = ReferralCode(
        code=_new_referral_code(),
        owner_store_id=store.id,
        reward_self_cents=REFERRAL_SELF_CENTS,
        reward_referee_cents=REFERRAL_REFEREE_CENTS,
    )
    db.session.add(rc); db.session.flush()
    return rc

def lookup_referral_code(raw):
    """Return the active ReferralCode matching the raw input, or None.
    Accepts either the code string or a URL like /signup?ref=ABC123."""
    if not raw:
        return None
    code = raw.strip().upper()
    if not code:
        return None
    rc = ReferralCode.query.filter_by(code=code, is_active=True).first()
    return rc

def apply_pending_referral_credits(referee_store):
    """Called from the Stripe webhook when a store transitions to a paid
    plan. If that store was referred AND hasn't been credited yet, apply
    the referee's $50 to their Stripe balance and the referrer's $100
    to theirs — recording a ReferralRedemption row so retries are safe.
    """
    if not referee_store or not referee_store.referred_by_code_id:
        return
    # Already credited on this store? bail — keeps webhook retries idempotent.
    if referee_store.referee_credit_applied_at:
        return
    rc = db.session.get(ReferralCode, referee_store.referred_by_code_id)
    if not rc or not rc.is_active:
        return
    owner = db.session.get(Store, rc.owner_store_id)
    if not owner:
        return
    now = datetime.utcnow()
    # Referee credit: must have stripe_customer_id by this point (webhook
    # fires on checkout.session.completed, which also sets it upstream).
    referee_txn_id = ""
    if referee_store.stripe_customer_id and stripe_is_configured():
        try:
            txn = stripe.Customer.create_balance_transaction(
                referee_store.stripe_customer_id,
                amount=-abs(rc.reward_referee_cents),
                currency="usd",
                description=f"Referral credit — welcome! Used code {rc.code}",
                metadata={"referral_code": rc.code, "side": "referee"},
            )
            referee_txn_id = getattr(txn, "id", "") or ""
        except stripe.error.StripeError as e:
            app.logger.warning(f"referee credit failed for store {referee_store.id}: {e}")
    # Referrer credit (only when they have a Stripe customer, which they
    # do since they're on a paid plan — but guard anyway).
    self_txn_id = ""
    if owner.stripe_customer_id and stripe_is_configured():
        try:
            txn = stripe.Customer.create_balance_transaction(
                owner.stripe_customer_id,
                amount=-abs(rc.reward_self_cents),
                currency="usd",
                description=f"Referral reward — {referee_store.name} just subscribed",
                metadata={"referral_code": rc.code, "side": "referrer",
                          "referee_store_id": str(referee_store.id)},
            )
            self_txn_id = getattr(txn, "id", "") or ""
        except stripe.error.StripeError as e:
            app.logger.warning(f"referrer credit failed for referrer {owner.id}: {e}")
    # Record the redemption regardless of whether Stripe succeeded — so we
    # don't double-post on a webhook retry. The txn_id is "" on failure,
    # and the superadmin can reconcile manually.
    db.session.add(ReferralRedemption(
        referral_code_id=rc.id,
        referee_store_id=referee_store.id,
        self_credit_applied_at=now if self_txn_id else None,
        referee_credit_applied_at=now if referee_txn_id else None,
        stripe_self_txn_id=self_txn_id,
        stripe_referee_txn_id=referee_txn_id,
    ))
    rc.redeemed_count = (rc.redeemed_count or 0) + 1
    referee_store.referee_credit_applied_at = now
    # Caller commits — keeps this function transactional alongside the
    # plan transition that triggered it.

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
    store = Store.query.filter_by(slug=slug).first()
    if store and store.is_active:
        return store
    return None

@app.route("/")
def landing():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    store = _active_store_from_cookie()
    if store:
        return redirect(url_for("login_store", slug=store.slug))
    return render_template("landing.html")

@app.route("/privacy")
def privacy():
    """Public privacy policy page. Used as the privacy URL on Stripe
    (Financial Connections and Checkout require it). No auth — any
    visitor, logged in or not, can read it."""
    return render_template("privacy.html")

# ── 2FA (TOTP) helpers ───────────────────────────────────────
# Mandatory for superadmin; other roles opt out entirely today.
# The login flow is:
#   1) POST /login → creds valid → session["pending_auth_user_id"] = uid
#   2) redirect to /login/2fa (if enrolled) or /login/2fa/enroll (if not)
#   3) successful TOTP / recovery code → _finalize_2fa_login() promotes
#      pending_auth_user_id → real user_id session.
# Nothing outside this block should set user_id on its own for a
# 2FA-required role.

RECOVERY_CODES_PER_USER = 10
TOTP_ISSUER = "DineroBook"

def _needs_totp(user):
    """Which roles must use 2FA. Keep this the single gatekeeper."""
    return bool(user and user.role == "superadmin")

def _totp_is_enrolled(user):
    return bool(user and user.totp_secret and user.totp_enrolled_at)

def _pending_auth_user():
    uid = session.get("pending_auth_user_id")
    return db.session.get(User, uid) if uid else None

def _hash_recovery_code(raw):
    # Normalize so casing/whitespace/hyphen differences don't lock the
    # user out. The display format is e.g. "ABCD-EFGH" but the stored
    # hash is of the unhyphenated, uppercase form.
    normalized = raw.strip().upper().replace("-", "").replace(" ", "")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

def _format_recovery_code(raw):
    """Pretty-print with a hyphen in the middle so codes are easier to
    read and to transcribe — e.g. 'ABCD-EFGH'."""
    s = raw.strip().upper()
    return f"{s[:4]}-{s[4:]}" if len(s) == 8 else s

def _generate_recovery_codes(user):
    """Wipe any existing codes for this user and mint a fresh batch.
    Returns the plaintext list (shown to the user exactly once)."""
    RecoveryCode.query.filter_by(user_id=user.id).delete()
    plaintext = []
    for _ in range(RECOVERY_CODES_PER_USER):
        raw = secrets.token_hex(4).upper()  # 8 hex chars
        plaintext.append(raw)
        db.session.add(RecoveryCode(user_id=user.id, code_hash=_hash_recovery_code(raw)))
    db.session.commit()
    return [_format_recovery_code(c) for c in plaintext]

def _consume_recovery_code(user, raw):
    """Return True if `raw` matches an unused code for `user` and mark
    it used. `raw` may be pasted with or without the hyphen."""
    if not raw:
        return False
    row = (RecoveryCode.query
           .filter_by(user_id=user.id, code_hash=_hash_recovery_code(raw), used_at=None)
           .first())
    if not row:
        return False
    row.used_at = datetime.utcnow()
    db.session.commit()
    return True

def _verify_totp(user, token):
    """True if `token` is a valid current (or immediately adjacent) 6-digit
    TOTP code for `user`. `valid_window=1` forgives a ±30s clock drift."""
    if not (user and user.totp_secret and token):
        return False
    try:
        return pyotp.TOTP(user.totp_secret).verify(str(token).strip(), valid_window=1)
    except Exception:
        return False

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
    """The effective RP ID. Passkeys are cryptographically bound to
    this string — it has to match across registration + authentication
    and survive a login from any path on the same host. Prefer an
    explicit env var (prod sets WEBAUTHN_RP_ID=dinerobook.com);
    otherwise strip the port off the request Host (localhost:5000 → localhost)."""
    explicit = os.environ.get("WEBAUTHN_RP_ID", "").strip()
    if explicit:
        return explicit
    return request.host.split(":", 1)[0]

def _webauthn_rp_name():
    return "DineroBook"

def _webauthn_origin():
    """Expected Origin header for WebAuthn verification — scheme + host.
    The browser signs this alongside the challenge; a mismatch means
    the request came from a different tab/frame and is rejected."""
    return f"{request.scheme}://{request.host}"

def _passkey_exclude_list(user):
    """Credential descriptors for every passkey this user already has,
    passed to the browser as excludeCredentials so the same physical
    authenticator can't be registered twice on one account."""
    return [
        PublicKeyCredentialDescriptor(id=p.credential_id)
        for p in Passkey.query.filter_by(user_id=user.id).all()
    ]

def _passkey_eligible(user):
    """Whether a user may enroll passkeys. Now: any logged-in user.
    Kept as a single predicate so future tightening (e.g. "deny pending
    self-deletion accounts") has one place to land."""
    return bool(user)

def _update_user_password(user, current_pw, new_pw, confirm_pw):
    """Validate + apply a password change. Returns ({} on success,
    {field: message} on failure). Caller commits the session and
    flashes; we keep this pure so it works from /admin/settings,
    /account/security, or any future surface."""
    errors = {}
    if not user.check_password(current_pw or ""):
        errors["current_password"] = "Current password is incorrect."
    elif len(new_pw or "") < 8:
        errors["new_password"] = "Password must be at least 8 characters."
    elif new_pw != confirm_pw:
        errors["confirm_password"] = "Passwords do not match."
    if not errors:
        user.set_password(new_pw)
    return errors

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

def _record_login(user):
    """Stamp last_login_at on a successful sign-in. Called by every
    login path (password, store-scoped, owner, passkey). Caller must
    commit; we don't, because some login paths batch other writes
    (sign_count update on passkey login) into the same transaction."""
    user.last_login_at = datetime.utcnow()

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

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        u = current_user()
        if u and u.role == "owner":
            return redirect(url_for("owner_dashboard"))
        return redirect(url_for("dashboard"))
    # On a fresh GET from a device that previously signed in to a store,
    # bounce to that store's login so installed-PWA employees aren't stuck
    # on the generic page with the address bar hidden.
    if request.method == "GET":
        store = _active_store_from_cookie()
        if store:
            return redirect(url_for("login_store", slug=store.slug))
    error=None
    if request.method=="POST":
        username=request.form.get("username","").strip()
        u=User.query.filter_by(username=username).first()
        if u and u.is_active and u.check_password(request.form.get("password","")):
            if u.role == "employee":
                # Don't authenticate on the generic page, but leave a
                # breadcrumb: persist the slug so their next hit to `/`
                # or `/login` auto-redirects to `/login/<slug>` (helps
                # PWA installs where the address bar is hidden).
                emp_store = db.session.get(Store, u.store_id) if u.store_id else None
                error = "Please use your store's sign-in page. Enter your store code below."
                resp = make_response(render_template(
                    "login.html", error=error,
                    store_code_value=(emp_store.slug if emp_store and emp_store.is_active else ""),
                ))
                if emp_store and emp_store.is_active:
                    _set_last_store_slug_cookie(resp, emp_store.slug)
                return resp
            elif _needs_totp(u):
                # Drop any previous partial-auth before starting a new one.
                session.pop("pending_auth_user_id", None)
                session.pop("totp_enrollment_codes", None)
                session["pending_auth_user_id"] = u.id
                if _totp_is_enrolled(u):
                    return redirect(url_for("login_totp"))
                return redirect(url_for("login_totp_enroll"))
            else:
                session["user_id"]=u.id; session["role"]=u.role; session["store_id"]=u.store_id
                _record_login(u); db.session.commit()
                if u.role == "owner":
                    return redirect(url_for("owner_dashboard"))
                return redirect(url_for("dashboard"))
        else:
            error="Invalid username or password."
    return render_template("login.html",error=error)

@app.route("/login/2fa", methods=["GET", "POST"])
def login_totp():
    u = _require_pending_auth()
    if not u:
        return redirect(url_for("login"))
    if not _totp_is_enrolled(u):
        return redirect(url_for("login_totp_enroll"))
    error = None
    if request.method == "POST":
        if _verify_totp(u, request.form.get("code", "")):
            _finalize_2fa_login(u)
            return redirect(url_for("dashboard"))
        error = "That code didn't match. Check the 6 digits in your authenticator app, or use a recovery code."
    return render_template("login_totp.html", error=error)

@app.route("/login/2fa/recover", methods=["GET", "POST"])
def login_totp_recover():
    u = _require_pending_auth()
    if not u:
        return redirect(url_for("login"))
    error = None
    if request.method == "POST":
        if _consume_recovery_code(u, request.form.get("code", "")):
            _finalize_2fa_login(u)
            flash("Recovery code used. Consider regenerating your recovery codes from Security settings.", "success")
            return redirect(url_for("dashboard"))
        error = "Recovery code not recognized, or already used."
    return render_template("login_totp_recover.html", error=error)

@app.route("/login/2fa/enroll", methods=["GET", "POST"])
def login_totp_enroll():
    u = _require_pending_auth()
    if not u:
        return redirect(url_for("login"))
    if _totp_is_enrolled(u):
        return redirect(url_for("login_totp"))
    # First hit: mint a secret if none pending. Refreshes reuse the pending
    # secret so the user's already-scanned QR stays valid.
    if not u.totp_secret:
        u.totp_secret = pyotp.random_base32()
        db.session.commit()
    error = None
    if request.method == "POST":
        if _verify_totp(u, request.form.get("code", "")):
            u.totp_enrolled_at = datetime.utcnow()
            codes = _generate_recovery_codes(u)
            session["totp_enrollment_codes"] = codes
            return redirect(url_for("login_totp_recovery_codes"))
        error = "That code didn't match. Make sure the clock on your phone is accurate, then try the next code your app shows."
    qr_svg = _totp_qr_svg(u.totp_secret, u.username)
    # Group the secret into 4-char chunks for easier manual entry.
    secret_chunks = " ".join(u.totp_secret[i:i+4] for i in range(0, len(u.totp_secret), 4))
    return render_template("login_totp_enroll.html",
                           qr_svg=qr_svg, secret=u.totp_secret,
                           secret_chunks=secret_chunks, username=u.username,
                           issuer=TOTP_ISSUER, error=error)

@app.route("/login/2fa/recovery-codes", methods=["GET", "POST"])
def login_totp_recovery_codes():
    u = _require_pending_auth()
    if not u:
        return redirect(url_for("login"))
    codes = session.get("totp_enrollment_codes")
    if not codes:
        # No fresh enrollment batch in session — enrollment either already
        # finalized or expired. Send them back to the code prompt.
        return redirect(url_for("login_totp"))
    if request.method == "POST" and request.form.get("saved") == "1":
        _finalize_2fa_login(u)
        flash("2FA is now active on your account. Keep those recovery codes somewhere safe.", "success")
        return redirect(url_for("dashboard"))
    return render_template("login_totp_recovery_codes.html", codes=codes)

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
            _record_login(u); db.session.commit()
            resp = redirect(url_for("dashboard"))
            return _set_last_store_slug_cookie(resp, store.slug)
        error = "Invalid username or password."
    resp = make_response(render_template("login_store.html", store=store, error=error))
    return _set_last_store_slug_cookie(resp, store.slug)

@app.route("/employee-login", methods=["POST"])
def employee_login_redirect():
    """Escape hatch for an installed-PWA employee who lands on the
    generic /login page (cleared cookies / fresh device). They enter
    their store code and we bounce them to /login/<slug>."""
    raw = (request.form.get("store_code") or "").strip().lower()
    # Accept anything that could be a slug; trim to the allowed charset.
    slug = re.sub(r"[^a-z0-9\-]", "", raw)
    if slug:
        store = Store.query.filter_by(slug=slug).first()
        if store and store.is_active:
            resp = redirect(url_for("login_store", slug=slug))
            return _set_last_store_slug_cookie(resp, slug)
    return render_template(
        "login.html",
        error="We couldn't find a store with that code. Check with your manager for the correct code.",
        store_code_value=raw,
    )

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

@app.route("/account/passkeys/register/begin", methods=["POST"])
@login_required
def passkey_register_begin():
    user = current_user()
    if not _passkey_eligible(user):
        return jsonify({"ok": False,
                        "error": "Passkeys aren't enabled for this account."}), 403
    options = generate_registration_options(
        rp_id=_webauthn_rp_id(),
        rp_name=_webauthn_rp_name(),
        user_id=str(user.id).encode("utf-8"),
        user_name=user.username,
        user_display_name=user.full_name or user.username,
        exclude_credentials=_passkey_exclude_list(user),
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    # Challenge is single-use — stored base64url-encoded in the session
    # so it survives the round-trip and the finish route can decode it back.
    session["pk_reg_challenge"] = bytes_to_base64url(options.challenge)
    return Response(options_to_json(options), mimetype="application/json")

@app.route("/account/passkeys/register/finish", methods=["POST"])
@login_required
def passkey_register_finish():
    user = current_user()
    if not _passkey_eligible(user):
        return jsonify({"ok": False,
                        "error": "Passkeys aren't enabled for this account."}), 403
    challenge_b64 = session.pop("pk_reg_challenge", None)
    if not challenge_b64:
        return jsonify({"ok": False,
                        "error": "No registration in progress. Start again."}), 400
    body = request.get_json(silent=True) or {}
    credential = body.get("credential")
    if not credential:
        return jsonify({"ok": False, "error": "Missing credential."}), 400
    name = (body.get("name") or "").strip()[:120] or "Passkey"
    try:
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(challenge_b64),
            expected_origin=_webauthn_origin(),
            expected_rp_id=_webauthn_rp_id(),
            require_user_verification=False,
        )
    except Exception as e:
        # Normalize the error message — library raises a mix of
        # InvalidRegistrationResponse / InvalidJSONStructure / …; the
        # user just needs to know it didn't work.
        return jsonify({"ok": False,
                        "error": f"Passkey could not be verified ({type(e).__name__})."}), 400
    db.session.add(Passkey(
        user_id=user.id,
        credential_id=verification.credential_id,
        public_key=verification.credential_public_key,
        sign_count=verification.sign_count,
        name=name,
        aaguid=str(verification.aaguid or ""),
    ))
    db.session.commit()
    return jsonify({"ok": True, "name": name})

@app.route("/account/passkeys/<int:pk_id>/delete", methods=["POST"])
@login_required
def passkey_delete(pk_id):
    user = current_user()
    pk = Passkey.query.filter_by(id=pk_id, user_id=user.id).first_or_404()
    db.session.delete(pk)
    db.session.commit()
    flash("Passkey removed.", "success")
    return redirect(url_for("account_security"))

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

@app.route("/account/security", methods=["GET", "POST"])
@login_required
def account_security():
    user = current_user()
    errors = {}
    if request.method == "POST":
        action = (request.form.get("_action") or "").strip()
        if action == "password":
            errors = _update_user_password(
                user,
                request.form.get("current_password", ""),
                request.form.get("new_password", ""),
                request.form.get("confirm_password", ""),
            )
            if not errors:
                db.session.commit()
                flash("Password updated.", "success")
                return redirect(url_for("account_security"))
        else:
            abort(400)

    passkeys = (Passkey.query.filter_by(user_id=user.id)
                .order_by(Passkey.created_at.desc()).all())
    return render_template("account_security.html",
        user=user, errors=errors,
        passkeys=passkeys,
        passkeys_eligible=_passkey_eligible(user),
    )

@app.route("/account/profile", methods=["GET", "POST"])
@login_required
def account_profile():
    """Personal profile — display name, email, phone, timezone. Same
    accessibility model as /account/security: every logged-in role can
    reach it, none of these fields cascade into store-scoped data, and
    the form is single-POST with no `_action` since there's only one
    action (save the whole form)."""
    user = current_user()
    errors = {}
    if request.method == "POST":
        errors = _update_user_profile(
            user,
            request.form.get("full_name", ""),
            request.form.get("email", ""),
            request.form.get("phone", ""),
            request.form.get("timezone", ""),
        )
        if not errors:
            db.session.commit()
            flash("Profile updated.", "success")
            return redirect(url_for("account_profile"))

    return render_template("account_profile.html",
        user=user, errors=errors,
        timezone_choices=PROFILE_TIMEZONES,
    )

@app.route("/admin/settings/security", methods=["GET"])
@login_required
def admin_settings_security_redirect():
    """Permanent redirect from the old admin-only Security tab to the
    new shared page. Keeps any bookmarks / external docs working."""
    return redirect(url_for("account_security"), code=301)


@app.route("/account/theme", methods=["POST"])
@login_required
def account_theme():
    """Persist the user's UI theme preference.

    Lives as its own endpoint (not folded into /account/profile) so the
    toggle can be a one-click action with its own redirect target —
    submitting it from any page returns the user to where they were.
    Validates strictly: anything other than "dark" / "light" is treated
    as a no-op rather than wiping the column.
    """
    user = current_user()
    choice = (request.form.get("theme") or "").strip().lower()
    if choice in ("dark", "light"):
        user.theme_preference = choice
        db.session.commit()
        flash(f"Switched to {choice} mode.", "success")
    else:
        flash("Invalid theme — no change.", "error")
    # Bounce back to the referring page so the toggle works from anywhere.
    nxt = request.form.get("next") or request.referrer or url_for("account_profile")
    return redirect(nxt)

@app.route("/account/notifications", methods=["GET", "POST"])
@login_required
def account_notifications():
    """Per-user notification preferences. v1 ships a single real
    toggle — trial-reminder emails — because that's the only sender
    (beyond password reset) we actually have today. The rest of the
    page is an honest catalog: what DineroBook sends you, and what
    you can control.

    Checkbox semantics: unchecked checkboxes don't appear in the POST
    body at all, so we always default the "trial reminder" pref to
    False on POST and flip it True only if the checkbox is present.
    """
    user = current_user()
    store = current_store()
    if request.method == "POST":
        user.notify_trial_reminders = bool(request.form.get("notify_trial_reminders"))
        user.notify_announcement_email = bool(request.form.get("notify_announcement_email"))
        db.session.commit()
        flash("Notification preferences saved.", "success")
        return redirect(url_for("account_notifications"))

    # "Does the trial-reminder toggle apply to me?" — only for
    # admins/owners of a store that's actually trialing today. For
    # employees + superadmin + paid stores the toggle is shown as
    # informational (greyed out with a note) rather than hidden, so
    # users understand the full preferences surface.
    trial_toggle_applies = bool(
        user.role in ("admin", "owner")
        and store is not None
        and get_trial_status(store) in ("active", "expiring_soon", "grace")
    )
    return render_template("account_notifications.html",
        user=user, store=store,
        trial_toggle_applies=trial_toggle_applies,
    )

@app.route("/login/passkey/begin", methods=["POST"])
def passkey_login_begin():
    """Discoverable-credential sign-in. No username needed — the browser
    asks the platform to pick one of the user's stored passkeys for
    this RP ID. The server just generates a challenge and lets the
    authenticator decide which credential to use."""
    options = generate_authentication_options(
        rp_id=_webauthn_rp_id(),
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    session["pk_login_challenge"] = bytes_to_base64url(options.challenge)
    return Response(options_to_json(options), mimetype="application/json")

@app.route("/login/passkey/finish", methods=["POST"])
def passkey_login_finish():
    challenge_b64 = session.pop("pk_login_challenge", None)
    if not challenge_b64:
        return jsonify({"ok": False,
                        "error": "No sign-in challenge in progress."}), 400
    body = request.get_json(silent=True) or {}
    credential = body.get("credential")
    if not credential:
        return jsonify({"ok": False, "error": "Missing credential."}), 400
    raw_cred_id_b64 = credential.get("rawId") or credential.get("id")
    if not raw_cred_id_b64:
        return jsonify({"ok": False, "error": "Invalid credential."}), 400
    try:
        cred_bytes = base64url_to_bytes(raw_cred_id_b64)
    except Exception:
        return jsonify({"ok": False, "error": "Invalid credential."}), 400
    pk = Passkey.query.filter_by(credential_id=cred_bytes).first()
    if not pk:
        return jsonify({"ok": False, "error": "Passkey not recognized."}), 400
    user = db.session.get(User, pk.user_id)
    if not user or not user.is_active:
        return jsonify({"ok": False, "error": "Account unavailable."}), 403
    try:
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(challenge_b64),
            expected_origin=_webauthn_origin(),
            expected_rp_id=_webauthn_rp_id(),
            credential_public_key=pk.public_key,
            credential_current_sign_count=pk.sign_count,
            require_user_verification=False,
        )
    except Exception:
        return jsonify({"ok": False,
                        "error": "Passkey verification failed."}), 400
    pk.sign_count = verification.new_sign_count
    pk.last_used_at = datetime.utcnow()
    _record_login(user)
    # Passkey IS MFA — skip the TOTP gate per the carve-out in CLAUDE.md
    # invariant #13. Clear any stale pending-auth too.
    session.pop("pending_auth_user_id", None)
    session.pop("totp_enrollment_codes", None)
    session["user_id"]  = user.id
    session["role"]     = user.role
    session["store_id"] = user.store_id
    db.session.commit()
    redirect_url = url_for("owner_dashboard") if user.role == "owner" else url_for("dashboard")
    return jsonify({"ok": True, "redirect": redirect_url})

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
_last_smtp_attempt = {
    "status": "unknown", "error": "", "when": None,
    "last_to_domain": "", "last_subject": "",
}

def _send_email(to_addr, subject, body, html=None):
    """Send a transactional email. Returns True on success, False on
    failure or when SMTP isn't configured. Every attempt updates
    _last_smtp_attempt so the superadmin health card can show the
    most recent outcome.

    When `html` is provided, the message is sent multipart/alternative
    so email clients that strip HTML (or users who prefer plain text)
    see `body`, and everyone else sees the rendered branded template.
    Keep both — plaintext fallback is a deliverability signal (spam
    filters flag HTML-only messages) and a real accessibility win.

    Env vars required: SMTP_HOST, SMTP_USER, SMTP_PASS. Optional: SMTP_PORT
    (default 587), SMTP_FROM (default SMTP_USER). When SMTP isn't configured
    the caller is expected to log enough context that a superadmin can
    retrieve the link manually.
    """
    global _last_smtp_attempt
    host = os.environ.get("SMTP_HOST")
    user = os.environ.get("SMTP_USER")
    pw   = os.environ.get("SMTP_PASS")
    now = datetime.utcnow()
    to_norm = (to_addr or "").strip().lower()
    to_domain = to_norm.split("@", 1)[1] if "@" in to_norm else ""
    # Bounce suppression: if a User row with this email got stamped by a
    # hard-bounce webhook, skip the send. Keeps us from hammering the
    # provider with guaranteed-failing addresses, which Resend (and every
    # other reputable provider) penalizes as a sender-reputation hit.
    # NOTE: we only skip when we can positively match to a User with the
    # stamp — superadmin test sends to personal addresses aren't gated.
    suppressed = (db.session.query(User.id)
                  .filter(db.func.lower(User.email) == to_norm,
                          User.email_bounced_at.isnot(None))
                  .first())
    if suppressed:
        _last_smtp_attempt = {
            "status": "suppressed",
            "error": f"{to_norm} is on the bounce suppression list",
            "when": now, "last_to_domain": to_domain, "last_subject": subject,
        }
        app.logger.warning(
            f"SMTP send suppressed (prior hard bounce) to *@{to_domain}")
        return False
    if not (host and user and pw):
        _last_smtp_attempt = {
            "status": "unconfigured", "error": "SMTP env vars not set",
            "when": now, "last_to_domain": to_domain, "last_subject": subject,
        }
        return False
    port = int(os.environ.get("SMTP_PORT", "587"))
    sender = os.environ.get("SMTP_FROM", user)
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")
    try:
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.starttls()
            s.login(user, pw)
            s.send_message(msg)
        _last_smtp_attempt = {
            "status": "sent", "error": "", "when": now,
            "last_to_domain": to_domain, "last_subject": subject,
        }
        return True
    except Exception as e:
        # Cheap type + message is enough for the superadmin to see whether
        # the auth creds are wrong, the host is unreachable, etc. — without
        # dumping a traceback into the HTML.
        err = f"{type(e).__name__}: {e}"
        app.logger.warning(f"SMTP send failed to {to_domain or '(no-to)'}: {err}")
        _last_smtp_attempt = {
            "status": "failed", "error": err, "when": now,
            "last_to_domain": to_domain, "last_subject": subject,
        }
        return False

def smtp_health_check():
    """Return a dict describing the email-delivery integration state,
    matching the shape of stripe_health_check so the template stays
    symmetric. Doesn't do a live SMTP probe — reads _last_smtp_attempt
    (updated on every _send_email call) and joins in delivery-event
    totals from EmailEvent (updated by the Resend webhook)."""
    env = {
        "host":     bool(os.environ.get("SMTP_HOST")),
        "user":     bool(os.environ.get("SMTP_USER")),
        "password": bool(os.environ.get("SMTP_PASS")),
        "from":     bool(os.environ.get("SMTP_FROM")),
        "webhook_secret": bool(os.environ.get("RESEND_WEBHOOK_SECRET")),
    }
    configured = env["host"] and env["user"] and env["password"]

    # Event totals over the last 7 days — a quick signal that:
    #   - the webhook is wired (any events at all)
    #   - bounce/complaint rate is under the ~2% Resend flags
    # Safe to run every Overview load; indexed on created_at.
    recent_events = {"delivered": 0, "bounced": 0, "complained": 0,
                     "sent": 0, "opened": 0, "clicked": 0}
    suppressed_count = 0
    last_event_at = None
    try:
        since = datetime.utcnow() - timedelta(days=7)
        rows = (db.session.query(EmailEvent.event_type, db.func.count(EmailEvent.id))
                .filter(EmailEvent.created_at >= since)
                .group_by(EmailEvent.event_type).all())
        for t, n in rows:
            # event_type comes in as "email.delivered" etc.
            key = t.split(".", 1)[-1] if "." in t else t
            if key in recent_events:
                recent_events[key] = n
        latest = (db.session.query(db.func.max(EmailEvent.created_at)).scalar())
        last_event_at = latest
        suppressed_count = User.query.filter(
            User.email_bounced_at.isnot(None)).count()
    except Exception:
        # EmailEvent / User columns may not exist on a pristine test DB
        # between migrations; don't blow up the Overview.
        pass

    return {
        "env":         env,
        "configured":  configured,
        "status":      _last_smtp_attempt["status"],
        "error":       _last_smtp_attempt["error"],
        "when":        _last_smtp_attempt["when"],
        "last_to_domain":  _last_smtp_attempt["last_to_domain"],
        "last_subject":    _last_smtp_attempt["last_subject"],
        "recent_events":   recent_events,
        "last_event_at":   last_event_at,
        "suppressed_count": suppressed_count,
    }

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Step 1 of the reset flow — generate a token for the supplied email.

    The response is deliberately the same whether the account exists or not,
    so attackers can't probe for registered emails. Employees aren't supported
    here; they should ask their store admin (admin_reset_employee_password).
    """
    sent = False
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        sent = True
        if username:
            # Superadmin is intentionally excluded: email-based reset would
            # be a 2FA bypass. Recovery is via `flask reset-superadmin` from
            # the Render shell. The response is still the "sent" message so
            # attackers can't tell a superadmin from a non-existent account.
            u = (User.query.filter_by(username=username)
                 .filter(User.role.in_(("admin", "owner")))
                 .first())
            if u and u.is_active:
                # Invalidate any still-valid tokens for this user, then mint fresh.
                now = datetime.utcnow()
                (PasswordResetToken.query
                 .filter(PasswordResetToken.user_id == u.id,
                         PasswordResetToken.used_at.is_(None),
                         PasswordResetToken.expires_at > now)
                 .update({"used_at": now}, synchronize_session=False))
                raw = secrets.token_urlsafe(48)
                db.session.add(PasswordResetToken(
                    user_id=u.id, token_hash=_hash_token(raw),
                    expires_at=now + timedelta(hours=PASSWORD_RESET_TTL_HOURS),
                ))
                db.session.commit()
                reset_url = url_for("reset_password", token=raw, _external=True)
                body = (
                    "Hi,\n\n"
                    "Someone (hopefully you) requested a password reset for your DineroBook "
                    "account. Follow this link within the next hour to set a new password:\n\n"
                    f"  {reset_url}\n\n"
                    "If you didn't request this you can safely ignore this email — your "
                    "current password will keep working.\n"
                )
                html = render_template(
                    "emails/password_reset.html",
                    preheader="Reset your DineroBook password — link expires in 1 hour.",
                    name=u.full_name or "",
                    reset_url=reset_url,
                    year=datetime.utcnow().year,
                    base_url=os.environ.get("APP_BASE_URL", "https://dinerobook.com"),
                )
                # Prefer the explicit email field (landed with /account/profile)
                # over the username. Username doubles as email for most admins
                # today, but owners often have a display username that isn't
                # an address — without this fallback their reset mail bounces.
                to_addr = (u.email or u.username).strip()
                delivered = _send_email(to_addr, "Reset your DineroBook password", body, html=html)
                if not delivered:
                    # No SMTP configured (or send failed): log the URL so the
                    # superadmin can retrieve it from the server logs and
                    # relay it to the user manually.
                    app.logger.warning(
                        f"[password-reset] email send skipped for {u.username}; "
                        f"reset URL: {reset_url}"
                    )
    return render_template("forgot_password.html", sent=sent)

@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    """Step 2 of the reset flow — verify the token and set the new password.

    Tokens are one-time-use and expire after PASSWORD_RESET_TTL_HOURS. We
    look them up by sha256 so the raw token never sits in the DB.
    """
    now = datetime.utcnow()
    row = (PasswordResetToken.query
           .filter_by(token_hash=_hash_token(token))
           .first())
    invalid = (row is None or row.used_at is not None or row.expires_at <= now)
    # Belt-and-suspenders: even if a token somehow exists for a superadmin
    # (it can't via /forgot-password today, but defense in depth), refuse
    # to honor it. Superadmin resets go through the Flask CLI.
    if row and not invalid:
        target = db.session.get(User, row.user_id)
        if target and target.role == "superadmin":
            invalid = True
    error = None
    if request.method == "POST" and not invalid:
        pw1 = request.form.get("password", "")
        pw2 = request.form.get("confirm_password", "")
        if len(pw1) < 8:
            error = "Password must be at least 8 characters."
        elif pw1 != pw2:
            error = "Passwords do not match."
        else:
            u = db.session.get(User, row.user_id)
            if u:
                u.set_password(pw1)
                row.used_at = now
                db.session.commit()
                flash("Password updated. You can now sign in with your new password.", "success")
                return redirect(url_for("login"))
            error = "Account no longer exists."
    return render_template("reset_password.html", invalid=invalid, error=error, token=token)

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if "user_id" in session and request.method == "GET":
        return redirect(url_for("dashboard"))
    errors = {}
    form = {}
    # Support both ?ref=CODE on GET (shared link) and a form field on POST
    # so the code survives if the page is reloaded after a validation error.
    ref_raw = (request.form.get("ref_code")
               or request.args.get("ref", "")).strip().upper()
    ref = lookup_referral_code(ref_raw) if ref_raw else None
    if request.method == "POST":
        store_name = request.form.get("store_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        phone = request.form.get("phone", "").strip()
        form = {"store_name": store_name, "email": email, "phone": phone,
                "ref_code": ref_raw}

        if not store_name:
            errors["store_name"] = "Store name is required."
        if not email:
            errors["email"] = "Email is required."
        if not password:
            errors["password"] = "Password is required."
        elif len(password) < 8:
            errors["password"] = "Password must be at least 8 characters."
        # A code that was typed / pasted but doesn't match any active one:
        # don't hard-fail — that's a bad UX for a nice-to-have. We silently
        # drop it and continue. The warning surface is the template's green
        # banner only appearing when the code resolved.
        if ref_raw and not ref:
            app.logger.info(f"signup: invalid ref code '{ref_raw}' ignored")

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
            if ref:
                s.referred_by_code_id = ref.id
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
            if ref:
                flash(f"Welcome! You'll get ${ref.reward_referee_cents/100:.0f} "
                      "off your first paid month when you subscribe.", "success")
            else:
                flash("Welcome! Your 7-day free trial has started.", "success")
            return redirect(url_for("dashboard"))

    return render_template("signup.html", errors=errors, form=form,
                           referral=ref, ref_code_raw=ref_raw)

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

# ── Owner-side helpers ──────────────────────────────────────────
#
# Owners read across many stores at once and want the same depth of BI
# the superadmin has, scoped to their umbrella. The helpers below carry
# the heavy lifting; the routes below just wire them to templates.
#
# Period selector vocabulary (today / month / year) matches the existing
# UI; "previous-period" windows are the same length, ending the day
# before the current window — that's what the delta badges compare to.

_OWNER_TRANSFER_EXCLUDED = ["Canceled", "Rejected"]

def _owner_period_window(period, today):
    """Map a `today|month|year` selector to current + prior windows.

    Returns (start, end, prev_start, prev_end, prev_label). The prior
    window has the same number of days as the current and ends the day
    before the current one starts, so KPI deltas are like-for-like.
    """
    if period == "month":
        start = today.replace(day=1)
        end = today
        days = (end - start).days
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=days)
        return start, end, prev_start, prev_end, "vs prior month"
    if period == "year":
        start = date(today.year, 1, 1)
        end = today
        days = (end - start).days
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=days)
        return start, end, prev_start, prev_end, "vs prior year"
    # default: today
    return today, today, today - timedelta(days=1), today - timedelta(days=1), "vs yesterday"


def _owner_store_ids(user):
    """Store IDs the given owner is linked to. Empty if none."""
    links = StoreOwnerLink.query.filter_by(owner_id=user.id).all()
    return [l.store_id for l in links]


def _owner_kpis(store_ids, start, end):
    """Aggregate (transfer_count, volume, over_short) across the given
    stores and date window. Excludes canceled/rejected transfers."""
    if not store_ids:
        return 0, 0.0, 0.0
    tx_count = Transfer.query.filter(
        Transfer.store_id.in_(store_ids),
        Transfer.send_date >= start, Transfer.send_date <= end,
        Transfer.status.notin_(_OWNER_TRANSFER_EXCLUDED),
    ).count()
    vol = db.session.query(db.func.coalesce(db.func.sum(Transfer.send_amount), 0.0)).filter(
        Transfer.store_id.in_(store_ids),
        Transfer.send_date >= start, Transfer.send_date <= end,
        Transfer.status.notin_(_OWNER_TRANSFER_EXCLUDED),
    ).scalar() or 0.0
    os_total = db.session.query(db.func.coalesce(db.func.sum(DailyReport.over_short), 0.0)).filter(
        DailyReport.store_id.in_(store_ids),
        DailyReport.report_date >= start, DailyReport.report_date <= end,
    ).scalar() or 0.0
    return int(tx_count), float(vol), float(os_total)


def _owner_dashboard_context(user, period):
    """Rich metrics for /owner/dashboard.

    Mirrors the superadmin dashboard pattern: KPI cards with prior-period
    deltas, a 30-day daily volume area chart (always 30d so the trend
    shape is independent of the selector), per-company donut for the
    selected window, and a per-store volume comparison bar.
    """
    today = date.today()
    start, end, prev_start, prev_end, prev_label = _owner_period_window(period, today)
    store_ids = _owner_store_ids(user)
    stores = (Store.query.filter(Store.id.in_(store_ids)).order_by(Store.name).all()
              if store_ids else [])

    agg_transfers, agg_volume, agg_over_short = _owner_kpis(store_ids, start, end)
    prev_transfers, prev_volume, prev_over_short = _owner_kpis(store_ids, prev_start, prev_end)

    # 30-day daily volume series — fixed window, used for the area chart.
    d30_ago = today - timedelta(days=29)
    daily_rows = (db.session.query(
        Transfer.send_date,
        db.func.count(Transfer.id),
        db.func.coalesce(db.func.sum(Transfer.send_amount), 0.0),
    ).filter(
        Transfer.store_id.in_(store_ids),
        Transfer.send_date >= d30_ago, Transfer.send_date <= today,
        Transfer.status.notin_(_OWNER_TRANSFER_EXCLUDED),
    ).group_by(Transfer.send_date).all() if store_ids else [])
    by_day_vol = {d: float(v or 0) for d, _c, v in daily_rows}
    by_day_cnt = {d: int(c or 0) for d, c, _v in daily_rows}
    series_labels, series_volume, series_count = [], [], []
    for i in range(29, -1, -1):
        d = today - timedelta(days=i)
        series_labels.append(d.isoformat())
        series_volume.append(round(by_day_vol.get(d, 0.0), 2))
        series_count.append(by_day_cnt.get(d, 0))

    # Per-company breakdown for the selected period.
    co_rows = (db.session.query(
        Transfer.company,
        db.func.count(Transfer.id),
        db.func.coalesce(db.func.sum(Transfer.send_amount), 0.0),
        db.func.coalesce(db.func.sum(Transfer.fee), 0.0),
    ).filter(
        Transfer.store_id.in_(store_ids),
        Transfer.send_date >= start, Transfer.send_date <= end,
        Transfer.status.notin_(_OWNER_TRANSFER_EXCLUDED),
    ).group_by(Transfer.company).order_by(
        db.func.coalesce(db.func.sum(Transfer.send_amount), 0.0).desc()
    ).all() if store_ids else [])
    company_breakdown = [
        {"company": (co or "—"), "count": int(cnt),
         "volume": float(v or 0), "fees": float(f or 0)}
        for co, cnt, v, f in co_rows
    ]

    # Per-store volume comparison for the selected period.
    store_rows = (db.session.query(
        Transfer.store_id,
        db.func.count(Transfer.id),
        db.func.coalesce(db.func.sum(Transfer.send_amount), 0.0),
    ).filter(
        Transfer.store_id.in_(store_ids),
        Transfer.send_date >= start, Transfer.send_date <= end,
        Transfer.status.notin_(_OWNER_TRANSFER_EXCLUDED),
    ).group_by(Transfer.store_id).all() if store_ids else [])
    store_stat = {sid: (int(c), float(v or 0)) for sid, c, v in store_rows}
    store_comparison = []
    for s in stores:
        c, v = store_stat.get(s.id, (0, 0.0))
        store_comparison.append({"id": s.id, "name": s.name, "count": c, "volume": v})
    store_comparison.sort(key=lambda x: x["volume"], reverse=True)

    # Return-check rollups across the owner's whole umbrella. Owner
    # cares about: outstanding pending balance, period recoveries
    # vs. losses, aging buckets (chase candidates), and a 12-month
    # bar chart of recoveries vs losses+fraud.
    rc_period = _return_check_period_aggregates(store_ids, start, end)
    rc_aging = _return_check_aging_buckets(store_ids, today=today)
    rc_labels, rc_recoveries, rc_losses = _return_check_monthly_series(
        store_ids, today=today)

    return dict(
        user=user, period=period, prev_label=prev_label,
        period_start=start, period_end=end,
        store_count=len(stores), stores=stores,
        agg_transfers=agg_transfers, agg_volume=agg_volume,
        agg_over_short=agg_over_short,
        agg_transfers_delta=agg_transfers - prev_transfers,
        agg_volume_delta=agg_volume - prev_volume,
        agg_over_short_delta=agg_over_short - prev_over_short,
        series_labels=series_labels, series_volume=series_volume,
        series_count=series_count,
        company_breakdown=company_breakdown,
        store_comparison=store_comparison,
        rc_period=rc_period, rc_aging=rc_aging,
        rc_labels=rc_labels, rc_recoveries=rc_recoveries,
        rc_losses=rc_losses,
    )


def _owner_locations_payload(user, period, query):
    """Per-store rows for /owner/locations.

    Each row has the basic period-scoped stats (transfers, volume,
    over/short) plus a per-company chip list so the owner sees provider
    mix at a glance without drilling in. `query` is a substring matched
    case-insensitively against store name.
    """
    today = date.today()
    start, end, *_ = _owner_period_window(period, today)
    store_ids = _owner_store_ids(user)
    if not store_ids:
        return [], 0

    base_q = Store.query.filter(Store.id.in_(store_ids))
    if query:
        ql = "%{}%".format(query.lower())
        base_q = base_q.filter(db.func.lower(Store.name).like(ql))
    stores = base_q.order_by(Store.name).all()
    if not stores:
        return [], len(store_ids)

    visible_ids = [s.id for s in stores]

    transfer_rows = db.session.query(
        Transfer.store_id,
        db.func.count(Transfer.id),
        db.func.coalesce(db.func.sum(Transfer.send_amount), 0.0),
    ).filter(
        Transfer.store_id.in_(visible_ids),
        Transfer.send_date >= start, Transfer.send_date <= end,
        Transfer.status.notin_(_OWNER_TRANSFER_EXCLUDED),
    ).group_by(Transfer.store_id).all()
    transfer_stat = {sid: (int(c), float(v or 0)) for sid, c, v in transfer_rows}

    daily_rows = db.session.query(
        DailyReport.store_id,
        db.func.coalesce(db.func.sum(DailyReport.over_short), 0.0),
        db.func.count(DailyReport.id),
    ).filter(
        DailyReport.store_id.in_(visible_ids),
        DailyReport.report_date >= start, DailyReport.report_date <= end,
    ).group_by(DailyReport.store_id).all()
    daily_stat = {sid: (float(os_v or 0), int(rc or 0)) for sid, os_v, rc in daily_rows}

    # Per-store, per-company chips (small, ≤ 6 each in practice).
    co_rows = db.session.query(
        Transfer.store_id, Transfer.company,
        db.func.count(Transfer.id),
        db.func.coalesce(db.func.sum(Transfer.send_amount), 0.0),
    ).filter(
        Transfer.store_id.in_(visible_ids),
        Transfer.send_date >= start, Transfer.send_date <= end,
        Transfer.status.notin_(_OWNER_TRANSFER_EXCLUDED),
    ).group_by(Transfer.store_id, Transfer.company).all()
    co_by_store = {}
    for sid, co, c, v in co_rows:
        co_by_store.setdefault(sid, []).append({
            "company": (co or "—"), "count": int(c), "volume": float(v or 0),
        })
    for sid in co_by_store:
        co_by_store[sid].sort(key=lambda x: x["volume"], reverse=True)

    rows = []
    for s in stores:
        c, v = transfer_stat.get(s.id, (0, 0.0))
        os_v, rc = daily_stat.get(s.id, (0.0, 0))
        rows.append({
            "store": s,
            "transfer_count": c,
            "volume": v,
            "over_short": os_v,
            "report_count": rc,
            "companies": co_by_store.get(s.id, []),
        })
    return rows, len(store_ids)


@app.route("/owner/dashboard")
@owner_required
def owner_dashboard():
    u = current_user()
    period = request.args.get("period", "month")
    if period not in ("today", "month", "year"):
        period = "month"
    return render_template("owner_dashboard.html",
                           **_owner_dashboard_context(u, period))


@app.route("/owner/locations")
@owner_required
def owner_locations():
    """Searchable list of stores the owner is linked to.

    Supports `?partial=1` for the live-search AJAX swap pattern (same
    contract as /transfers): returns JSON `{html, total, query}` and
    the page-level template wraps the partial in a stable swap container.
    """
    u = current_user()
    period = request.args.get("period", "month")
    if period not in ("today", "month", "year"):
        period = "month"
    query = (request.args.get("q") or "").strip()
    rows, total = _owner_locations_payload(u, period, query)
    if request.args.get("partial") == "1":
        html = render_template("_owner_locations_table.html",
                               rows=rows, period=period, query=query)
        return jsonify({"html": html, "total": total,
                        "matched": len(rows), "query": query})
    return render_template("owner_locations.html",
                           user=u, period=period, query=query,
                           rows=rows, total=total)


@app.route("/owner/store/<int:store_id>")
@owner_required
def owner_store_detail(store_id):
    """Drill-down view for a single store the owner is linked to.

    Read-only — owner can't edit transfers/reports here, only inspect.
    Access is gated on StoreOwnerLink so an owner can't poke at a
    store they don't own by guessing IDs.
    """
    u = current_user()
    link = StoreOwnerLink.query.filter_by(owner_id=u.id, store_id=store_id).first()
    if not link:
        flash("That store is not linked to your account.", "error")
        return redirect(url_for("owner_locations"))
    period = request.args.get("period", "month")
    if period not in ("today", "month", "year"):
        period = "month"
    today = date.today()
    start, end, prev_start, prev_end, prev_label = _owner_period_window(period, today)
    store = db.session.get(Store, store_id)

    co_rows = db.session.query(
        Transfer.company,
        db.func.count(Transfer.id),
        db.func.coalesce(db.func.sum(Transfer.send_amount), 0.0),
        db.func.coalesce(db.func.sum(Transfer.fee), 0.0),
        db.func.coalesce(db.func.sum(Transfer.federal_tax), 0.0),
    ).filter(
        Transfer.store_id == store_id,
        Transfer.send_date >= start, Transfer.send_date <= end,
        Transfer.status.notin_(_OWNER_TRANSFER_EXCLUDED),
    ).group_by(Transfer.company).order_by(
        db.func.coalesce(db.func.sum(Transfer.send_amount), 0.0).desc()
    ).all()
    company_rows = [
        {"company": (co or "—"), "count": int(c),
         "volume": float(v or 0), "fees": float(f or 0), "tax": float(t or 0)}
        for co, c, v, f, t in co_rows
    ]
    period_count = sum(r["count"] for r in company_rows)
    period_volume = sum(r["volume"] for r in company_rows)
    period_fees = sum(r["fees"] for r in company_rows)
    period_tax = sum(r["tax"] for r in company_rows)

    prev_count, prev_volume, _ = _owner_kpis([store_id], prev_start, prev_end)

    # 30-day over/short trend, fixed window — independent of selector.
    d30_ago = today - timedelta(days=29)
    daily_reports = DailyReport.query.filter(
        DailyReport.store_id == store_id,
        DailyReport.report_date >= d30_ago,
        DailyReport.report_date <= today,
    ).all()
    by_day = {r.report_date: r for r in daily_reports}
    daily_labels, over_short_data, receipts_data = [], [], []
    for i in range(29, -1, -1):
        d = today - timedelta(days=i)
        r = by_day.get(d)
        daily_labels.append(d.isoformat())
        over_short_data.append(round(float(r.over_short) if r else 0.0, 2))
        receipts_data.append(round(float(r.total_receipts) if r else 0.0, 2))

    # Recent activity for context.
    recent_transfers = (Transfer.query.filter_by(store_id=store_id)
                        .order_by(Transfer.created_at.desc()).limit(10).all())

    period_over_short = db.session.query(
        db.func.coalesce(db.func.sum(DailyReport.over_short), 0.0)
    ).filter(
        DailyReport.store_id == store_id,
        DailyReport.report_date >= start, DailyReport.report_date <= end,
    ).scalar() or 0.0

    return render_template("owner_store_detail.html",
        user=u, store=store, period=period, prev_label=prev_label,
        period_start=start, period_end=end,
        company_rows=company_rows,
        period_count=period_count, period_volume=period_volume,
        period_fees=period_fees, period_tax=period_tax,
        period_over_short=float(period_over_short),
        prev_count=prev_count, prev_volume=prev_volume,
        daily_labels=daily_labels,
        over_short_data=over_short_data, receipts_data=receipts_data,
        recent_transfers=recent_transfers,
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
    # Yearly buttons show up on the pricing page only if their price ID
    # is configured in the environment — otherwise a user clicking them
    # would just get bounced back with "Invalid plan selected."
    prices = _stripe_price_ids()
    return render_template("subscribe.html", user=user, store=store,
        basic_yearly_enabled=bool(prices["basic_yearly"]),
        pro_yearly_enabled=bool(prices["pro_yearly"]))

@app.route("/subscribe/checkout", methods=["POST"])
@login_required
def subscribe_checkout():
    """Create a Stripe Checkout Session for the chosen plan and redirect there.

    The webhook (checkout.session.completed) is what actually flips the store
    onto the new plan — this route only initiates the payment flow.
    """
    store = current_store()
    plan = request.form.get("plan", "").strip()
    # "_yearly" variants are separate Stripe prices but land on the same
    # Store.plan value — basic_yearly→"basic", pro_yearly→"pro" — because
    # Store.plan is about feature entitlement, not billing cadence.
    price_map = _stripe_price_ids()
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

# ── Referrals (store-admin to new-store share + earn) ───────
@app.route("/account/referrals")
@admin_required
def admin_referrals():
    """Self-service view of the admin's own referral code + stats.

    Paid plans only — the crown in the topbar is hidden on trial and the
    webhook mints the code at the paid transition. If somehow a paid
    admin arrives here without a code (e.g. they subscribed before this
    feature shipped), lazily mint on the fly.
    """
    user  = current_user()
    store = current_store()
    if not store_has_paid_plan(store):
        flash("Referrals unlock when your subscription is active.", "error")
        return redirect(url_for("admin_subscription"))
    rc = ensure_referral_code(store)
    db.session.commit()
    # Stats: total redemptions + total credits earned (from the history).
    redemptions = (ReferralRedemption.query
                   .filter_by(referral_code_id=rc.id)
                   .order_by(ReferralRedemption.redeemed_at.desc())
                   .all())
    credits_earned_cents = sum(
        rc.reward_self_cents for r in redemptions if r.self_credit_applied_at
    )
    share_url = url_for("signup", ref=rc.code, _external=True)
    return render_template("admin_referrals.html",
        user=user, store=store,
        referral=rc, redemptions=redemptions,
        credits_earned_cents=credits_earned_cents,
        share_url=share_url,
    )

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
    plan_prices = {"basic": "$35 / month", "pro": "$45 / month"}
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

def _open_billing_portal(store, error_msg, log_label="billing portal"):
    """Open the Stripe Customer Portal for `store` and 303-redirect there.

    On failure, flashes `error_msg` and redirects back to
    /admin/subscription. Centralizes the Stripe boilerplate that the
    portal-open and the cancel-via-portal routes used to duplicate
    line for line — the only thing that varies is which error
    message + log label to show when Stripe fails.

    Returns a Flask response. Caller is responsible for the
    pre-checks (does the store have a Stripe customer id, is the
    plan paid, etc.) so this helper stays single-purpose.
    """
    try:
        portal = stripe.billing_portal.Session.create(
            customer=store.stripe_customer_id,
            return_url=url_for("admin_subscription", _external=True),
        )
        return redirect(portal.url, code=303)
    except stripe.error.StripeError as e:
        app.logger.error(f"Stripe {log_label} error: {e}")
        flash(error_msg, "error")
        return redirect(url_for("admin_subscription"))


@app.route("/admin/subscription/billing-portal", methods=["POST"])
@admin_required
def admin_subscription_billing_portal():
    store = current_store()
    if not store or not store.stripe_customer_id:
        flash("No billing account found. Choose a plan to get started.", "error")
        return redirect(url_for("subscribe"))
    return _open_billing_portal(
        store,
        error_msg="Could not open billing portal. Please try again.",
        log_label="billing portal")


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
    return _open_billing_portal(
        store,
        error_msg="Could not open the cancellation page. Please try again.",
        log_label="billing portal (cancel)")

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
    # Toggle the addon key in/out of the CSV. Stripe billing for the
    # subscription item is handled separately (see BACKLOG); for now
    # this gives the pilot store immediate access to the feature, and
    # the "real money" wiring can land once we've validated the UX.
    keys = store_addon_keys(store)
    if addon_key in keys:
        keys.discard(addon_key)
        flash(f"{addon['name']} turned off.", "success")
    else:
        keys.add(addon_key)
        flash(f"{addon['name']} is now active. Set up your display →", "success")
    store.addons = ",".join(sorted(keys))
    db.session.commit()
    # When a feature has a dedicated dashboard, drop the user there
    # right after activating so they don't have to hunt for it.
    if addon_key == "tv_display" and addon_key in keys:
        return redirect(url_for("admin_tv_display"))
    return redirect(url_for("admin_subscription"))

def store_has_addon(store, addon_key):
    """Single predicate every gated route uses, so future Stripe-driven
    `customer.subscription.updated` syncs flip every gated surface in
    one shot."""
    return addon_key in store_addon_keys(store)

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
        return redirect(url_for("admin_subscription"))
    return (user, store)

def _ensure_tv_display(store):
    """Get-or-create the store's TVDisplay row + initial token."""
    d = TVDisplay.query.filter_by(store_id=store.id).first()
    if d is None:
        d = TVDisplay(store_id=store.id,
                       public_token=secrets.token_urlsafe(24))
        db.session.add(d); db.session.commit()
    return d

def _csv_split(s):
    return [x.strip() for x in (s or "").split(",") if x.strip()]

@app.route("/tv-display")
@login_required
def admin_tv_display():
    """Landing page for the TV display add-on. Lists country sections,
    surfaces the public-display link + token-rotate action, and
    deep-links into the per-country edit page."""
    guard = _tv_required()
    if not isinstance(guard, tuple):
        return guard
    user, store = guard
    display = _ensure_tv_display(store)
    countries = (TVDisplayCountry.query
                  .filter_by(display_id=display.id)
                  .order_by(TVDisplayCountry.sort_order, TVDisplayCountry.id).all())
    # Quick stats per country so the index is useful at a glance.
    country_stats = {}
    for c in countries:
        bank_count = TVDisplayPayoutBank.query.filter_by(country_id=c.id).count()
        rate_count = (db.session.query(TVDisplayRate)
                       .join(TVDisplayPayoutBank,
                             TVDisplayRate.bank_id == TVDisplayPayoutBank.id)
                       .filter(TVDisplayPayoutBank.country_id == c.id).count())
        country_stats[c.id] = {"banks": bank_count, "rates": rate_count}
    public_url = url_for("tv_public_display", token=display.public_token,
                          _external=True)
    # Active Fire TV pairing for the "Currently paired" pill on the
    # admin landing. None when no Fire TV has paired (or all prior
    # pairings have been revoked / superseded).
    active_pairing = (TVPairing.query
                       .filter_by(display_id=display.id, revoked_at=None)
                       .order_by(TVPairing.paired_at.desc())
                       .first())
    return render_template("tv_display_admin.html",
                            user=user, store=store, display=display,
                            countries=countries, country_stats=country_stats,
                            public_url=public_url,
                            active_pairing=active_pairing,
                            country_picker=_TV_COUNTRY_PICKER)

@app.route("/tv-display/pairings/<int:pairing_id>/revoke", methods=["POST"])
@login_required
def tv_display_revoke_pairing(pairing_id):
    """Manually revoke a paired Fire TV (e.g. operator replaced it,
    lost it, decommissioned it). Sets revoked_at = now; the device's
    URL 404s on next refresh."""
    guard = _tv_required()
    if not isinstance(guard, tuple):
        return guard
    _, store = guard
    display = _ensure_tv_display(store)
    pairing = TVPairing.query.filter_by(
        id=pairing_id, display_id=display.id).first_or_404()
    if pairing.revoked_at is None:
        pairing.revoked_at = datetime.utcnow()
        db.session.commit()
        flash("Fire TV unpaired. The device will stop showing the board on its next refresh.",
              "success")
    return redirect(url_for("admin_tv_display"))

@app.route("/tv-display/settings", methods=["POST"])
@login_required
def tv_display_save_settings():
    guard = _tv_required()
    if not isinstance(guard, tuple):
        return guard
    _, store = guard
    display = _ensure_tv_display(store)
    display.title = (request.form.get("title") or "").strip()[:120] or "Cheapest Money Transfer"
    display.subtitle = (request.form.get("subtitle") or "").strip()[:120]
    orient = (request.form.get("orientation") or "auto").strip()
    if orient not in ("auto", "landscape", "portrait"):
        orient = "auto"
    display.orientation = orient
    theme = (request.form.get("theme") or "light").strip()
    if theme not in ("light", "dark"):
        theme = "light"
    display.theme = theme
    display.last_updated_at = datetime.utcnow()
    db.session.commit()
    flash("Display settings saved.", "success")
    return redirect(url_for("admin_tv_display"))

@app.route("/tv-display/regenerate-token", methods=["POST"])
@login_required
def tv_display_regenerate_token():
    """Rotate the public token. Anyone holding the old URL stops
    seeing the board on the next page load."""
    guard = _tv_required()
    if not isinstance(guard, tuple):
        return guard
    _, store = guard
    display = _ensure_tv_display(store)
    display.public_token = secrets.token_urlsafe(24)
    db.session.commit()
    flash("Display URL regenerated. Update any TV pointing at the old link.",
          "success")
    return redirect(url_for("admin_tv_display"))

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
        if (not TVPairing.query.filter_by(device_token=t).first()
                and not TVPendingPair.query.filter_by(device_token=t).first()):
            return t
    # All 8 collided — implausible but raise rather than silently
    # reuse a token.
    raise RuntimeError("Could not mint a unique device_token")

@app.route("/api/tv-pair/init", methods=["POST"])
def tv_pair_init():
    """The Fire TV app calls this on launch. Creates a TVPendingPair
    with a fresh code + device_token and returns both. The app
    displays the code on screen and polls /api/tv-pair/status with
    its device_token until claimed.

    No auth — anyone with the app can request a code; the addon
    gate sits on /tv-display/claim where the admin binds the code
    to a paying store."""
    payload = request.get_json(silent=True) or {}
    device_label = (payload.get("device_label") or "").strip()[:80]

    # Loop on code collision (rare with a 387M space, free to retry).
    for _ in range(8):
        code = _generate_pair_code()
        if not TVPendingPair.query.filter_by(code=code).first():
            break

    now = datetime.utcnow()
    pending = TVPendingPair(
        code=code,
        device_token=_generate_device_token(),
        device_label=device_label,
        created_at=now,
        expires_at=now + _PAIR_CODE_LIFETIME,
    )
    db.session.add(pending)
    db.session.commit()

    return jsonify({
        "code":         pending.code,
        "device_token": pending.device_token,
        "expires_at":   pending.expires_at.isoformat() + "Z",
        "ttl_seconds":  int(_PAIR_CODE_LIFETIME.total_seconds()),
    })

@app.route("/api/tv-pair/status", methods=["GET"])
def tv_pair_status():
    """The Fire TV polls this with its device_token. Returns one of:
       200 {status: "pending", code, ttl_seconds}    — code still on screen, waiting
       200 {status: "claimed", display_url, ...}     — operator claimed it; load the URL
       200 {status: "expired"}                       — code expired; app should call /init again

    Always 200 so the Fire TV can branch off the JSON. Unknown
    tokens get treated as "expired" so a fresh /init is the
    recovery path; that's a stronger UX guarantee than 404'ing the
    whole poll loop."""
    token = (request.args.get("token") or "").strip()
    if not token:
        return jsonify({"status": "expired"}), 200

    # Did this token already get claimed (i.e. there's a TVPairing
    # row keyed by it)? If so, return claimed regardless of pending
    # state — claim cleanup may not have run yet.
    pairing = TVPairing.query.filter_by(
        device_token=token, revoked_at=None).first()
    if pairing is not None:
        display = db.session.get(TVDisplay, pairing.display_id)
        store = db.session.get(Store, display.store_id) if display else None
        if (display and store and store_has_addon(store, "tv_display")):
            display_url = url_for("tv_device_display", device_token=token,
                                   _external=True)
            return jsonify({
                "status":      "claimed",
                "display_url": display_url,
                "store_name":  store.name,
                "title":       display.title or "Money Transfer Rates",
            }), 200
        # Pairing exists but addon is gone — same as expired from
        # the app's POV; it should re-init.
        return jsonify({"status": "expired"}), 200

    pending = TVPendingPair.query.filter_by(device_token=token).first()
    if not pending:
        return jsonify({"status": "expired"}), 200
    if pending.expires_at < datetime.utcnow():
        return jsonify({"status": "expired"}), 200
    if pending.claimed_at is not None:
        # Pending row was claimed but the resulting TVPairing was
        # already revoked (someone paired a newer Fire TV with the
        # same backing token? unlikely but possible) or the addon
        # was yanked between claim and poll. Treat as expired so
        # the Fire TV re-inits.
        return jsonify({"status": "expired"}), 200
    # Still pending. Return the code so the Fire TV can re-display
    # it after a process death / config change without losing the
    # bound code.
    ttl = int((pending.expires_at - datetime.utcnow()).total_seconds())
    return jsonify({
        "status":       "pending",
        "code":         pending.code,
        "ttl_seconds":  max(0, ttl),
    }), 200

@app.route("/tv-display/claim", methods=["POST"])
@login_required
def tv_display_claim():
    """Admin enters a 6-char code from a Fire TV showing the pairing
    screen. Server validates the code is live and not yet claimed,
    revokes any prior active TVPairing on this store's display, then
    creates a fresh TVPairing reusing the device_token from the
    pending row.

    Failure modes (all flash + redirect, none reveal whether the
    code exists):
      - missing/short code              → "Enter the 6-character code…"
      - unknown code                    → "Code not found or expired."
      - expired code                    → "Code not found or expired."
      - already claimed                 → "Code not found or expired."
    """
    guard = _tv_required()
    if not isinstance(guard, tuple):
        return guard
    _, store = guard
    display = _ensure_tv_display(store)

    raw = (request.form.get("code") or "").strip().upper()
    code = "".join(c for c in raw if c in _PAIR_CODE_ALPHABET)
    if len(code) != 6:
        flash("Enter the 6-character code shown on your Fire TV.", "error")
        return redirect(url_for("admin_tv_display"))

    pending = TVPendingPair.query.filter_by(code=code).first()
    if (not pending
            or pending.claimed_at is not None
            or pending.expires_at < datetime.utcnow()):
        flash("Code not found or expired. Generate a fresh code on the Fire TV and try again.",
              "error")
        return redirect(url_for("admin_tv_display"))

    # Revoke any prior active pairing on this display. One Fire TV
    # at a time per subscription.
    now = datetime.utcnow()
    TVPairing.query.filter(
        TVPairing.display_id == display.id,
        TVPairing.revoked_at.is_(None),
    ).update({"revoked_at": now}, synchronize_session=False)

    # Create the new pairing, reusing the device_token the Fire TV
    # already holds — fewer moving parts on the client.
    pairing = TVPairing(
        display_id=display.id,
        device_token=pending.device_token,
        device_label=pending.device_label,
        paired_at=now,
        last_seen_at=now,
    )
    db.session.add(pairing)
    db.session.flush()  # need pairing.id before linking the pending row

    pending.claimed_at = now
    pending.claimed_pairing_id = pairing.id
    display.last_updated_at = now
    db.session.commit()

    flash("Fire TV paired. The screen will switch to the rate board within a few seconds.",
          "success")
    return redirect(url_for("admin_tv_display"))

@app.route("/tv-display/countries/new", methods=["POST"])
@login_required
def tv_display_country_new():
    guard = _tv_required()
    if not isinstance(guard, tuple):
        return guard
    _, store = guard
    display = _ensure_tv_display(store)
    name = (request.form.get("country_name") or "").strip()[:80]
    code = (request.form.get("country_code") or "").strip().upper()[:4]
    if not name:
        flash("Country name is required.", "error")
        return redirect(url_for("admin_tv_display"))
    # Default sort_order = max + 10 so manual reordering has room.
    last = (db.session.query(db.func.max(TVDisplayCountry.sort_order))
             .filter_by(display_id=display.id).scalar() or 0)
    c = TVDisplayCountry(display_id=display.id, country_code=code,
                          country_name=name, sort_order=last + 10,
                          mt_companies=(request.form.get("mt_companies") or "").strip()[:500])
    db.session.add(c); db.session.commit()
    display.last_updated_at = datetime.utcnow(); db.session.commit()
    flash(f"Added {name}. Now add payout banks and rates.", "success")
    return redirect(url_for("tv_display_country_edit", country_id=c.id))

@app.route("/tv-display/countries/<int:country_id>", methods=["GET", "POST"])
@login_required
def tv_display_country_edit(country_id):
    guard = _tv_required()
    if not isinstance(guard, tuple):
        return guard
    _, store = guard
    display = _ensure_tv_display(store)
    country = TVDisplayCountry.query.filter_by(
        id=country_id, display_id=display.id).first_or_404()

    if request.method == "POST":
        # Single big form holds:
        #   - country header fields (name, code, mt_companies CSV)
        #   - the bank list (existing rows + optional "new bank")
        #   - the rate matrix (one input per cell, named "rate-<bank_id>-<col_idx>")
        # Rates that come back blank delete the cell entirely so admins
        # can clear a value by emptying the box.
        country.country_name = (request.form.get("country_name") or country.country_name).strip()[:80]
        country.country_code = (request.form.get("country_code") or "").strip().upper()[:4]
        new_companies = (request.form.get("mt_companies") or "").strip()[:500]
        country.mt_companies = new_companies
        companies = _csv_split(new_companies)

        # Update existing banks (by id), drop ones flagged delete=1,
        # and append a single new bank if the form supplies one.
        for b in TVDisplayPayoutBank.query.filter_by(country_id=country.id).all():
            if request.form.get(f"bank-{b.id}-delete"):
                # Cascade-delete the cells under this bank too.
                TVDisplayRate.query.filter_by(bank_id=b.id).delete(
                    synchronize_session=False)
                db.session.delete(b)
                continue
            new_name = (request.form.get(f"bank-{b.id}-name") or "").strip()[:120]
            if new_name:
                b.bank_name = new_name
            try:
                b.sort_order = int(request.form.get(f"bank-{b.id}-sort") or 0)
            except ValueError:
                pass
        # Accept one or many new banks in a single POST — the grid
        # editor exposes "+ Insert row" which can be tapped multiple
        # times before the operator hits Save. Backwards compatible:
        # form.getlist returns ["x"] for a single new_bank_name=x and
        # [] when the field is absent.
        new_bank_names = [
            (n or "").strip()[:120]
            for n in request.form.getlist("new_bank_name")
            if (n or "").strip()
        ]
        if new_bank_names:
            last = (db.session.query(db.func.max(TVDisplayPayoutBank.sort_order))
                     .filter_by(country_id=country.id).scalar() or 0)
            for offset, name in enumerate(new_bank_names, start=1):
                db.session.add(TVDisplayPayoutBank(
                    country_id=country.id, bank_name=name,
                    sort_order=last + 10 * offset))
        db.session.commit()

        # Now upsert the rate matrix. After the bank deletes/adds above
        # we re-query so the form can include cells for both old and
        # newly created banks.
        banks = (TVDisplayPayoutBank.query
                  .filter_by(country_id=country.id)
                  .order_by(TVDisplayPayoutBank.sort_order, TVDisplayPayoutBank.id).all())
        for b in banks:
            for idx, company in enumerate(companies):
                key = f"rate-{b.id}-{idx}"
                raw = (request.form.get(key) or "").strip()
                existing = TVDisplayRate.query.filter_by(
                    bank_id=b.id, mt_company=company).first()
                if not raw:
                    if existing:
                        db.session.delete(existing)
                    continue
                try:
                    val = float(raw)
                except ValueError:
                    continue
                if existing:
                    existing.rate = val
                else:
                    db.session.add(TVDisplayRate(
                        bank_id=b.id, mt_company=company, rate=val))
        # Drop any orphan rates whose mt_company isn't in the current
        # column list (admin removed a column). Use a subquery on
        # bank_id rather than .join().delete(), which SQLAlchemy
        # explicitly doesn't allow on bulk deletes.
        bank_ids_subq = db.session.query(TVDisplayPayoutBank.id).filter_by(
            country_id=country.id)
        if companies:
            (TVDisplayRate.query
             .filter(TVDisplayRate.bank_id.in_(bank_ids_subq),
                     ~TVDisplayRate.mt_company.in_(companies))
             .delete(synchronize_session=False))
        else:
            # No columns at all — wipe every rate for this country.
            TVDisplayRate.query.filter(
                TVDisplayRate.bank_id.in_(bank_ids_subq)
            ).delete(synchronize_session=False)
        display.last_updated_at = datetime.utcnow()
        db.session.commit()
        flash("Saved.", "success")
        return redirect(url_for("tv_display_country_edit", country_id=country.id))

    # GET — build a {(bank_id, mt_company): rate} map for quick cell lookup.
    banks = (TVDisplayPayoutBank.query
              .filter_by(country_id=country.id)
              .order_by(TVDisplayPayoutBank.sort_order,
                        TVDisplayPayoutBank.id).all())
    companies = _csv_split(country.mt_companies)
    rate_lookup = {}
    if banks:
        for r in (TVDisplayRate.query
                   .filter(TVDisplayRate.bank_id.in_([b.id for b in banks]))
                   .all()):
            rate_lookup[(r.bank_id, r.mt_company)] = r.rate

    # Catalog rows for the company-column + bank-row pickers. Banks
    # scope to the section's country code; companies are global. Only
    # active rows surface in the picker (is_active=False = retired
    # but still resolvable for legacy references).
    company_catalog = (TVCompanyCatalog.query
                        .filter_by(is_active=True)
                        .order_by(TVCompanyCatalog.sort_order,
                                  TVCompanyCatalog.display_name).all())
    bank_catalog = (TVBankCatalog.query
                     .filter_by(is_active=True,
                                country_code=(country.country_code or "").upper())
                     .order_by(TVBankCatalog.sort_order,
                               TVBankCatalog.display_name).all())
    # Lookups for resolving stored slugs back to a friendly label
    # in the chip / row display. Includes inactive entries so
    # legacy data still renders. Falls back to the raw stored
    # token when nothing matches (free-text legacy values).
    company_name_by_slug = {c.slug: c.display_name
                             for c in TVCompanyCatalog.query.all()}
    bank_name_by_slug = {b.slug: b.display_name
                          for b in TVBankCatalog.query.all()}
    # Logo URLs (with cache-bust query) keyed by slug so the chip /
    # row markup can resolve in one O(1) lookup. Empty string when
    # no logo has been uploaded — the template falls back to text.
    logo_versions = {(r.catalog_type, r.slug): int(r.updated_at.timestamp())
                      for r in TVCatalogLogo.query.all()}
    company_logo_by_slug = {}
    for c in TVCompanyCatalog.query.all():
        if c.logo_url:
            v = logo_versions.get(("company", c.slug), 0)
            company_logo_by_slug[c.slug] = (
                url_for("tv_catalog_logo", catalog_type="company", slug=c.slug)
                + (f"?v={v}" if v else "")
            )
    bank_logo_by_slug = {}
    for b in TVBankCatalog.query.all():
        if b.logo_url:
            v = logo_versions.get(("bank", b.slug), 0)
            bank_logo_by_slug[b.slug] = (
                url_for("tv_catalog_logo", catalog_type="bank", slug=b.slug)
                + (f"?v={v}" if v else "")
            )
    return render_template("tv_display_country.html",
                            user=current_user(), store=store, display=display,
                            country=country, banks=banks, companies=companies,
                            rate_lookup=rate_lookup,
                            company_catalog=company_catalog,
                            bank_catalog=bank_catalog,
                            company_logo_by_slug=company_logo_by_slug,
                            bank_logo_by_slug=bank_logo_by_slug,
                            company_name_by_slug=company_name_by_slug,
                            bank_name_by_slug=bank_name_by_slug,
                            country_picker=_TV_COUNTRY_PICKER,
                            country_picker_codes=[c[0] for c in _TV_COUNTRY_PICKER])

@app.route("/tv-display/countries/<int:country_id>/delete", methods=["POST"])
@login_required
def tv_display_country_delete(country_id):
    guard = _tv_required()
    if not isinstance(guard, tuple):
        return guard
    _, store = guard
    display = _ensure_tv_display(store)
    country = TVDisplayCountry.query.filter_by(
        id=country_id, display_id=display.id).first_or_404()
    # Manual cascade — same pattern as the retention purge.
    bank_ids = [b.id for b in TVDisplayPayoutBank.query.filter_by(
        country_id=country.id).all()]
    if bank_ids:
        TVDisplayRate.query.filter(TVDisplayRate.bank_id.in_(bank_ids)).delete(
            synchronize_session=False)
    TVDisplayPayoutBank.query.filter_by(country_id=country.id).delete(
        synchronize_session=False)
    db.session.delete(country)
    display.last_updated_at = datetime.utcnow()
    db.session.commit()
    flash(f"Removed {country.country_name}.", "success")
    return redirect(url_for("admin_tv_display"))

def _render_tv_board(display, store):
    """Build the section payload + render the public TV template.
    Shared by the legacy /tv/<public_token> route and the per-device
    /tv/device/<device_token> route — same content, different keys
    in front of it.

    Resolves catalog slugs to display_name so the public board shows
    "BBVA Bancomer" not "mx_bbva_bancomer". Lookups include INACTIVE
    catalog rows so legacy references keep rendering even after the
    superadmin retires a catalog entry."""
    # Resolve all catalog slugs in one query rather than per-section.
    company_name_by_slug = {c.slug: c.display_name
                             for c in TVCompanyCatalog.query.all()}
    bank_name_by_slug = {b.slug: b.display_name
                          for b in TVBankCatalog.query.all()}
    # Logo URL maps with cache-bust suffix. Only includes catalog
    # rows whose logo_url is populated; entries without uploads are
    # absent and the template falls back to display_name text.
    logo_versions = {(r.catalog_type, r.slug): int(r.updated_at.timestamp())
                      for r in TVCatalogLogo.query.all()}
    company_logo_by_slug = {}
    for c in TVCompanyCatalog.query.all():
        if c.logo_url:
            v = logo_versions.get(("company", c.slug), 0)
            company_logo_by_slug[c.slug] = (
                url_for("tv_catalog_logo", catalog_type="company", slug=c.slug)
                + (f"?v={v}" if v else "")
            )
    bank_logo_by_slug = {}
    for b in TVBankCatalog.query.all():
        if b.logo_url:
            v = logo_versions.get(("bank", b.slug), 0)
            bank_logo_by_slug[b.slug] = (
                url_for("tv_catalog_logo", catalog_type="bank", slug=b.slug)
                + (f"?v={v}" if v else "")
            )

    countries = (TVDisplayCountry.query
                  .filter_by(display_id=display.id)
                  .order_by(TVDisplayCountry.sort_order, TVDisplayCountry.id).all())
    sections = []
    # Global company list, deduplicated by first appearance — every
    # country uses the same column structure, so the public board
    # renders ONE shared top header row instead of per-country headers.
    # If a country happens to omit a global company, its rate cells
    # render as "—" via the rate_map fallback (see _CELL_PLACEHOLDER).
    seen = set()
    global_companies = []
    for c in countries:
        for slug in _csv_split(c.mt_companies):
            if slug not in seen:
                seen.add(slug)
                global_companies.append(slug)
    global_company_labels = [company_name_by_slug.get(s, s) for s in global_companies]
    global_company_logos  = [company_logo_by_slug.get(s, "") for s in global_companies]

    for c in countries:
        banks = (TVDisplayPayoutBank.query
                  .filter_by(country_id=c.id)
                  .order_by(TVDisplayPayoutBank.sort_order,
                            TVDisplayPayoutBank.id).all())
        rate_map = {}
        if banks:
            for r in (TVDisplayRate.query
                       .filter(TVDisplayRate.bank_id.in_([b.id for b in banks]))
                       .all()):
                rate_map[(r.bank_id, r.mt_company)] = r.rate
        sections.append({
            "country": c,
            "banks":   banks,
            "rates":   rate_map,
        })
    return render_template("tv_display_public.html",
                            display=display, store=store, sections=sections,
                            global_companies=global_companies,
                            global_company_labels=global_company_labels,
                            global_company_logos=global_company_logos,
                            bank_name_by_slug=bank_name_by_slug,
                            bank_logo_by_slug=bank_logo_by_slug)

# ── Catalog logo serve ──────────────────────────────────────
#
# Public, no auth — the TV display itself is public-by-token, and
# the logos shown on it can't reasonably be auth-gated. Brute-force
# enumeration is not a concern (logos are intentionally displayed
# on-screen for customers in the shop). We DO want aggressive
# browser caching so the rate board doesn't re-fetch every logo on
# every 30s refresh; templates append ?v=<updated_at_unix> to bust
# the cache when an admin re-uploads.

# MIME types accepted on upload AND served back. Anything not in
# this set returns a 404 — keeps a corrupted DB row from spitting
# arbitrary bytes at a browser.
_TV_LOGO_ALLOWED_MIMES = {
    "image/png", "image/jpeg", "image/webp", "image/svg+xml",
}

@app.route("/tv/logo/<catalog_type>/<slug>")
def tv_catalog_logo(catalog_type, slug):
    """Stream the BLOB for a catalog logo. Year-long Cache-Control;
    cache-bust by ?v=<timestamp> on the embedding template."""
    if catalog_type not in ("company", "bank"):
        abort(404)
    row = TVCatalogLogo.query.filter_by(
        catalog_type=catalog_type, slug=slug).first()
    if not row or row.mime_type not in _TV_LOGO_ALLOWED_MIMES:
        abort(404)
    resp = make_response(row.blob)
    resp.headers["Content-Type"] = row.mime_type
    resp.headers["Content-Length"] = str(len(row.blob))
    # Year-long immutable cache. Templates append ?v=<unix> so a
    # re-upload changes the URL → fresh fetch on next render.
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    # Block image-format sniffing — the served bytes match the
    # whitelisted mime exactly.
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp

@app.route("/tv/<token>")
def tv_public_display(token):
    """Fullscreen rate board, no auth. Anyone with the URL sees it.
    No chrome (no base.html), so it works on a smart-TV browser /
    Chromecast / Fire TV WebView with no extra UI to confuse the
    operator.

    Tablets / Chromecasts use this URL directly. Fire TV companion
    apps go through /tv/device/<device_token> instead so the shared
    public_token never leaves the browser/Chromecast world."""
    display = TVDisplay.query.filter_by(public_token=token).first_or_404()
    store = db.session.get(Store, display.store_id)
    # If the store later removes the addon, the URL stops working —
    # belt-and-suspenders, since regenerate_token is the supported path.
    if not store or not store_has_addon(store, "tv_display"):
        abort(404)
    return _render_tv_board(display, store)

@app.route("/tv/device/<device_token>")
def tv_device_display(device_token):
    """Per-device rate-board URL handed to a Fire TV companion app
    after a successful pair-code redeem. Same content as
    /tv/<public_token>, but bound to a single TVPairing row.

    404s on:
      - unknown device_token
      - revoked TVPairing (replaced by a newer pairing or admin-revoked)
      - addon switched off after pairing
    On every successful render we bump TVPairing.last_seen_at so the
    admin UI can show "last seen 2 min ago"."""
    pairing = TVPairing.query.filter_by(device_token=device_token).first()
    if not pairing or pairing.revoked_at is not None:
        abort(404)
    display = db.session.get(TVDisplay, pairing.display_id)
    if not display:
        abort(404)
    store = db.session.get(Store, display.store_id)
    if not store or not store_has_addon(store, "tv_display"):
        abort(404)
    pairing.last_seen_at = datetime.utcnow()
    db.session.commit()
    return _render_tv_board(display, store)

# ── Dashboard ────────────────────────────────────────────────
@app.route("/dashboard")
@login_required
def dashboard():
    user=current_user(); store=current_store(); today=date.today()
    month_start=date(today.year,today.month,1)
    if user.role=="superadmin":
        return render_template("dashboard_superadmin.html",
                               user=user, today=today,
                               **_superadmin_dashboard_context())
    # Owners don't have a `current_store` — they live across multiple
    # stores under their umbrella. /dashboard previously crashed on
    # `store.id` for owner sessions; route them to their own dashboard.
    if user.role == "owner":
        return redirect(url_for("owner_dashboard"))
    if store is None:
        # Defensive: any other role without a store context (shouldn't
        # happen for admin/employee under normal login) gets bounced
        # back to login rather than 500'ing on store.id below.
        return redirect(url_for("login"))
    sid=store.id
    if user.role=="admin":
        total_transfers=Transfer.query.filter_by(store_id=sid).count()
        today_transfers=Transfer.query.filter_by(store_id=sid,send_date=today).count()
        pending_ach=ACHBatch.query.filter_by(store_id=sid,reconciled=False).count()
        recent_transfers=Transfer.query.filter_by(store_id=sid).order_by(Transfer.created_at.desc()).limit(8).all()
        recent_batches=ACHBatch.query.filter_by(store_id=sid).order_by(ACHBatch.ach_date.desc()).limit(5).all()
        company_stats={}
        for co in store_mt_companies(store):
            rows=Transfer.query.filter(Transfer.store_id==sid,Transfer.company==co,
                Transfer.send_date>=month_start,Transfer.status.notin_(["Canceled","Rejected"])).all()
            company_stats[co]={"count":len(rows),"total":sum(r.send_amount for r in rows),"fees":sum(r.fee for r in rows)}
        today_report=DailyReport.query.filter_by(store_id=sid,report_date=today).first()
        month_report=MonthlyFinancial.query.filter_by(store_id=sid,year=today.year,month=today.month).first()
        stripe_accounts = (StripeBankAccount.query
                           .filter_by(store_id=sid, enabled=True)
                           .order_by(StripeBankAccount.connected_at.desc()).limit(3).all())
        return render_template("dashboard_admin.html",user=user,store=store,today=today,
            total_transfers=total_transfers,today_transfers=today_transfers,
            pending_ach=pending_ach,recent_transfers=recent_transfers,recent_batches=recent_batches,
            company_stats=company_stats,today_report=today_report,month_report=month_report,
            stripe_accounts=stripe_accounts)
    else:
        # Employee dashboard shows only TODAY'S transfers and only aggregates
        # scoped to today. "This Month" and "All Time" counts were removed
        # — those are business-level totals that belong with the admin.
        # Historical transfers are still reachable via /transfers for
        # customer-service lookups.
        my_today=Transfer.query.filter_by(store_id=sid,send_date=today).order_by(Transfer.created_at.desc()).all()
        return render_template("dashboard_employee.html",user=user,store=store,today=today,
            my_today=my_today)

# ── Customers (per-store directory) ──────────────────────────
# Ordered roughly by likelihood for a US-based remittance storefront; the
# picker displays these in order so the common choices stay on top.
PHONE_COUNTRY_CODES = [
    ("+1",   "United States / Canada"),
    ("+52",  "Mexico"),
    ("+502", "Guatemala"),
    ("+503", "El Salvador"),
    ("+504", "Honduras"),
    ("+505", "Nicaragua"),
    ("+506", "Costa Rica"),
    ("+507", "Panama"),
    ("+509", "Haiti"),
    ("+57",  "Colombia"),
    ("+593", "Ecuador"),
    ("+51",  "Peru"),
    ("+58",  "Venezuela"),
    ("+54",  "Argentina"),
    ("+55",  "Brazil"),
    ("+56",  "Chile"),
    ("+91",  "India"),
    ("+92",  "Pakistan"),
    ("+63",  "Philippines"),
    ("+234", "Nigeria"),
    ("+254", "Kenya"),
    ("+233", "Ghana"),
]

def sibling_store_ids(store_id):
    """All store IDs that share at least one owner with the given store.

    Includes the input store_id itself. Returns [store_id] when the store
    has no Owner links (solo shop) so this is safe to call unconditionally.

    Used to scope customer-directory queries: a multi-store owner should
    see one unified customer list across all their locations, while
    unrelated stores stay fully isolated.
    """
    owner_ids = [r.owner_id for r in
                 StoreOwnerLink.query.filter_by(store_id=store_id).all()]
    if not owner_ids:
        return [store_id]
    sibling_rows = (StoreOwnerLink.query
                    .filter(StoreOwnerLink.owner_id.in_(owner_ids))
                    .all())
    ids = {r.store_id for r in sibling_rows}
    ids.add(store_id)
    return sorted(ids)

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
    cust = None
    sibling_ids = sibling_store_ids(store_id)
    if customer_id:
        cust = (Customer.query
                .filter(Customer.id == customer_id,
                        Customer.store_id.in_(sibling_ids))
                .first())
    if cust is None and phone_number:
        cust = (Customer.query
                .filter(Customer.store_id.in_(sibling_ids),
                        Customer.phone_country == (phone_country or "+1"),
                        Customer.phone_number == phone_number)
                .first())
    if cust is None:
        cust = Customer(store_id=store_id, full_name=full_name or "",
                        phone_country=(phone_country or "+1"),
                        phone_number=phone_number or "")
        db.session.add(cust)
    if full_name:     cust.full_name     = full_name
    if address:       cust.address       = address
    if dob:           cust.dob           = dob
    if phone_country: cust.phone_country = phone_country
    if phone_number:  cust.phone_number  = phone_number
    cust.updated_at = datetime.utcnow()
    db.session.flush()
    return cust

@app.route("/api/customers/search")
@login_required
def api_customers_search():
    """Autocomplete endpoint for the sender field on the transfer form.

    Scope: all stores under the same owner umbrella as the current session's
    store. Standalone stores (no owner links) see only their own customers.
    Unrelated stores can never see each other's customers.

    Searches phone number OR name (not address — too noisy). 2-char minimum
    on the query so the dropdown doesn't blast the whole directory. Address
    rides along in each payload so the UI can auto-fill it on pick.
    """
    sid = session.get("store_id")
    if not sid:
        return jsonify([])
    q_text = request.args.get("q", "").strip()
    if len(q_text) < 2:
        return jsonify([])
    like = f"%{q_text}%"
    scope_ids = sibling_store_ids(sid)
    rows = (Customer.query
            .filter(Customer.store_id.in_(scope_ids))
            .filter(db.or_(
                Customer.phone_number.ilike(like),
                Customer.full_name.ilike(like),
            ))
            .order_by(Customer.updated_at.desc())
            .limit(10)
            .all())
    # Precompute the home-store name for rows not owned by the current
    # store so the UI can label "from Store A" on cross-store matches.
    other_store_ids = {c.store_id for c in rows if c.store_id != sid}
    home_names = {}
    if other_store_ids:
        home_names = {s.id: s.name for s in
                      Store.query.filter(Store.id.in_(other_store_ids)).all()}
    return jsonify([c.to_dict(current_store_id=sid, home_names=home_names) for c in rows])

# ── Transfers ────────────────────────────────────────────────
@app.route("/transfers")
@login_required
def transfers():
    user=current_user(); sid=session.get("store_id")
    if not sid:
        flash("Select a store first.","error"); return redirect(url_for("dashboard"))
    q=Transfer.query.filter_by(store_id=sid)
    # Employees and admins see the same store-scoped transfer list. The
    # earlier `created_by=self` + `send_date=today` clamps hid transfers
    # the employee genuinely needs — a customer coming back days later
    # to update a transfer's status often asks a different cashier.
    # Cross-store isolation is still enforced by the store_id filter;
    # the aggregate totals that reveal business-level info are hidden
    # separately on the employee dashboard.
    company=request.args.get("company",""); status=request.args.get("status","")
    date_from=request.args.get("date_from",""); date_to=request.args.get("date_to","")
    sender=request.args.get("sender","").strip()
    recipient=request.args.get("recipient","").strip()
    country=request.args.get("country","").strip()
    confirm=request.args.get("confirm","").strip()
    batch=request.args.get("batch","").strip()
    search=request.args.get("q","").strip()
    if company: q=q.filter_by(company=company)
    if status:  q=q.filter_by(status=status)
    if date_from:
        # ValueError on bad user input from the query string. Silently
        # ignore — we just skip the filter if the string isn't
        # YYYY-MM-DD. Don't catch broader Exception — we want a real
        # bug (e.g. an unexpected AttributeError) to actually raise.
        try: q=q.filter(Transfer.send_date>=datetime.strptime(date_from,"%Y-%m-%d").date())
        except ValueError: pass
    if date_to:
        try: q=q.filter(Transfer.send_date<=datetime.strptime(date_to,"%Y-%m-%d").date())
        except ValueError: pass
    if sender:    q=q.filter(Transfer.sender_name.ilike(f"%{sender}%"))
    if recipient: q=q.filter(Transfer.recipient_name.ilike(f"%{recipient}%"))
    if country:   q=q.filter(Transfer.country.ilike(f"%{country}%"))
    if confirm:   q=q.filter(Transfer.confirm_number.ilike(f"%{confirm}%"))
    if batch:     q=q.filter(Transfer.batch_id.ilike(f"%{batch}%"))
    if search:
        like=f"%{search}%"
        q=q.filter(db.or_(
            Transfer.sender_name.ilike(like),
            Transfer.recipient_name.ilike(like),
            Transfer.confirm_number.ilike(like),
            Transfer.country.ilike(like),
            Transfer.batch_id.ilike(like),
        ))
    q=q.order_by(Transfer.send_date.desc(),Transfer.created_at.desc())
    PER_PAGE=50
    try: page=max(1,int(request.args.get("page",1)))
    except (TypeError, ValueError): page=1
    total=q.count()
    total_pages=max(1,(total+PER_PAGE-1)//PER_PAGE)
    if page>total_pages: page=total_pages
    rows=q.offset((page-1)*PER_PAGE).limit(PER_PAGE).all()
    ctx = dict(user=user, transfers=rows,
        company=company, status=status, date_from=date_from, date_to=date_to,
        sender=sender, recipient=recipient, country=country, confirm=confirm,
        batch=batch, q=search, page=page, total=total, total_pages=total_pages,
        per_page=PER_PAGE)
    # Live-search AJAX path — called from templates/transfers.html's JS.
    # Combined page total — send_amount + fee + federal_tax, matching the
    # single "Amount" column the user sees in the table (each row shows
    # the total with a hover-pill breakdown). Shared between the full and
    # partial render paths so the header always matches the column sum.
    page_amount = float(sum(
        r.send_amount + r.fee + (r.federal_tax or 0) for r in rows))
    ctx["page_amount"] = page_amount

    # Returns the table+pager HTML plus meta so the client can update the
    # card header without refetching the whole chrome.
    if request.args.get("partial") == "1":
        return jsonify({
            "html":        render_template("_transfers_table.html", **ctx),
            "total":       total,
            "page":        page,
            "total_pages": total_pages,
            "page_amount": page_amount,
        })
    return render_template("transfers.html", **ctx)

def _parse_dob(raw):
    """Parse a YYYY-MM-DD date string from the form, or None when blank/bad."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None

def _active_roster(store_id):
    """Names available in the "Processed by" dropdown. Inactive roster rows
    are hidden so cashiers can't credit new transfers to former employees."""
    return StoreEmployee.query.filter_by(
        store_id=store_id, is_active=True
    ).order_by(StoreEmployee.name.asc()).all()

def _pick_employee(store_id, raw_id):
    """Resolve a form `employee_id` value against the store's roster.
    Returns (employee_or_none, display_name). Cross-store picks are rejected."""
    try:
        eid = int(raw_id) if raw_id else None
    except (TypeError, ValueError):
        return None, ""
    if not eid:
        return None, ""
    emp = StoreEmployee.query.filter_by(id=eid, store_id=store_id).first()
    return (emp, emp.name) if emp else (None, "")

# Fields whose changes are interesting to surface in the audit log summary.
# Sender PII edits are included (addr/phone/dob) since the customer directory
# propagates them across sibling stores and admins want to see who edited.
_TRANSFER_AUDIT_FIELDS = [
    ("send_date",      "Send date"),
    ("company",        "Company"),
    ("service_type",   "Service"),
    ("sender_name",    "Sender"),
    ("send_amount",    "Amount"),
    ("fee",            "Fee"),
    ("federal_tax",    "Tax"),
    ("commission",     "Commission"),
    ("recipient_name", "Recipient"),
    ("country",        "Country"),
    ("recipient_phone","Recipient phone"),
    ("sender_phone",   "Sender phone"),
    ("sender_address", "Sender address"),
    ("confirm_number", "Confirm #"),
    ("status",         "Status"),
    ("status_notes",   "Status notes"),
    ("batch_id",       "Batch"),
    ("internal_notes", "Notes"),
    ("employee_name",  "Processed by"),
]

# Service types other than Money Transfer don't carry the 1% federal tax —
# bill payments, top-ups, and recharges aren't ACH-withdrawal flows where
# tax would be remitted. The transfer form's dropdown options must match
# this set exactly. Server-side check is the gate; the JS preview just
# mirrors the same rule for live feedback.
SERVICE_TYPES = ("Money Transfer", "Bill Payment", "Top Up", "Recharge")
_TAX_EXEMPT_SERVICES = frozenset(SERVICE_TYPES) - {"Money Transfer"}

# Recipient countries that don't carry the federal-tax remittance.
# The tax is the percentage the IRS collects on money sent ABROAD —
# domestic transfers (within the US) skip it entirely. Same enforcement
# pattern as _TAX_EXEMPT_SERVICES: server zeros tax when the country
# matches; the JS toggles the field's visibility for live UX.
_DOMESTIC_COUNTRIES = frozenset({"United States"})

# Countries shown in the recipient-country dropdown on the transfer
# form. Single source so server validation, template, and tests agree.
# 'United States' is included so admins can log a domestic transfer
# (no federal tax). 'Other' stays as the catch-all for anything else.
TRANSFER_COUNTRIES = (
    "United States", "Mexico", "Guatemala", "El Salvador", "Honduras",
    "Dominican Republic", "Colombia", "Ecuador", "Peru", "Other",
)

def _normalize_service_type(raw):
    """Coerce the form input to a known service type. Anything we don't
    recognize falls back to Money Transfer (the historical default), so a
    bad client value can't quietly disable tax."""
    val = (raw or "").strip()
    return val if val in SERVICE_TYPES else "Money Transfer"

def _federal_tax_for(send_amount, service_type, store, country=None):
    """The single source of truth for transfer tax. Bill Payment / Top Up /
    Recharge skip the tax entirely; Money Transfer applies the store's
    configured rate UNLESS the recipient country is domestic (US), in
    which case the tax also skips (it's only owed on money leaving the
    country). Both new_transfer and edit_transfer call this so the
    rule can't drift between create and update."""
    if service_type in _TAX_EXEMPT_SERVICES:
        return 0.0
    if country and country.strip() in _DOMESTIC_COUNTRIES:
        return 0.0
    rate = (store.federal_tax_rate if store else None) or 0
    return round((send_amount or 0) * rate, 2)

def _summarize_transfer_changes(before, after, max_fields=4):
    """Format a before/after diff into the audit log summary string."""
    parts = []
    for field, label in _TRANSFER_AUDIT_FIELDS:
        old, new = before.get(field), after.get(field)
        if (old or None) == (new or None):
            continue
        old_s = "—" if old in (None, "") else str(old)
        new_s = "—" if new in (None, "") else str(new)
        parts.append(f"{label}: {old_s} → {new_s}")
    if len(parts) > max_fields:
        overflow = len(parts) - max_fields
        parts = parts[:max_fields] + [f"+{overflow} more field{'s' if overflow != 1 else ''}"]
    return "; ".join(parts)

def _record_transfer_audit(transfer, user, action, employee_id, employee_name, summary):
    db.session.add(TransferAudit(
        store_id=transfer.store_id,
        transfer_id=transfer.id,
        user_id=user.id if user else None,
        employee_id=employee_id,
        employee_name=employee_name,
        action=action,
        summary=summary,
    ))

def _transfer_snapshot(t):
    """Capture the subset of Transfer fields we audit, as a dict."""
    return {field: getattr(t, field, None) for field, _ in _TRANSFER_AUDIT_FIELDS}

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

@app.route("/transfers/new",methods=["GET","POST"])
@login_required
def new_transfer():
    user=current_user(); sid=session.get("store_id")
    if not sid:
        flash("Select a store first.","error"); return redirect(url_for("dashboard"))
    if request.method=="POST":
        # "Processed by" is required so every transfer has an auditable owner.
        emp, emp_name = _pick_employee(sid, request.form.get("employee_id"))
        if not emp:
            flash("Pick who processed this transfer before saving.", "error")
            return redirect(url_for("new_transfer"))
        sender_name     = request.form["sender_name"]
        sender_phone_cc = (request.form.get("sender_phone_country") or "+1").strip()
        sender_phone    = request.form.get("sender_phone","").strip()
        sender_address  = request.form.get("sender_address","").strip()
        sender_dob      = _parse_dob(request.form.get("sender_dob"))
        # Upsert the Customer first so the transfer can link to a stable FK.
        cust = find_or_upsert_customer(
            store_id=sid, full_name=sender_name,
            phone_country=sender_phone_cc, phone_number=sender_phone,
            address=sender_address, dob=sender_dob,
            customer_id=request.form.get("customer_id", type=int),
        )
        send_amount_v = float(request.form.get("send_amount") or 0)
        service_type_v = _normalize_service_type(request.form.get("service_type"))
        country_v = (request.form.get("country","") or "").strip()
        t=Transfer(store_id=sid,created_by=user.id,customer_id=cust.id,
            send_date=datetime.strptime(request.form["send_date"],"%Y-%m-%d").date(),
            company=request.form["company"],
            service_type=service_type_v,
            sender_name=sender_name,
            send_amount=send_amount_v,
            fee=float(request.form.get("fee") or 0),
            # Federal tax is server-computed via _federal_tax_for — the rule
            # (Money Transfer = taxed, but domestic / non-MT exempt) lives
            # in one place so the form, edit, and recompute paths can't
            # drift apart.
            federal_tax=_federal_tax_for(send_amount_v, service_type_v,
                                         current_store(), country=country_v),
            commission=float(request.form.get("commission") or 0),
            recipient_name=request.form.get("recipient_name",""),
            country=country_v,
            recipient_phone=request.form.get("recipient_phone",""),
            sender_phone=sender_phone,
            sender_phone_country=sender_phone_cc,
            sender_address=sender_address,
            sender_dob=sender_dob,
            confirm_number=request.form.get("confirm_number",""),
            status=request.form.get("status","Sent"),
            status_notes=request.form.get("status_notes",""),
            batch_id=request.form.get("batch_id",""),
            internal_notes=request.form.get("internal_notes",""),
            employee_id=emp.id,
            employee_name=emp_name)
        db.session.add(t); db.session.flush()
        _record_transfer_audit(t, user, "created", emp.id, emp_name,
            f"Logged by {emp_name}.")
        db.session.commit()
        flash("Transfer logged successfully.","success"); return redirect(url_for("transfers"))
    return render_template("transfer_form.html", user=user, transfer=None,
        roster=_active_roster(sid), audit_entries=[],
        **_transfer_form_ctx(current_store()))

@app.route("/transfers/<int:tid>/edit",methods=["GET","POST"])
@login_required
def edit_transfer(tid):
    """Edit any transfer belonging to the current store.

    Employees share a login, so anyone logged in at the store can edit any
    of the store's transfers. The "Processed by" dropdown (required) +
    audit log are what give the admin visibility into who actually did
    what. Employees at other stores are still blocked by `store_id`.
    """
    user=current_user(); sid=session.get("store_id")
    if not sid:
        flash("Select a store first.","error"); return redirect(url_for("dashboard"))
    t=Transfer.query.filter_by(id=tid,store_id=sid).first_or_404()
    if request.method=="POST":
        emp, emp_name = _pick_employee(sid, request.form.get("employee_id"))
        if not emp:
            flash("Pick who made this edit before saving.", "error")
            return redirect(url_for("edit_transfer", tid=t.id))
        before = _transfer_snapshot(t)
        t.send_date=datetime.strptime(request.form["send_date"],"%Y-%m-%d").date()
        t.company=request.form["company"]; t.sender_name=request.form["sender_name"]
        t.service_type=_normalize_service_type(request.form.get("service_type"))
        t.send_amount=float(request.form.get("send_amount") or 0)
        t.fee=float(request.form.get("fee") or 0)
        t.commission=float(request.form.get("commission") or 0)
        t.recipient_name=request.form.get("recipient_name","")
        # Set country FIRST so the federal_tax recompute below sees the
        # newly-chosen country (domestic transfers skip tax).
        t.country=(request.form.get("country","") or "").strip()
        # Always recompute federal_tax server-side via _federal_tax_for so
        # changing the send amount OR the service type OR the country
        # all flip the tax.
        t.federal_tax=_federal_tax_for(t.send_amount, t.service_type,
                                       current_store(), country=t.country)
        t.recipient_phone=request.form.get("recipient_phone","")
        t.sender_phone=request.form.get("sender_phone","").strip()
        t.sender_phone_country=(request.form.get("sender_phone_country") or "+1").strip()
        t.sender_address=request.form.get("sender_address","").strip()
        t.sender_dob=_parse_dob(request.form.get("sender_dob"))
        t.confirm_number=request.form.get("confirm_number","")
        t.status=request.form.get("status","Sent")
        t.status_notes=request.form.get("status_notes","")
        t.batch_id=request.form.get("batch_id","")
        t.internal_notes=request.form.get("internal_notes","")
        t.employee_id=emp.id
        t.employee_name=emp_name
        t.updated_at=datetime.utcnow()
        # Keep the customer directory in sync with the edited snapshot.
        cust = find_or_upsert_customer(
            store_id=sid, full_name=t.sender_name,
            phone_country=t.sender_phone_country, phone_number=t.sender_phone,
            address=t.sender_address, dob=t.sender_dob,
            customer_id=request.form.get("customer_id", type=int) or t.customer_id,
        )
        t.customer_id = cust.id
        after = _transfer_snapshot(t)
        summary = _summarize_transfer_changes(before, after) or "No field changes."
        # Flag pure status changes as a distinct audit action so the admin
        # view can highlight them — status transitions are the most common
        # reason an edit happens after the initial save.
        changed_fields = {
            f for f, _ in _TRANSFER_AUDIT_FIELDS
            if (before.get(f) or None) != (after.get(f) or None)
        }
        action = "status_changed" if changed_fields == {"status"} else "updated"
        _record_transfer_audit(t, user, action, emp.id, emp_name, summary)
        db.session.commit(); flash("Transfer updated.","success")
        return redirect(url_for("edit_transfer", tid=t.id))
    # The preselected "Processed by" is the original roster row if it still
    # exists (even if deactivated); historical names with no matching row
    # fall through to a read-only hint line in the form.
    audit_entries = TransferAudit.query.filter_by(
        store_id=sid, transfer_id=t.id
    ).order_by(TransferAudit.created_at.desc()).limit(50).all()
    roster = _active_roster(sid)
    # If the transfer's current employee was deactivated, surface them in the
    # dropdown as a selectable (but italicized) fallback so editing doesn't
    # silently blank the attribution.
    if t.employee_id and not any(r.id == t.employee_id for r in roster):
        legacy = db.session.get(StoreEmployee, t.employee_id)
        if legacy and legacy.store_id == sid:
            roster = [legacy] + roster
    return render_template("transfer_form.html", user=user, transfer=t,
        roster=roster, audit_entries=audit_entries,
        **_transfer_form_ctx(current_store()))


@app.route("/transfers/<int:tid>/delete", methods=["POST"])
@admin_required
def delete_transfer(tid):
    """Hard-delete a transfer. Store admins only; employees get blocked
    by @admin_required at the route level, so hiding the button in the
    template is defense-in-depth, not the actual gate.

    TransferAudit has an FK onto Transfer, so we drop the audit rows
    for this transfer first. The transfer's audit history disappears
    along with the record it described — the intent of deletion — but
    anything downstream that aggregates from transfers (batch totals,
    daily book MT auto-pre-fill, dashboard counts) is a live query, so
    those recompute correctly on the next page load.
    """
    sid = session.get("store_id")
    if not sid:
        flash("Select a store first.", "error")
        return redirect(url_for("dashboard"))
    t = Transfer.query.filter_by(id=tid, store_id=sid).first_or_404()
    TransferAudit.query.filter_by(store_id=sid, transfer_id=t.id).delete(
        synchronize_session=False)
    db.session.delete(t)
    db.session.commit()
    flash("Transfer deleted.", "success")
    return redirect(url_for("transfers"))


# ── Daily Book ───────────────────────────────────────────────
# Companies a new store can pick from on the settings page. The daily book
# and transfer form both pull per-store from Store.companies (resolved via
# store_mt_companies), so this is only the catalog — not a hardcoded list.
KNOWN_MT_COMPANIES = [
    "Intermex", "Maxi", "Barri", "Ria", "Vigo",
    "Inter Cambio", "Sigue", "MoneyGram", "Western Union",
    "Dolex", "Viamericas", "Transfast", "Pangea", "Boss Revolution",
]
DEFAULT_MT_COMPANIES = ["Intermex", "Maxi", "Barri"]

def store_mt_companies(store):
    """The active list of money-transfer companies for a store.

    Falls back to DEFAULT_MT_COMPANIES when the Store.companies CSV is
    empty — so existing stores keep working the moment the migration
    lands, and new stores get a sensible default on signup.
    """
    if store is None or not (store.companies or "").strip():
        return list(DEFAULT_MT_COMPANIES)
    return [c.strip() for c in store.companies.split(",") if c.strip()]

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

def _ensure_daily_report(store_id, report_date):
    """Return the DailyReport for (store, date), creating an empty one if needed."""
    rpt = DailyReport.query.filter_by(store_id=store_id, report_date=report_date).first()
    if rpt is None:
        rpt = DailyReport(store_id=store_id, report_date=report_date)
        db.session.add(rpt)
        db.session.flush()
    return rpt

_DAILY_LOCKED_MSG = "This daily report is locked. Unlock it before making changes."

def _daily_is_locked(store_id, report_date):
    """True if a DailyReport exists for (store, date) and is locked.
    Write routes call this first and bail before touching the DB."""
    rpt = DailyReport.query.filter_by(store_id=store_id, report_date=report_date).first()
    return bool(rpt and rpt.locked_at)

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
    return redirect(url_for("daily_report", ds=ds))



def _migrate_legacy_line_item_tables():
    """One-time, idempotent migration: copy legacy DailyDrop and
    CheckDeposit rows into DailyLineItem with discriminator kinds
    ('drop' and 'check_deposit'). Runs at boot after db.create_all().

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
        legacy_drops = DailyDrop.query.all()
    except Exception:
        # Tables don't exist yet on a brand-new boot before
        # db.create_all() finishes. Caller wraps this in a try block
        # but we belt-and-suspenders here too.
        legacy_drops = []
    for dd in legacy_drops:
        existing = DailyLineItem.query.filter_by(
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
        legacy_checks = CheckDeposit.query.all()
    except Exception:
        legacy_checks = []
    for cd in legacy_checks:
        existing = DailyLineItem.query.filter_by(
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
_LINE_ITEM_KINDS = {
    "return_payback": ("return_check_paid_back", "return check payback", "entries"),
    "cash_purchase":  ("cash_purchases",         "cash purchase",        "entries"),
    "cash_expense":   ("cash_expense",           "cash expense",         "entries"),
    "check_purchase": ("check_purchases",        "check purchase",       "entries"),
    "check_expense":  ("check_expense",          "check expense",        "entries"),
    # Catch-all "other" buckets — a single day can have multiple
    # ad-hoc cash-ins (refunds, owner contributions) and cash-outs
    # (one-off payouts that don't fit Payroll or Drops). Backed by
    # the same DailyLineItem model + auto-derived total contract as
    # the rest of the kinds above.
    "other_cash_in":  ("other_cash_in",          "other cash in",        "entries"),
    "other_cash_out": ("other_cash_out",         "other cash out",       "entries"),
    # Outside-cash drops (ATM drops, safe drops). Originally lived in
    # its own DailyDrop table + bespoke routes/IIFE — collapsed into
    # the generic kind system after the data migration. The legacy
    # DailyDrop table is preserved (data not deleted) but the code
    # path no longer references it.
    "drop":           ("outside_cash_drops",     "drop",                 "drops"),
    # Check deposits (morning/afternoon trips to the bank). Same
    # story as drops — was its own CheckDeposit table; now a kind.
    "check_deposit":  ("checks_deposit",         "check deposit",        "deposits"),
}

def _line_item_kind_or_404(kind):
    if kind not in _LINE_ITEM_KINDS:
        abort(404)
    return _LINE_ITEM_KINDS[kind]

def _recompute_line_items_total(kind, store_id, report_date):
    """Sum DailyLineItem rows of the given kind and push the total onto
    the matching DailyReport field. Same contract as the drops /
    check-deposits helpers."""
    field, _, _ = _LINE_ITEM_KINDS[kind]
    total = (db.session.query(db.func.coalesce(db.func.sum(DailyLineItem.amount), 0.0))
             .filter_by(store_id=store_id, report_date=report_date, kind=kind).scalar()) or 0.0
    rpt = _ensure_daily_report(store_id, report_date)
    setattr(rpt, field, float(total))
    rpt.updated_at = datetime.utcnow()
    return total

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

@app.route("/daily/<string:ds>",methods=["GET","POST"])
@admin_required
def daily_report(ds):
    user=current_user(); sid=session["store_id"]
    store = current_store()
    try: report_date=datetime.strptime(ds,"%Y-%m-%d").date()
    except ValueError: flash("Invalid date.","error"); return redirect(url_for("daily_list"))
    report=DailyReport.query.filter_by(store_id=sid,report_date=report_date).first()
    mt_rows={r.company:r for r in MoneyTransferSummary.query.filter_by(store_id=sid,report_date=report_date).all()}
    companies = store_mt_companies(store)
    # Auto-sum the per-transfer ledger for every company configured on the
    # store — not just the old hardcoded trio. Includes federal_tax now.
    auto_mt={}
    for co in companies:
        rows = Transfer.query.filter(
            Transfer.store_id == sid, Transfer.company == co,
            Transfer.send_date == report_date,
            Transfer.status.notin_(["Canceled", "Rejected"]),
        ).all()
        auto_mt[co] = {
            "amount":     sum(r.send_amount   for r in rows),
            "fees":       sum(r.fee           for r in rows),
            "commission": sum(r.commission    for r in rows),
            "federal_tax":sum((r.federal_tax or 0) for r in rows),
            "count":      len(rows),
        }
    # Drops + Check Deposits used to live in their own DailyDrop /
    # CheckDeposit tables. They're now `kind='drop'` and
    # `kind='check_deposit'` rows in DailyLineItem, picked up by the
    # generic loader below. Legacy data is migrated at boot via
    # _migrate_legacy_line_item_tables().
    # Load + total every generic line-item kind in a single query, then
    # bucket in Python — cheaper than five separate SELECTs for a page
    # that usually has a handful of rows per kind.
    line_item_rows = (DailyLineItem.query
                      .filter_by(store_id=sid, report_date=report_date)
                      .order_by(DailyLineItem.kind, DailyLineItem.at_time).all())
    line_items = {k: [] for k in _LINE_ITEM_KINDS}
    for row in line_item_rows:
        if row.kind in line_items:
            line_items[row.kind].append(row)
    line_items_total = {k: sum(r.amount for r in rows) for k, rows in line_items.items()}
    if request.method=="POST":
        # Locked reports reject every write. We re-query to avoid TOCTOU with
        # the view-render read above (the user could lock from another tab).
        blocked = _reject_if_locked(sid, report_date, ds)
        if blocked is not None:
            return blocked
        if not report: report=DailyReport(store_id=sid,report_date=report_date); db.session.add(report)
        def fv(k): return float(request.form.get(k) or 0)
        for field in _DAILY_REPORT_FIELDS:
            setattr(report,field,fv(field))
        # Every DailyReport field backed by a generic line-item kind
        # is derived — pull from the line-item totals so a stale form
        # submission can't overwrite the truth. (Includes drops and
        # check deposits, which are now just two more kinds.)
        for kind, (field, _, _) in _LINE_ITEM_KINDS.items():
            setattr(report, field, float(line_items_total[kind]))
        report.notes=request.form.get("notes",""); report.updated_at=datetime.utcnow()
        # money_transfer is derived — the spreadsheet treats this line as a
        # subtotal of the MT table below. Compute from the submitted MT row
        # values so tampering with the read-only field in the UI can't
        # affect the saved total.
        mt_grand_total = 0.0
        for co in companies:
            key=co.lower().replace(" ","_").replace(".","")
            ex=mt_rows.get(co) or MoneyTransferSummary(store_id=sid,report_date=report_date,company=co)
            ex.amount       = fv(f"mt_amount_{key}")
            ex.fees         = fv(f"mt_fees_{key}")
            ex.commission   = fv(f"mt_commission_{key}")
            ex.federal_tax  = fv(f"mt_tax_{key}")
            mt_grand_total += (ex.amount or 0) + (ex.fees or 0) + (ex.commission or 0) + (ex.federal_tax or 0)
            db.session.add(ex)
        report.money_transfer = round(mt_grand_total, 2)
        db.session.commit()
        flash(f"Daily report for {report_date.strftime('%B %d, %Y')} saved.","success")
        return redirect(url_for("daily_list",month=report_date.month,year=report_date.year))
    # Resolve the lock actor's display name here so the template doesn't
    # have to join on User.
    locked_by_name = ""
    if report and report.locked_by:
        actor = db.session.get(User, report.locked_by)
        if actor:
            locked_by_name = actor.full_name or actor.username or ""
    return render_template("daily_report.html",user=user,report_date=report_date,
        report=report,mt_rows=mt_rows,companies=companies,auto_mt=auto_mt,
        line_items=line_items, line_items_total=line_items_total,
        locked_by_name=locked_by_name)

def _wants_json():
    """Client explicitly asked for JSON (AJAX from the drops widget).

    Keeping the drop routes dual-mode means they still work as plain HTML
    form posts if JS is off, so the feature degrades gracefully.
    """
    accept = request.accept_mimetypes
    return bool(accept and accept.best == "application/json")

def _line_items_json_payload(kind, store_id, report_date):
    """Current state of a generic line-item widget for a given day + kind."""
    rows = (DailyLineItem.query
            .filter_by(store_id=store_id, report_date=report_date, kind=kind)
            .order_by(DailyLineItem.at_time).all())
    total = sum(r.amount for r in rows)
    return {"ok": True, "kind": kind, "total": float(total),
            "items": [r.to_dict() for r in rows]}

@app.route("/daily/<string:ds>/line-items/<string:kind>/new", methods=["POST"])
@admin_required
def daily_line_item_new(ds, kind):
    """Append a single line item of the given kind for this report date.

    Kind must be one of _LINE_ITEM_KINDS; unknown kinds 404 so a
    malformed URL can't silently create an orphan row."""
    _, label, _ = _line_item_kind_or_404(kind)
    sid = session["store_id"]
    # Return-check paybacks come exclusively from the Return Checks
    # page (via /return-checks/<id>/payment). Blocking the manual
    # path here keeps the daily book in sync with that single source
    # of truth and matches the read-only UI the cashier sees.
    if kind == "return_payback":
        msg = ("Log return-check paybacks via Books → Return Checks "
               "(Add Payment). The daily-book line auto-populates.")
        if _wants_json():
            return jsonify({"ok": False, "error": msg}), 403
        flash(msg, "error")
        return redirect(url_for("daily_report", ds=ds))
    try: report_date = datetime.strptime(ds, "%Y-%m-%d").date()
    except ValueError:
        if _wants_json(): return jsonify({"ok": False, "error": "Invalid date."}), 400
        flash("Invalid date.", "error"); return redirect(url_for("daily_list"))
    blocked = _reject_if_locked(sid, report_date, ds)
    if blocked is not None: return blocked
    raw_time = request.form.get("at_time", "").strip()
    raw_amt  = request.form.get("amount", "").strip()
    err = None
    at_time = amount = None
    try:
        at_time = datetime.strptime(raw_time, "%H:%M").time()
    except ValueError:
        err = "Enter a valid time (HH:MM)."
    if err is None:
        try:
            amount = float(raw_amt)
            if amount <= 0: raise ValueError
        except ValueError:
            err = "Amount must be greater than zero."
    if err:
        if _wants_json(): return jsonify({"ok": False, "error": err}), 400
        flash(err, "error"); return redirect(url_for("daily_report", ds=ds))
    db.session.add(DailyLineItem(
        store_id=sid, report_date=report_date, kind=kind,
        at_time=at_time, amount=amount,
        note=request.form.get("note", "").strip()[:120],
        created_by=current_user().id,
    ))
    db.session.flush()
    _recompute_line_items_total(kind, sid, report_date)
    db.session.commit()
    if _wants_json():
        return jsonify(_line_items_json_payload(kind, sid, report_date))
    flash(f"{label.capitalize()} of ${amount:,.2f} at {at_time.strftime('%H:%M')} added.", "success")
    return redirect(url_for("daily_report", ds=ds))

@app.route("/daily/<string:ds>/line-items/<string:kind>/<int:item_id>/delete", methods=["POST"])
@admin_required
def daily_line_item_delete(ds, kind, item_id):
    """Delete a single line item and refresh the rolled-up total."""
    _, label, _ = _line_item_kind_or_404(kind)
    sid = session["store_id"]
    try: report_date = datetime.strptime(ds, "%Y-%m-%d").date()
    except ValueError:
        if _wants_json(): return jsonify({"ok": False, "error": "Invalid date."}), 400
        flash("Invalid date.", "error"); return redirect(url_for("daily_list"))
    blocked = _reject_if_locked(sid, report_date, ds)
    if blocked is not None: return blocked
    row = (DailyLineItem.query
           .filter_by(id=item_id, store_id=sid,
                      report_date=report_date, kind=kind)
           .first_or_404())
    # Return-check-linked paybacks are owned by the Return Checks page
    # — letting the cashier delete them here would diverge the daily
    # book from the source of truth. Front-end hides the Remove button
    # for these rows; this is the server-side guard against a hand-
    # crafted POST.
    if row.return_check_id is not None:
        msg = ("This payback is linked to a return check. Remove it "
               "from Books → Return Checks (delete the payment).")
        if _wants_json():
            return jsonify({"ok": False, "error": msg}), 403
        flash(msg, "error")
        return redirect(url_for("daily_report", ds=ds))
    db.session.delete(row)
    db.session.flush()
    _recompute_line_items_total(kind, sid, report_date)
    db.session.commit()
    if _wants_json():
        return jsonify(_line_items_json_payload(kind, sid, report_date))
    flash(f"{label.capitalize()} deleted.", "success")
    return redirect(url_for("daily_report", ds=ds))

@app.route("/daily/<string:ds>/lock", methods=["POST"])
@admin_required
def daily_report_lock(ds):
    """Lock a daily report so it stops accepting writes. Intended signal:
    'this day's books are closed.' Creates the DailyReport row if it
    doesn't exist yet so the user can lock an empty day on purpose."""
    sid = session["store_id"]
    try: report_date = datetime.strptime(ds, "%Y-%m-%d").date()
    except ValueError:
        flash("Invalid date.", "error"); return redirect(url_for("daily_list"))
    rpt = _ensure_daily_report(sid, report_date)
    if not rpt.locked_at:
        rpt.locked_at = datetime.utcnow()
        rpt.locked_by = current_user().id
        rpt.updated_at = datetime.utcnow()
        db.session.commit()
        flash(f"Daily report for {report_date.strftime('%B %d, %Y')} locked.", "success")
    return redirect(url_for("daily_report", ds=ds))

@app.route("/daily/<string:ds>/unlock", methods=["POST"])
@admin_required
def daily_report_unlock(ds):
    """Unlock a daily report. Admin-only; same gate as locking so an
    employee on shift can't undo a close."""
    sid = session["store_id"]
    try: report_date = datetime.strptime(ds, "%Y-%m-%d").date()
    except ValueError:
        flash("Invalid date.", "error"); return redirect(url_for("daily_list"))
    rpt = DailyReport.query.filter_by(store_id=sid, report_date=report_date).first()
    if rpt and rpt.locked_at:
        rpt.locked_at = None
        rpt.locked_by = None
        rpt.updated_at = datetime.utcnow()
        db.session.commit()
        flash(f"Daily report for {report_date.strftime('%B %d, %Y')} unlocked.", "success")
    return redirect(url_for("daily_report", ds=ds))

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
          "over_short":sum(r.over_short for r in daily_rows),
          # Net G/L for the month from the ReturnCheck workflow
          # (recoveries minus losses+fraud, by status_changed_on).
          # Stored as the signed P&L amount; the monthly_report
          # template renders it as a locked, editable-looking field.
          "return_check_gl":_return_check_monthly_pl(sid, year, month)}
    # Auto-feed every category in _BANK_CATEGORY_PL_FIELD into its
    # mapped P&L column. Multiple slugs may share one column (e.g.
    # bank_charge / bank_charge_210 / bank_charge_230 all feed
    # bank_charges_total) — sum per-slug into the field. Conditional
    # LOCK below preserves manual entry when the auto value is 0.
    for slug, field in _BANK_CATEGORY_PL_FIELD.items():
        auto[field] = (auto.get(field, 0) or 0) + _bank_charges_for_month(
            sid, year, month, slug)
    # Two-level breakdown for the expandable bank-charge view: groups
    # transactions by description, each group expandable to its rows.
    auto["bank_charges_breakdown"] = _bank_charges_breakdown_for_month(
        sid, year, month)
    if request.method=="POST":
        if not report: report=MonthlyFinancial(store_id=sid,year=year,month=month); db.session.add(report)
        def fv(k): return float(request.form.get(k) or 0)
        # Fields that are sums of the store's daily books for this month.
        # The template shows them as readonly, and the server forces them
        # to the auto sum here — so a tampered POST (or a stale form
        # submission after a daily-book edit) can't override the truth.
        LOCKED_FIELDS = {
            "cash_purchases", "check_purchases",
            "cash_expenses", "check_expenses", "cash_payroll",
            # Check Cashing Fees is the per-day fee receipts column on
            # DailyReport — adding it here means the monthly P&L always
            # mirrors what the cashier logged daily and a stale or
            # tampered POST can't override the truth.
            "check_cashing_fees",
            # Net G/L from the ReturnCheck workflow (recoveries minus
            # losses+fraud, by status_changed_on within the month).
            # See _return_check_monthly_pl().
            "return_check_gl",
        }
        # Bank-derived fields lock conditionally — only when there's
        # at least one tagged transaction in the month. Stores without
        # bank sync (or with no charges in this month) keep manual entry.
        for field in _BANK_CATEGORY_PL_FIELD.values():
            if auto.get(field, 0) > 0:
                LOCKED_FIELDS.add(field)
        for f in ["taxable_sales","non_taxable","bill_payment_charge","phone_recargas","boost_mobile",
            "check_cashing_fees","return_check_hold_fees","rebates_commissions","mt_commission_in_bank",
            "other_income_1","other_income_2","other_income_3","cash_purchases","check_purchases",
            "cash_expenses","check_expenses","cash_payroll","bank_charges_total",
            "credit_card_fees","money_order_rent","emaginenet_tech","irs_payroll_tax","texas_workforce",
            "other_taxes","accounting_charges","return_check_gl","other_expense_1","other_expense_2",
            "other_expense_3","other_expense_4","other_expense_5","over_short",
            "borrowed_money_return","profit_distributed","cash_carry_forward"]:
            if f in LOCKED_FIELDS:
                setattr(report, f, float(auto.get(f, 0)))
            else:
                setattr(report, f, fv(f))
        report.notes=request.form.get("notes",""); report.updated_at=datetime.utcnow()
        db.session.commit(); flash(f"P&L for {calendar.month_name[month]} {year} saved.","success")
        return redirect(url_for("monthly_list"))
    return render_template("monthly_report.html",user=user,year=year,month=month,
        month_name=calendar.month_name[month],report=report,auto=auto)

@app.route("/monthly/new")
@admin_required
def monthly_new():
    today=date.today(); return redirect(url_for("monthly_report",year=today.year,month=today.month))


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
    """Sum the still-owed balance of return checks marked `status_value`
    (typically 'loss' or 'fraud') whose status_changed_on falls in
    [start, end]. Subtracts payments already received against each
    parent — partial recoveries before the close were already booked
    as recoveries in their own months.
    """
    rows = (db.session.query(ReturnCheck.id, ReturnCheck.amount)
            .filter(
                ReturnCheck.store_id.in_(store_ids),
                ReturnCheck.status == status_value,
                ReturnCheck.status_changed_on >= start,
                ReturnCheck.status_changed_on <= end,
            ).all())
    if not rows:
        return 0.0
    rc_ids = [rid for rid, _ in rows]
    # Sum payments per parent, all in one query so we don't N+1
    # for stores with lots of write-offs.
    paid_rows = (db.session.query(
        ReturnCheckPayment.return_check_id,
        db.func.coalesce(db.func.sum(ReturnCheckPayment.amount), 0.0),
    ).filter(ReturnCheckPayment.return_check_id.in_(rc_ids))
     .group_by(ReturnCheckPayment.return_check_id).all())
    paid_by = {rid: float(s or 0.0) for rid, s in paid_rows}
    total = 0.0
    for rid, amt in rows:
        total += max(0.0, float(amt or 0.0) - paid_by.get(rid, 0.0))
    return total

def _return_check_period_aggregates(store_ids, start, end):
    """Sum recoveries (by payment date) and losses+fraud (by parent
    status-change date), plus the still-pending balance.

    Recoveries are measured at the PAYMENT level — a $300 installment
    in April and $400 in May contribute to those months separately,
    even though the parent ReturnCheck is the same row. This matches
    the user's mental model: money received this month = recovery
    this month, regardless of when the original check bounced.

    Losses + fraud are measured at the parent level — they're a
    single closing event, not a stream. The amount is the REMAINING
    balance at the time of the write-off (parent.amount minus
    payments already received), so a partially-recovered check that
    eventually goes bad only reports the unrecovered portion as the
    loss.

    Empty store list returns zeros — caller doesn't need to short-
    circuit. Returns gain-positive `net_gl` (used by owner dashboard);
    `_return_check_monthly_pl` flips the sign for the P&L expense
    column.
    """
    if not store_ids:
        return {"recoveries": 0.0, "losses": 0.0, "fraud": 0.0,
                "net_gl": 0.0, "pending": 0.0, "pending_count": 0}

    # Recoveries: Σ payments by paid_on, joined to parent for the
    # store filter. Note the payment itself doesn't carry store_id —
    # the parent does — so we join through.
    rec = db.session.query(
        db.func.coalesce(db.func.sum(ReturnCheckPayment.amount), 0.0)
    ).join(
        ReturnCheck, ReturnCheckPayment.return_check_id == ReturnCheck.id
    ).filter(
        ReturnCheck.store_id.in_(store_ids),
        ReturnCheckPayment.paid_on >= start,
        ReturnCheckPayment.paid_on <= end,
    ).scalar() or 0.0

    # Losses + fraud: closed ReturnChecks whose status_changed_on falls
    # in the window. The contribution is the REMAINING balance, not
    # the original amount — partial recoveries before the close were
    # already booked as recoveries on their own months. The summing
    # logic lives in the module-level _return_check_writeoff_total
    # helper so it can be unit-tested without spinning up the parent.
    loss  = _return_check_writeoff_total(store_ids, start, end, "loss")
    fraud = _return_check_writeoff_total(store_ids, start, end, "fraud")

    pending_q = db.session.query(
        db.func.coalesce(db.func.sum(ReturnCheck.amount), 0.0),
        db.func.count(ReturnCheck.id),
    ).filter(
        ReturnCheck.store_id.in_(store_ids),
        ReturnCheck.status == "pending",
        ReturnCheck.bounced_on <= end,
    ).first()
    pending_amount_total = float(pending_q[0] or 0.0)
    pending_count = int(pending_q[1] or 0)
    # Subtract installments already received against pending parents
    # so the "Pending balance" KPI shows the OUTSTANDING owed, not
    # the original face value.
    if pending_count > 0:
        pending_paid = (db.session.query(
            db.func.coalesce(db.func.sum(ReturnCheckPayment.amount), 0.0)
        ).join(ReturnCheck,
               ReturnCheckPayment.return_check_id == ReturnCheck.id)
         .filter(
             ReturnCheck.store_id.in_(store_ids),
             ReturnCheck.status == "pending",
             ReturnCheck.bounced_on <= end,
         ).scalar() or 0.0)
        pending = max(0.0, pending_amount_total - float(pending_paid))
    else:
        pending = 0.0

    return {
        "recoveries":   float(rec),
        "losses":       float(loss),
        "fraud":        float(fraud),
        "net_gl":       float(rec) - float(loss) - float(fraud),
        "pending":      pending,
        "pending_count": pending_count,
    }


def _return_check_aging_buckets(store_ids, today=None):
    """Pending balance sliced into 0–30 / 31–60 / 61–90 / 90+ day
    buckets by `bounced_on`. Helps the owner spot stale receivables
    that probably won't recover."""
    if today is None:
        today = date.today()
    if not store_ids:
        return [
            {"label": "0–30 d",  "amount": 0.0, "count": 0},
            {"label": "31–60 d", "amount": 0.0, "count": 0},
            {"label": "61–90 d", "amount": 0.0, "count": 0},
            {"label": "90+ d",   "amount": 0.0, "count": 0},
        ]
    rows = ReturnCheck.query.filter(
        ReturnCheck.store_id.in_(store_ids),
        ReturnCheck.status == "pending",
    ).all()
    buckets = [
        {"label": "0–30 d",  "amount": 0.0, "count": 0, "max": 30},
        {"label": "31–60 d", "amount": 0.0, "count": 0, "max": 60},
        {"label": "61–90 d", "amount": 0.0, "count": 0, "max": 90},
        {"label": "90+ d",   "amount": 0.0, "count": 0, "max": None},
    ]
    for r in rows:
        age = (today - r.bounced_on).days if r.bounced_on else 0
        for b in buckets:
            if b["max"] is None or age <= b["max"]:
                b["amount"] += float(r.amount or 0.0)
                b["count"]  += 1
                break
    for b in buckets:
        b.pop("max", None)
    return buckets


def _bank_charges_for_month(store_id, year, month, category_slug):
    """Sum the absolute amount of BankTransactions tagged with the given
    category_slug for the given month. Generic over any bank category
    (despite the historical name) — used by every entry in
    _BANK_CATEGORY_PL_FIELD to feed the monthly P&L.

    Stored amounts are signed (debits negative); P&L expense columns
    use positive numbers, so we abs().

    Returns 0.0 when no transactions match — the monthly_report route
    only LOCKs the field when this is > 0, leaving the manual P&L
    value in place for stores without bank sync.
    """
    month_start = datetime(year, month, 1)
    month_end_d = monthrange(year, month)[1]
    month_end = datetime(year, month, month_end_d, 23, 59, 59)
    cents = (db.session.query(
        db.func.coalesce(db.func.sum(BankTransaction.amount_cents), 0)
    ).filter(
        BankTransaction.store_id == store_id,
        BankTransaction.category_slug == category_slug,
        BankTransaction.posted_at >= month_start,
        BankTransaction.posted_at <= month_end,
    ).scalar())
    return abs(float(cents or 0)) / 100.0

def _bank_charges_breakdown_for_month(store_id, year, month):
    """Two-level breakdown feeding the expandable Bank Charges block on
    the monthly P&L. Groups bank-charge transactions by description
    string; each group exposes its individual rows.

    Returns a list of dicts:
      [
        {"description": "REMOTE DEPOSIT FEE",
         "total":       2.10,
         "count":       1,
         "transactions": [
           {"posted_at": datetime, "amount": 2.10,
            "account_label": "••0230" or nickname,
            "description": "REMOTE DEPOSIT FEE 04/29"},
         ]},
        ...
      ]

    Sorted by total descending so the biggest contributor reads first.
    Pulls every slug listed in _BANK_CATEGORY_PL_FIELD that maps to
    bank_charges_total — so any future built-in rule that targets a
    bank-charge category automatically lands in the breakdown.
    """
    month_start = datetime(year, month, 1)
    month_end_d = monthrange(year, month)[1]
    month_end = datetime(year, month, month_end_d, 23, 59, 59)
    bank_charge_slugs = [slug for slug, field in _BANK_CATEGORY_PL_FIELD.items()
                         if field == "bank_charges_total"]
    if not bank_charge_slugs:
        return []
    rows = (BankTransaction.query
            .filter(
                BankTransaction.store_id == store_id,
                BankTransaction.category_slug.in_(bank_charge_slugs),
                BankTransaction.posted_at >= month_start,
                BankTransaction.posted_at <= month_end,
            )
            .order_by(BankTransaction.posted_at.desc()).all())
    if not rows:
        return []
    # Map account ids → label so we don't N+1 lookup per transaction.
    acct_ids = {r.stripe_bank_account_id for r in rows if r.stripe_bank_account_id}
    accts = {a.id: a for a in StripeBankAccount.query.filter(
        StripeBankAccount.id.in_(acct_ids)).all()} if acct_ids else {}
    # Group by description. The exact full description is the key —
    # operators want each variant visible (e.g. "REMOTE DEPOSIT FEE
    # 04/29" and "REMOTE DEPOSIT FEE 05/02" group separately if the
    # bank includes the date in the string). If you want strings to
    # collapse on common prefixes that's a future enhancement.
    groups = {}
    for r in rows:
        key = r.description or "(no description)"
        g = groups.setdefault(key, {"description": key, "total": 0.0,
                                     "count": 0, "transactions": []})
        amt = abs(float(r.amount_cents or 0) / 100.0)
        g["total"] += amt
        g["count"] += 1
        acct = accts.get(r.stripe_bank_account_id)
        g["transactions"].append({
            "posted_at": r.posted_at,
            "amount":    amt,
            "description": r.description or "",
            "account_label": acct.label if acct else "",
        })
    return sorted(groups.values(), key=lambda g: g["total"], reverse=True)

def _return_check_monthly_pl(store_id, year, month):
    """Signed value for the monthly P&L's Return Check (G/L) line,
    using EXPENSE convention so it slots correctly into the
    expense column on monthly_report (which subtracts from net income).

      positive  → net loss for the month (losses + fraud > recoveries)
      negative  → net gain for the month (recoveries > losses + fraud)

    Note: _return_check_period_aggregates['net_gl'] uses the OPPOSITE
    convention (positive = gain) because that's what the owner
    dashboard shows. We deliberately negate here so each consumer
    reads the right sign for its context.
    """
    start = date(year, month, 1)
    end   = date(year, month, monthrange(year, month)[1])
    agg = _return_check_period_aggregates([store_id], start, end)
    # Flip the sign: dashboard's "net_gl" is gain-positive, P&L line
    # is loss-positive (expense convention).
    return -agg["net_gl"]


def _return_check_monthly_series(store_ids, today=None):
    """12-month bars for the owner dashboard: per-month recoveries
    (positive) and losses+fraud (negative). Labels are 'YYYY-MM' so
    ApexCharts renders them as a date axis."""
    if today is None:
        today = date.today()
    months = []
    y, m = today.year, today.month
    for _ in range(12):
        months.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    months.reverse()  # oldest → newest
    labels, recoveries, losses = [], [], []
    if not store_ids:
        for (yy, mm) in months:
            labels.append(f"{yy:04d}-{mm:02d}")
            recoveries.append(0.0)
            losses.append(0.0)
        return labels, recoveries, losses
    for (yy, mm) in months:
        s = date(yy, mm, 1)
        e = date(yy, mm, monthrange(yy, mm)[1])
        agg = _return_check_period_aggregates(store_ids, s, e)
        labels.append(f"{yy:04d}-{mm:02d}")
        recoveries.append(round(agg["recoveries"], 2))
        # Combine loss + fraud — both are write-offs from the P&L's POV.
        losses.append(round(agg["losses"] + agg["fraud"], 2))
    return labels, recoveries, losses


def _return_check_list_payload(store_id, status, query, date_from, date_to):
    """Filtered list rows for /return-checks. Status filter values:
    'pending' (default), 'recovered', 'loss', 'fraud', 'closed'
    (recovered+loss+fraud), 'all'."""
    q = ReturnCheck.query.filter_by(store_id=store_id)
    if status == "pending":
        q = q.filter(ReturnCheck.status == "pending")
    elif status == "recovered":
        q = q.filter(ReturnCheck.status == "recovered")
    elif status == "loss":
        q = q.filter(ReturnCheck.status == "loss")
    elif status == "fraud":
        q = q.filter(ReturnCheck.status == "fraud")
    elif status == "closed":
        q = q.filter(ReturnCheck.status.in_(["recovered", "loss", "fraud"]))
    # status="all" (or anything unknown) → no status filter

    if query:
        ql = "%{}%".format(query.lower())
        q = q.filter(db.or_(
            db.func.lower(ReturnCheck.customer_name).like(ql),
            db.func.lower(ReturnCheck.check_number).like(ql),
            db.func.lower(ReturnCheck.payer_bank).like(ql),
        ))
    if date_from:
        try:
            df = datetime.strptime(date_from, "%Y-%m-%d").date()
            q = q.filter(ReturnCheck.bounced_on >= df)
        except (ValueError, TypeError):
            pass
    if date_to:
        try:
            dt = datetime.strptime(date_to, "%Y-%m-%d").date()
            q = q.filter(ReturnCheck.bounced_on <= dt)
        except (ValueError, TypeError):
            pass
    # Pending first (sorted by oldest bounced_on so stale items rise to
    # the top), then closed rows by most-recently-changed.
    return q.order_by(
        # Pending sorts before closed via the custom case() expression
        # because all closed rows have status_changed_on set, and we
        # want pending at the top regardless of how old they are.
        db.case((ReturnCheck.status == "pending", 0), else_=1),
        db.case((ReturnCheck.status == "pending", ReturnCheck.bounced_on),
                else_=None).asc(),
        ReturnCheck.status_changed_on.desc().nullslast()
            if hasattr(ReturnCheck.status_changed_on.desc(), "nullslast")
            else ReturnCheck.status_changed_on.desc(),
        ReturnCheck.bounced_on.desc(),
    ).all()


@app.route("/return-checks")
@admin_required
def return_checks():
    """Searchable list of return checks for the current store, with a
    pending-balance KPI strip and inline status filter (Pending /
    Recovered / Loss / Fraud / All).

    Same `?partial=1` JSON contract as /transfers and /owner/locations
    so the live-search swap works without a full page reload.
    """
    user = current_user()
    sid  = session["store_id"]
    today_d = date.today()
    status = (request.args.get("status") or "pending").lower()
    if status not in ("pending", "recovered", "loss", "fraud", "closed", "all"):
        status = "pending"
    query = (request.args.get("q") or "").strip()
    date_from = request.args.get("from") or ""
    date_to   = request.args.get("to") or ""

    rows = _return_check_list_payload(sid, status, query, date_from, date_to)

    # Month-to-date aggregates for the KPI strip.
    month_start = date(today_d.year, today_d.month, 1)
    mtd = _return_check_period_aggregates([sid], month_start, today_d)
    aging = _return_check_aging_buckets([sid], today=today_d)

    if request.args.get("partial") == "1":
        html = render_template("_return_checks_table.html",
                               rows=rows, today=today_d)
        return jsonify({"html": html, "matched": len(rows),
                        "status": status, "query": query,
                        "pending_balance": round(mtd["pending"], 2),
                        "pending_count":   mtd["pending_count"]})

    return render_template("return_checks.html",
        user=user, today=today_d, rows=rows,
        status=status, query=query,
        date_from=date_from, date_to=date_to,
        mtd=mtd, aging=aging,
    )


@app.route("/return-checks/new", methods=["POST"])
@admin_required
def return_check_new():
    sid = session["store_id"]
    user = current_user()
    bounced_on_s = (request.form.get("bounced_on") or "").strip()
    customer = (request.form.get("customer_name") or "").strip()
    amount_s = (request.form.get("amount") or "").strip()
    if not bounced_on_s or not customer or not amount_s:
        flash("Date, customer, and amount are required.", "error")
        return redirect(url_for("return_checks"))
    try:
        bounced_on = datetime.strptime(bounced_on_s, "%Y-%m-%d").date()
    except ValueError:
        flash("Invalid bounce date.", "error")
        return redirect(url_for("return_checks"))
    try:
        amount = float(amount_s)
    except ValueError:
        flash("Invalid amount.", "error")
        return redirect(url_for("return_checks"))
    if amount <= 0:
        flash("Amount must be greater than zero.", "error")
        return redirect(url_for("return_checks"))

    rc = ReturnCheck(
        store_id=sid,
        bounced_on=bounced_on,
        customer_name=customer[:120],
        check_number=(request.form.get("check_number") or "").strip()[:40],
        payer_bank=(request.form.get("payer_bank") or "").strip()[:120],
        amount=amount,
        notes=(request.form.get("notes") or "").strip(),
        status="pending",
        created_by=user.id,
    )
    db.session.add(rc)
    db.session.commit()
    flash(f"Return check logged for {rc.customer_name} (${rc.amount:,.2f}).",
          "success")
    return redirect(url_for("return_checks"))


def _get_owned_return_check(rc_id):
    """Lookup a ReturnCheck scoped to the current store. Returns
    (rc, error_response) — exactly one is non-None. Used by the
    mark-* + edit + delete routes so cross-store IDs can't slip in."""
    sid = session["store_id"]
    rc = db.session.get(ReturnCheck, rc_id)
    if rc is None or rc.store_id != sid:
        flash("Return check not found.", "error")
        return None, redirect(url_for("return_checks"))
    return rc, None


_PAYMENT_METHODS = ("cash", "check", "zelle", "wire", "money_order", "other")


def _payback_note_for(rc, payment):
    """Human-readable note for the auto-created DailyLineItem so the
    daily-book widget shows useful context. Each installment gets its
    own line, so the note describes THAT installment specifically."""
    bits = [f"Return check from {rc.customer_name}"]
    if rc.check_number:
        bits.append(f"#{rc.check_number}")
    if payment.payment_method:
        bits.append(f"via {payment.payment_method}")
    if payment.note:
        bits.append(payment.note)
    return " · ".join(bits)[:120]


def _create_daily_payback_for(rc, payment):
    """Create the shadow DailyLineItem for one ReturnCheckPayment.

    One installment → one line item, on the payment's `paid_on`. The
    FK on DailyLineItem points back at the parent ReturnCheck (not
    the payment) so the daily-book widget can show "this came from
    a return check" context without joining through the payment.
    The line item rows for repeated payments to the same parent are
    differentiated by their distinct timestamps + amounts.

    Returns the created DailyLineItem (caller does NOT need to add to
    session — already added).
    """
    user = current_user()
    li = DailyLineItem(
        store_id=rc.store_id,
        report_date=payment.paid_on,
        kind="return_payback",
        at_time=datetime.utcnow().time(),
        amount=float(payment.amount or 0.0),
        note=_payback_note_for(rc, payment),
        return_check_id=rc.id,
        created_by=user.id if user else None,
    )
    db.session.add(li)
    return li


def _delete_daily_paybacks_for_payment(rc, payment_amount, payment_paid_on):
    """Find and delete the shadow line item for a specific payment.

    Match by (return_check_id, report_date, amount). Since multiple
    payments on the SAME date for the SAME amount on the SAME parent
    is possible-but-rare, we delete just the first match — re-running
    deletes the next one if needed. Better than ambiguously deleting
    all of them.
    """
    li = DailyLineItem.query.filter_by(
        store_id=rc.store_id,
        return_check_id=rc.id,
        kind="return_payback",
        report_date=payment_paid_on,
        amount=float(payment_amount),
    ).first()
    if li is not None:
        db.session.delete(li)


@app.route("/return-checks/<int:rc_id>/payment", methods=["POST"])
@admin_required
def return_check_payment_new(rc_id):
    """Log one installment of repayment.

    Validates the amount fits within the still-outstanding balance.
    On a fully-paid parent we auto-flip status='recovered' so the
    admin doesn't have to click a separate "close" button — and the
    P&L doesn't double-count: the closing event simply marks WHEN it
    became fully recovered, the actual recovered $ already counted at
    the payment level.
    """
    rc, err = _get_owned_return_check(rc_id)
    if err is not None:
        return err
    if rc.status in ("loss", "fraud"):
        flash("This return check is closed (loss/fraud) — reopen it first.",
              "error")
        return redirect(url_for("return_checks"))

    amt_s    = (request.form.get("amount") or "").strip()
    paid_s   = (request.form.get("paid_on") or "").strip()
    method   = (request.form.get("payment_method") or "").strip().lower()
    note     = (request.form.get("note") or "").strip()
    if method and method not in _PAYMENT_METHODS:
        method = "other"
    try:
        amt = float(amt_s)
    except ValueError:
        flash("Invalid payment amount.", "error")
        return redirect(url_for("return_checks"))
    remaining = rc.remaining
    if amt <= 0:
        flash("Payment amount must be greater than zero.", "error")
        return redirect(url_for("return_checks"))
    # Allow a tiny float epsilon on the cap so $999.999... rounding
    # from the front-end doesn't trip the validation.
    if amt > remaining + 0.005:
        flash(
            f"Payment $ {amt:,.2f} exceeds remaining balance "
            f"${remaining:,.2f}. Lower the amount or split into "
            f"multiple payments.", "error")
        return redirect(url_for("return_checks"))
    try:
        paid_on = (datetime.strptime(paid_s, "%Y-%m-%d").date()
                   if paid_s else date.today())
    except ValueError:
        flash("Invalid payment date.", "error")
        return redirect(url_for("return_checks"))

    user = current_user()
    payment = ReturnCheckPayment(
        return_check_id=rc.id,
        amount=amt,
        paid_on=paid_on,
        payment_method=method,
        note=note[:200],
        created_by=user.id if user else None,
    )
    # Snapshot the prior total BEFORE adding the new row — the
    # `payments` relationship is lazy-loaded once and won't see the
    # uncommitted insert without an explicit refresh. Cheaper to just
    # add the new payment's amount to what we already had.
    prior_total = rc.recovered_total
    db.session.add(payment)
    db.session.flush()
    _create_daily_payback_for(rc, payment)
    # Auto-close when the cumulative payments reach the original
    # amount. Use the new payment's date as status_changed_on so the
    # dashboard's "marked recovered" badge ties back to the same day.
    new_total = prior_total + amt
    if new_total + 0.005 >= float(rc.amount or 0.0):
        rc.status = "recovered"
        rc.status_changed_on = paid_on
    db.session.commit()
    flash(
        f"Logged ${amt:,.2f} payment for {rc.customer_name}"
        + (f" via {method}" if method else "") + ".",
        "success")
    return redirect(url_for("return_checks"))


@app.route("/return-checks/<int:rc_id>/payment/<int:pid>/delete",
           methods=["POST"])
@admin_required
def return_check_payment_delete(rc_id, pid):
    """Remove one installment. Drops the shadow daily-book line item
    and, if the parent was auto-flipped to 'recovered' but the
    deletion now leaves the balance > 0, walks status back to
    'pending' so the row reappears in the active list."""
    rc, err = _get_owned_return_check(rc_id)
    if err is not None:
        return err
    payment = db.session.get(ReturnCheckPayment, pid)
    if payment is None or payment.return_check_id != rc.id:
        flash("Payment not found.", "error")
        return redirect(url_for("return_checks"))
    _delete_daily_paybacks_for_payment(rc, payment.amount, payment.paid_on)
    db.session.delete(payment)
    db.session.flush()
    # If this was a recovered case and the deletion drops below full
    # payment, reopen so the admin's UI stays accurate.
    if rc.status == "recovered" and rc.recovered_total + 0.005 < float(rc.amount or 0.0):
        rc.status = "pending"
        rc.status_changed_on = None
    db.session.commit()
    flash("Payment removed.", "success")
    return redirect(url_for("return_checks"))


def _close_as_writeoff(rc_id, status):
    """Shared body for /loss and /fraud: only the status word + flash
    message differ. The remaining balance (amount − payments) is what
    lands on the P&L for status_changed_on's month."""
    rc, err = _get_owned_return_check(rc_id)
    if err is not None:
        return err
    on_s = (request.form.get("status_changed_on") or "").strip()
    try:
        when = (datetime.strptime(on_s, "%Y-%m-%d").date()
                if on_s else date.today())
    except ValueError:
        flash("Invalid date.", "error")
        return redirect(url_for("return_checks"))
    rc.status = status
    rc.status_changed_on = when
    db.session.commit()
    label = "fraud" if status == "fraud" else "loss"
    flash(
        f"Marked {label}: {rc.customer_name} "
        f"(remaining balance ${rc.remaining:,.2f}).", "success")
    return redirect(url_for("return_checks"))


@app.route("/return-checks/<int:rc_id>/loss", methods=["POST"])
@admin_required
def return_check_loss(rc_id):
    return _close_as_writeoff(rc_id, "loss")


@app.route("/return-checks/<int:rc_id>/fraud", methods=["POST"])
@admin_required
def return_check_fraud(rc_id):
    return _close_as_writeoff(rc_id, "fraud")


@app.route("/return-checks/<int:rc_id>/reopen", methods=["POST"])
@admin_required
def return_check_reopen(rc_id):
    """Undo a recover / loss / fraud — returns the row to pending.
    Payments themselves are NOT deleted (they represent real money
    that came in); only the closing status is reverted. To remove an
    individual payment, use the payment-delete route."""
    rc, err = _get_owned_return_check(rc_id)
    if err is not None:
        return err
    rc.status = "pending"
    rc.status_changed_on = None
    db.session.commit()
    flash(f"Reopened: {rc.customer_name}.", "success")
    return redirect(url_for("return_checks"))


@app.route("/return-checks/<int:rc_id>/edit", methods=["POST"])
@admin_required
def return_check_edit(rc_id):
    rc, err = _get_owned_return_check(rc_id)
    if err is not None:
        return err
    customer = (request.form.get("customer_name") or "").strip()
    if customer:
        rc.customer_name = customer[:120]
    rc.check_number = (request.form.get("check_number") or "").strip()[:40]
    rc.payer_bank   = (request.form.get("payer_bank") or "").strip()[:120]
    rc.notes        = (request.form.get("notes") or "").strip()
    # Allow editing amount only on pending rows — once booked, the P&L
    # for the closed month is fixed and we don't want a quiet retroactive
    # change.
    if rc.status == "pending":
        amt_s = (request.form.get("amount") or "").strip()
        if amt_s:
            try:
                amt = float(amt_s)
                if amt > 0:
                    rc.amount = amt
            except ValueError:
                pass
        on_s = (request.form.get("bounced_on") or "").strip()
        if on_s:
            try:
                rc.bounced_on = datetime.strptime(on_s, "%Y-%m-%d").date()
            except ValueError:
                pass
    db.session.commit()
    flash("Return check updated.", "success")
    return redirect(url_for("return_checks"))


@app.route("/return-checks/<int:rc_id>/delete", methods=["POST"])
@admin_required
def return_check_delete(rc_id):
    rc, err = _get_owned_return_check(rc_id)
    if err is not None:
        return err
    # Sweep up the shadow line items first so the daily-book stays
    # consistent — the FK column on DailyLineItem isn't ON DELETE
    # CASCADE because we want to track who created which line item,
    # so the cleanup is explicit here.
    DailyLineItem.query.filter_by(
        store_id=rc.store_id,
        return_check_id=rc.id,
        kind="return_payback",
    ).delete(synchronize_session=False)
    db.session.delete(rc)
    db.session.commit()
    flash("Return check deleted.", "success")
    return redirect(url_for("return_checks"))


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

# ── Bank (Stripe Financial Connections) ─────────────────────────
@app.route("/bank")
@pro_required
def bank():
    user = current_user()
    store = current_store()
    sid = store.id
    stripe_accounts = (StripeBankAccount.query
                       .filter_by(store_id=sid, enabled=True)
                       .order_by(StripeBankAccount.connected_at.desc()).all())
    # Auto-refresh balances older than the staleness window so the page
    # always shows something close to live. Silent on failure.
    now = datetime.utcnow()
    stale = [a for a in stripe_accounts
             if not a.last_balance_as_of or
             (now - a.last_balance_as_of).total_seconds() > BANK_BALANCE_STALE_SECONDS]
    if stale and stripe_is_configured():
        try:
            refresh_bank_balances(store)
            stripe_accounts = (StripeBankAccount.query
                               .filter_by(store_id=sid, enabled=True)
                               .order_by(StripeBankAccount.connected_at.desc()).all())
        except Exception as e:
            app.logger.warning(f"bank() auto-refresh failed: {e}")
    # The tuple return shape from refresh_bank_balances is intentional —
    # the manual /bank/stripe/refresh route surfaces last_error in a flash
    # so operators can see why a refresh failed; the auto-refresh above
    # ignores it and renders silently.
    # Rate-limit state for the Sync transactions button. Read-only —
    # actual gate happens server-side in /bank/stripe/sync-transactions.
    sync_allowed, sync_reason, sync_retry_after = _can_sync_bank_transactions(store)
    today_count = (store.bank_sync_count_today or 0) if (
        store.bank_sync_count_date == datetime.utcnow().date()) else 0
    recent_txns = (BankTransaction.query.filter_by(store_id=sid)
                   .order_by(BankTransaction.posted_at.desc(),
                             BankTransaction.id.desc())
                   .limit(10).all())
    return render_template("bank.html", user=user,
        stripe_accounts=stripe_accounts,
        stripe_ready=stripe_is_configured(),
        stripe_publishable_key=stripe_publishable_key(),
        max_bank_accounts=MAX_BANK_ACCOUNTS_PER_STORE,
        recent_txns=recent_txns,
        sync_allowed=sync_allowed,
        sync_reason=sync_reason,
        sync_retry_after=sync_retry_after,
        sync_count_today=today_count,
        sync_max_per_day=MAX_BANK_SYNCS_PER_DAY,
        sync_last_at=store.bank_sync_last_at)

@app.route("/bank/stripe/connect", methods=["POST"])
@pro_required
def bank_stripe_connect():
    """Create a Stripe Financial Connections session and return its
    client_secret as JSON. The browser then opens the Stripe-hosted FC
    modal via stripe.js (collectFinancialConnectionsAccounts), which
    settles the linking flow and POSTs the user back to
    /bank/stripe/return?session_id=<id> on success.

    Stripe's FC API does NOT expose a server-side hosted URL — the
    browser drives the modal directly with the client_secret."""
    if not stripe_is_configured():
        return jsonify({"error": "Stripe isn't configured yet — ask the platform admin."}), 503
    if not stripe_publishable_key():
        return jsonify({"error": "STRIPE_PUBLISHABLE_KEY is not set; the FC modal can't initialize."}), 503
    store = current_store()
    # Enforce the per-store account cap before we even mint an FC
    # session. The UI already hides the button when at the cap, but
    # this is the authoritative check in case someone POSTs directly.
    existing_count = StripeBankAccount.query.filter_by(
        store_id=store.id, enabled=True).count()
    if existing_count >= MAX_BANK_ACCOUNTS_PER_STORE:
        return jsonify({
            "error": (f"You've reached the {MAX_BANK_ACCOUNTS_PER_STORE}-account "
                      "limit. Disconnect an account first to free up a slot."),
        }), 409
    try:
        customer_id = ensure_stripe_customer(store)
        fc_session = stripe.financial_connections.Session.create(
            account_holder={"type": "customer", "customer": customer_id},
            permissions=["balances", "transactions"],
            # Pre-fetch balances + transactions during the linking flow
            # itself — without this, balance.current is None on retrieve
            # and Transaction.list returns nothing until Stripe's async
            # fetcher catches up. Prefetch keeps the user inside the
            # Stripe modal until both feeds are populated.
            prefetch=["balances", "transactions"],
            filters={"countries": ["US"]},
            return_url=url_for("bank_stripe_return", _external=True),
        )
        # Remember the session id server-side too — gives us a fallback
        # path if Stripe.js can't echo the id back through the URL.
        session["fc_session_id"] = fc_session.id
        return jsonify({
            "clientSecret": fc_session.client_secret,
            "sessionId":    fc_session.id,
            "publishableKey": stripe_publishable_key(),
            "returnUrl":    url_for("bank_stripe_return", session_id=fc_session.id),
        })
    except stripe.error.StripeError as e:
        app.logger.error(f"FC session create failed: {e}")
        msg = e.user_message or str(e)
        return jsonify({"error": f"Could not start the bank connection: {msg}"}), 502

@app.route("/bank/stripe/return")
@pro_required
def bank_stripe_return():
    """Called by the browser after the FC modal finishes. Accepts
    session_id from the query string (Stripe.js path) or falls back to
    the server-side session value (for browsers that lose the query
    after a redirect chain)."""
    sid = session["store_id"]
    fc_session_id = (request.args.get("session_id")
                     or session.pop("fc_session_id", None))
    if not fc_session_id:
        flash("No active bank-link session found.", "error")
        return redirect(url_for("bank"))
    # Always clear the server-side copy now that we have an id in hand.
    session.pop("fc_session_id", None)
    try:
        fc_session = stripe.financial_connections.Session.retrieve(
            fc_session_id, expand=["accounts"])
        accounts = fc_session.accounts.data if hasattr(fc_session, "accounts") else []
        if not accounts:
            flash("No accounts were linked.", "error")
            return redirect(url_for("bank"))
        # Per-store cap. We honor existing enabled rows AND any of the
        # just-linked accounts that are already on file (re-link case),
        # then accept up to the remaining slots.
        existing_ids = {row.stripe_account_id for row in
                        StripeBankAccount.query.filter_by(
                            store_id=sid, enabled=True).all()}
        slots_remaining = MAX_BANK_ACCOUNTS_PER_STORE - len(existing_ids)
        kept = 0
        skipped = 0
        for acct_summary in accounts:
            already_linked = acct_summary.id in existing_ids
            if not already_linked and slots_remaining <= 0:
                skipped += 1
                continue
            # The session returns a trimmed account object; retrieve it fully
            # so we get balance and institution metadata.
            full = stripe.financial_connections.Account.retrieve(acct_summary.id)
            _upsert_fc_account(sid, full)
            # Subscribe to the transactions feature on each linked account.
            # Session-level permission alone is NOT enough — Stripe needs an
            # account-level subscription before it will populate Transaction
            # data (and before Transaction.list returns anything). Idempotent;
            # safe to call on re-link. Best-effort — we still consider the
            # account "kept" if the subscribe call fails.
            try:
                stripe.financial_connections.Account.subscribe(
                    acct_summary.id, features=["transactions"])
            except stripe.error.StripeError as e:
                app.logger.warning(
                    f"FC transactions subscribe failed for {acct_summary.id}: {e}")
            # Trigger an immediate refresh so the first sync picks up data
            # rather than waiting for Stripe's async fetcher.
            try:
                stripe.financial_connections.Account.refresh_account(
                    acct_summary.id, features=["transactions"])
            except stripe.error.StripeError as e:
                app.logger.warning(
                    f"FC transactions refresh failed for {acct_summary.id}: {e}")
            if not already_linked:
                slots_remaining -= 1
            kept += 1
        db.session.commit()
        # Immediately pull fresh balances + initial transaction window
        # (yesterday + today) for the newly-linked accounts. The initial
        # txn sync does NOT count against the per-store daily cap — it's
        # part of the connect flow, not a discretionary user action.
        try:
            refresh_bank_balances(current_store())
        except Exception as e:
            app.logger.warning(f"post-connect refresh failed: {e}")
        try:
            initial_since = datetime.combine(
                (datetime.utcnow() - timedelta(days=INITIAL_SYNC_DAYS_BACK)).date(),
                datetime.min.time())
            sync_bank_transactions(current_store(), since=initial_since)
        except Exception as e:
            app.logger.warning(f"post-connect initial txn sync failed: {e}")
        if skipped:
            flash((f"Connected {kept} account(s); skipped {skipped} because the "
                   f"per-store limit is {MAX_BANK_ACCOUNTS_PER_STORE}. Disconnect "
                   "an existing account to free a slot."), "warning")
        else:
            flash(f"Connected {kept} account(s) via Stripe.", "success")
    except stripe.error.StripeError as e:
        app.logger.error(f"FC session retrieve failed: {e}")
        flash(f"Stripe error while completing the link: {e.user_message or str(e)}", "error")
    return redirect(url_for("bank"))

@app.route("/bank/stripe/refresh", methods=["POST"])
@pro_required
def bank_stripe_refresh():
    """Manually refresh all connected account balances."""
    n, last_error = refresh_bank_balances(current_store())
    if n and not last_error:
        flash(f"Refreshed {n} account(s).", "success")
    elif n and last_error:
        flash(f"Refreshed {n} account(s); one or more failed: {last_error}", "warning")
    elif last_error:
        flash(f"Refresh failed: {last_error}", "error")
    else:
        flash("Nothing to refresh.", "error")
    return redirect(url_for("bank"))

@app.route("/bank/stripe/sync-transactions", methods=["POST"])
@pro_required
def bank_stripe_sync_transactions():
    """Pull new transactions for every connected account, gated by the
    per-store rate-limiter so we don't blow through Stripe billing.
    Each Transaction.list call is metered, and a single click can
    fan out to up to MAX_BANK_ACCOUNTS_PER_STORE accounts."""
    store = current_store()
    allowed, reason, retry_after = _can_sync_bank_transactions(store)
    if not allowed:
        flash(reason, "error")
        return redirect(url_for("bank"))
    new_rows, total, last_error = sync_bank_transactions(store)
    # Always record the sync attempt — Stripe billed us regardless of
    # how many rows came back. Caller's commit happens here.
    _record_bank_sync(store)
    db.session.commit()
    if last_error and not total:
        flash(f"Sync failed: {last_error}", "error")
    elif last_error:
        flash(f"Synced {new_rows} new transaction(s); one or more accounts errored: {last_error}",
              "warning")
    else:
        used = store.bank_sync_count_today
        remaining = MAX_BANK_SYNCS_PER_DAY - used
        flash((f"Synced {new_rows} new transaction(s) "
               f"({remaining} sync(s) remaining today)."),
              "success" if total else "info")
    return redirect(url_for("bank"))

@app.route("/bank/transactions")
@pro_required
def bank_transactions():
    """Paginated list of pulled bank transactions. Live-search per
    CLAUDE.md invariant #14: ?partial=1 returns JSON, full GET returns
    the page chrome."""
    store = current_store()
    sid = store.id
    is_partial = request.args.get("partial") == "1"
    page = max(1, request.args.get("page", default=1, type=int))
    per_page = 50
    q          = (request.args.get("q") or "").strip()
    account_id = request.args.get("account", type=int)
    date_from  = (request.args.get("date_from") or "").strip()
    date_to    = (request.args.get("date_to") or "").strip()

    qry = BankTransaction.query.filter_by(store_id=sid)
    if account_id:
        qry = qry.filter_by(stripe_bank_account_id=account_id)
    if q and len(q) >= 2:
        like = f"%{q}%"
        qry = qry.filter(BankTransaction.description.ilike(like))
    if date_from:
        try:
            d = datetime.strptime(date_from, "%Y-%m-%d")
            qry = qry.filter(BankTransaction.posted_at >= d)
        except ValueError:
            pass
    if date_to:
        try:
            d = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            qry = qry.filter(BankTransaction.posted_at < d)
        except ValueError:
            pass
    total = qry.count()
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    rows = (qry.order_by(BankTransaction.posted_at.desc(),
                         BankTransaction.id.desc())
              .offset((page - 1) * per_page).limit(per_page).all())
    accounts = (StripeBankAccount.query
                 .filter_by(store_id=sid, enabled=True)
                 .order_by(StripeBankAccount.connected_at.desc()).all())
    # Pre-fetch any linked DailyLineItems so the row template can show
    # the current report_date in the per-row date picker without an
    # N+1 lookup. Map by id; rows without a link get None.
    linked_ids = [r.daily_line_item_id for r in rows if r.daily_line_item_id]
    line_by_id = {}
    if linked_ids:
        for line in DailyLineItem.query.filter(
                DailyLineItem.id.in_(linked_ids)).all():
            line_by_id[line.id] = line
    ctx = dict(rows=rows, total=total, page=page, total_pages=total_pages,
               accounts=accounts, q=q, account_id=account_id,
               date_from=date_from, date_to=date_to,
               category_groups=_bank_category_groups(),
               category_label=_bank_category_label,
               line_by_id=line_by_id)
    if is_partial:
        return jsonify({
            "html": render_template("_bank_transactions_table.html", **ctx),
            "total": total, "page": page, "total_pages": total_pages,
        })
    return render_template("bank_transactions.html",
        user=current_user(), **ctx)

# ── Reconcile actions ───────────────────────────────────────
@app.route("/bank/transactions/<int:txn_id>/categorize", methods=["POST"])
@pro_required
def bank_transaction_categorize(txn_id):
    sid = session["store_id"]
    txn = BankTransaction.query.filter_by(id=txn_id, store_id=sid).first_or_404()
    target = (request.form.get("kind") or "").strip()
    if not target:
        flash("Pick a category before saving.", "error")
        return redirect(request.referrer or url_for("bank_transactions"))
    if target not in _LINE_ITEM_KINDS and target not in BANK_CATEGORIES_NON_POSTING:
        flash("Unknown category.", "error")
        return redirect(request.referrer or url_for("bank_transactions"))
    # Optional date override — supports the RDC case where the bank
    # posted the entry the next morning but it should land on the
    # previous day's daily book.
    override_date = None
    raw_date = (request.form.get("report_date") or "").strip()
    if raw_date:
        try:
            override_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid date.", "error")
            return redirect(request.referrer or url_for("bank_transactions"))
    _categorize_bank_transaction(txn, target, rule=None,
                                  post_to_daily=True,
                                  report_date=override_date)
    db.session.commit()
    flash(f"Categorized as {_bank_category_label(target)}.", "success")
    return redirect(request.referrer or url_for("bank_transactions"))

@app.route("/bank/transactions/<int:txn_id>/uncategorize", methods=["POST"])
@pro_required
def bank_transaction_uncategorize(txn_id):
    sid = session["store_id"]
    txn = BankTransaction.query.filter_by(id=txn_id, store_id=sid).first_or_404()
    _uncategorize_bank_transaction(txn)
    db.session.commit()
    flash("Uncategorized; daily-book line removed.", "success")
    return redirect(request.referrer or url_for("bank_transactions"))

@app.route("/bank/transactions/<int:txn_id>/move-date", methods=["POST"])
@pro_required
def bank_transaction_move_date(txn_id):
    """Re-date the linked DailyLineItem. Use case: the bank posted the
    transaction next morning (e.g. RDC dropped at 9 PM) but the cash-
    handling event belongs on the previous day's book."""
    sid = session["store_id"]
    txn = BankTransaction.query.filter_by(id=txn_id, store_id=sid).first_or_404()
    if not txn.daily_line_item_id:
        flash("This transaction isn't linked to a daily-book line.", "error")
        return redirect(request.referrer or url_for("bank_transactions"))
    raw = (request.form.get("report_date") or "").strip()
    if not raw:
        flash("Pick a date.", "error")
        return redirect(request.referrer or url_for("bank_transactions"))
    try:
        new_date = datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        flash("Invalid date.", "error")
        return redirect(request.referrer or url_for("bank_transactions"))
    line = db.session.get(DailyLineItem, txn.daily_line_item_id)
    if line is None:
        # Linked line was deleted out from under us — clear the link
        # silently so the row goes back to its uncategorized look.
        txn.daily_line_item_id = None
        db.session.commit()
        flash("Linked line not found; cleared the link.", "warning")
        return redirect(request.referrer or url_for("bank_transactions"))
    line.report_date = new_date
    db.session.commit()
    flash(f"Moved to {new_date.isoformat()}.", "success")
    return redirect(request.referrer or url_for("bank_transactions"))

# ── Rules CRUD ──────────────────────────────────────────────
def _parse_rule_form(form, sid):
    """Pull + validate a BankRule's fields from form data. Returns a
    dict of attribute updates plus an error string (empty on success).
    Reused by both new and edit handlers."""
    desc_match_type = (form.get("desc_match_type") or "").strip()
    desc_match_value = (form.get("desc_match_value") or "").strip()
    sign_filter = (form.get("sign_filter") or "").strip()
    target_kind = (form.get("target_kind") or "").strip()
    if not target_kind:
        return None, "Pick a category to apply when this rule matches."
    if target_kind not in _LINE_ITEM_KINDS and target_kind not in BANK_CATEGORIES_NON_POSTING:
        return None, "Unknown category."
    # Description match — both fields must be set together, or both empty.
    if desc_match_type and not desc_match_value:
        return None, "Enter a description value to match against."
    if desc_match_value and not desc_match_type:
        desc_match_type = "contains"
    if desc_match_type and desc_match_type not in ("contains", "starts_with", "equals", "regex"):
        return None, "Unknown description match type."
    if sign_filter and sign_filter not in ("credit", "debit"):
        return None, "Sign filter must be credit or debit."
    # Amounts come in as positive dollar strings; store as absolute cents.
    def _parse_dollars(label):
        raw = (form.get(label) or "").strip()
        if not raw:
            return None, ""
        try:
            cents = int(round(float(raw) * 100))
            if cents < 0:
                return None, "Amounts must be non-negative."
            return cents, ""
        except ValueError:
            return None, f"Invalid amount in {label}."
    amount_min_cents, e1 = _parse_dollars("amount_min")
    if e1: return None, e1
    amount_max_cents, e2 = _parse_dollars("amount_max")
    if e2: return None, e2
    if (amount_min_cents is not None and amount_max_cents is not None
            and amount_min_cents > amount_max_cents):
        return None, "Min amount can't be greater than max."
    # Account filter — must belong to the store.
    account_filter_id = None
    raw_acct = (form.get("account_filter_id") or "").strip()
    if raw_acct:
        try:
            acct_id = int(raw_acct)
        except ValueError:
            return None, "Invalid account filter."
        owned = StripeBankAccount.query.filter_by(
            id=acct_id, store_id=sid).first()
        if not owned:
            return None, "Account filter does not belong to this store."
        account_filter_id = acct_id
    # At least one condition must be set — an empty rule would catch
    # every transaction and is almost always a misconfiguration.
    if (not desc_match_type and not sign_filter
            and amount_min_cents is None and amount_max_cents is None
            and account_filter_id is None):
        return None, "Set at least one condition (description, sign, amount, or account)."
    try:
        priority = int(form.get("priority") or 100)
    except ValueError:
        priority = 100
    return {
        "enabled":           form.get("enabled") == "on",
        "priority":          priority,
        "desc_match_type":   desc_match_type,
        "desc_match_value":  desc_match_value,
        "sign_filter":       sign_filter,
        "amount_min_cents":  amount_min_cents,
        "amount_max_cents":  amount_max_cents,
        "account_filter_id": account_filter_id,
        "target_kind":       target_kind,
        "auto_post":         form.get("auto_post") == "on",
        "description":       (form.get("description") or "").strip()[:200],
    }, ""

@app.route("/bank/rules")
@pro_required
def bank_rules():
    sid = session["store_id"]
    rules = (BankRule.query.filter_by(store_id=sid)
             .order_by(BankRule.priority.asc(), BankRule.id.asc()).all())
    accounts = (StripeBankAccount.query.filter_by(store_id=sid, enabled=True)
                .order_by(StripeBankAccount.connected_at.desc()).all())
    return render_template("bank_rules.html",
        user=current_user(), rules=rules, accounts=accounts,
        category_groups=_bank_category_groups(),
        category_label=_bank_category_label)

@app.route("/bank/rules/new", methods=["POST"])
@pro_required
def bank_rule_new():
    sid = session["store_id"]
    fields, err = _parse_rule_form(request.form, sid)
    if err:
        flash(err, "error")
        return redirect(url_for("bank_rules"))
    rule = BankRule(store_id=sid, **fields)
    db.session.add(rule)
    db.session.commit()
    flash("Rule created.", "success")
    return redirect(url_for("bank_rules"))

@app.route("/bank/rules/<int:rule_id>/edit", methods=["POST"])
@pro_required
def bank_rule_edit(rule_id):
    sid = session["store_id"]
    rule = BankRule.query.filter_by(id=rule_id, store_id=sid).first_or_404()
    fields, err = _parse_rule_form(request.form, sid)
    if err:
        flash(err, "error")
        return redirect(url_for("bank_rules"))
    for k, v in fields.items():
        setattr(rule, k, v)
    db.session.commit()
    flash("Rule updated.", "success")
    return redirect(url_for("bank_rules"))

@app.route("/bank/rules/<int:rule_id>/toggle", methods=["POST"])
@pro_required
def bank_rule_toggle(rule_id):
    sid = session["store_id"]
    rule = BankRule.query.filter_by(id=rule_id, store_id=sid).first_or_404()
    rule.enabled = not rule.enabled
    db.session.commit()
    flash(f"Rule { 'enabled' if rule.enabled else 'disabled' }.", "success")
    return redirect(url_for("bank_rules"))

@app.route("/bank/rules/<int:rule_id>/delete", methods=["POST"])
@pro_required
def bank_rule_delete(rule_id):
    sid = session["store_id"]
    rule = BankRule.query.filter_by(id=rule_id, store_id=sid).first_or_404()
    db.session.delete(rule)
    db.session.commit()
    flash("Rule deleted.", "success")
    return redirect(url_for("bank_rules"))

@app.route("/bank/stripe/nickname/<int:acct_id>", methods=["POST"])
@pro_required
def bank_stripe_set_nickname(acct_id):
    """Set or clear the operator-defined nickname on a connected
    bank account. Empty input reverts to the ••<last4> label."""
    sid = session["store_id"]
    acct = StripeBankAccount.query.filter_by(
        id=acct_id, store_id=sid).first_or_404()
    nickname = (request.form.get("nickname") or "").strip()[:60]
    acct.nickname = nickname
    db.session.commit()
    flash(("Nickname saved." if nickname else "Nickname cleared."), "success")
    return redirect(url_for("bank"))

@app.route("/bank/stripe/disconnect/<int:acct_id>", methods=["POST"])
@pro_required
def bank_stripe_disconnect(acct_id):
    """Disconnect a single Stripe FC account. We both mark it disabled
    locally and tell Stripe to revoke, so the account stops counting
    toward the per-account billing line as well."""
    sid = session["store_id"]
    row = StripeBankAccount.query.filter_by(id=acct_id, store_id=sid).first_or_404()
    try:
        if stripe_is_configured():
            stripe.financial_connections.Account.disconnect(row.stripe_account_id)
    except stripe.error.StripeError as e:
        app.logger.warning(f"FC disconnect API call failed (continuing locally): {e}")
    row.enabled = False
    row.disconnected_at = datetime.utcnow()
    db.session.commit()
    flash("Bank account disconnected.", "success")
    return redirect(url_for("bank"))

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
    # The Security tab graduated to /account/security (a per-user page
    # reachable from every role's chrome). Old bookmarks land here.
    if active_tab == "security" and request.method == "GET":
        return redirect(url_for("account_security"), code=301)
    errors = {}

    if request.method == "POST":
        form_tab = request.form.get("_tab", "store")
        active_tab = form_tab

        if form_tab == "store":
            name = request.form.get("store_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            phone = request.form.get("phone", "").strip()
            # Federal tax rate: input is a percentage string (e.g. "1.00" for
            # 1%). Store as a decimal. Clamp 0–100% so an accidental "25" ≠ 25x.
            rate_raw = (request.form.get("federal_tax_rate") or "").strip()
            rate_decimal = store.federal_tax_rate or 0.01
            if rate_raw:
                try:
                    rate_pct = float(rate_raw)
                    if rate_pct < 0 or rate_pct > 100:
                        errors["federal_tax_rate"] = "Enter a percent between 0 and 100."
                    else:
                        rate_decimal = round(rate_pct / 100.0, 6)
                except ValueError:
                    errors["federal_tax_rate"] = "Enter a number (e.g. 1 for 1%)."

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
                store.federal_tax_rate = rate_decimal
                user.username = email
                db.session.commit()
                flash("Store info updated.", "success")
                return redirect(url_for("admin_settings", tab="store"))

        elif form_tab == "security":
            errors = _update_user_password(
                user,
                request.form.get("current_password", ""),
                request.form.get("new_password", ""),
                request.form.get("confirm_password", ""),
            )
            if not errors:
                db.session.commit()
                flash("Password updated.", "success")
                return redirect(url_for("account_security"))

        elif form_tab == "companies":
            # Known companies come in as checkboxes ("company_known" list);
            # operator-added names come as a newline-separated free-form
            # textarea. We merge + dedupe preserving input order.
            picked = request.form.getlist("company_known")
            extras_raw = request.form.get("company_extras", "")
            extras = [line.strip() for line in extras_raw.splitlines() if line.strip()]
            seen, out = set(), []
            for name in list(picked) + extras:
                if name not in seen:
                    seen.add(name); out.append(name)
            # Cap length so we don't try to stuff a novel into the column.
            csv = ",".join(out)[:500]
            store.companies = csv
            db.session.commit()
            flash("Money transfer companies updated.", "success")
            return redirect(url_for("admin_settings", tab="companies"))

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

    # Companies tab state: split the CSV into a set for checkbox state, and
    # list any names that aren't in the known catalog as "custom" so the
    # operator can see them and keep/remove.
    current_companies = store_mt_companies(store)
    current_set       = set(current_companies)
    custom_companies  = [c for c in current_companies if c not in KNOWN_MT_COMPANIES]

    # Roster tab: list every named employee, active first, then alpha.
    roster = StoreEmployee.query.filter_by(store_id=store.id).order_by(
        StoreEmployee.is_active.desc(), StoreEmployee.name.asc()
    ).all()

    return render_template("admin_settings.html",
        user=user, store=store,
        active_tab=active_tab, errors=errors,
        employees=employees,
        owner_invite=owner_invite,
        owner_link=owner_link,
        owner_user=owner_user,
        known_companies=KNOWN_MT_COMPANIES,
        current_company_set=current_set,
        custom_companies=custom_companies,
        roster=roster,
    )

@app.route("/admin/settings/roster/add", methods=["POST"])
@admin_required
def admin_roster_add():
    store = current_store()
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Name is required.", "error")
        return redirect(url_for("admin_settings", tab="roster"))
    # Case-insensitive dedupe against the store's existing roster. If a
    # deactivated entry matches, re-activate it instead of creating a second
    # row so the audit log stays intact.
    existing = StoreEmployee.query.filter(
        StoreEmployee.store_id == store.id,
        db.func.lower(StoreEmployee.name) == name.lower(),
    ).first()
    if existing:
        if not existing.is_active:
            existing.is_active = True
            db.session.commit()
            flash(f"Reactivated {existing.name}.", "success")
        else:
            flash(f"{existing.name} is already on the roster.", "error")
        return redirect(url_for("admin_settings", tab="roster"))
    db.session.add(StoreEmployee(store_id=store.id, name=name))
    db.session.commit()
    flash(f"Added {name}.", "success")
    return redirect(url_for("admin_settings", tab="roster"))

@app.route("/admin/settings/roster/<int:eid>/toggle", methods=["POST"])
@admin_required
def admin_roster_toggle(eid):
    sid = session["store_id"]
    emp = StoreEmployee.query.filter_by(id=eid, store_id=sid).first_or_404()
    emp.is_active = not emp.is_active
    db.session.commit()
    flash(
        f"{emp.name} {'reactivated' if emp.is_active else 'deactivated'}.",
        "success",
    )
    return redirect(url_for("admin_settings", tab="roster"))

@app.route("/admin/settings/roster/<int:eid>/rename", methods=["POST"])
@admin_required
def admin_roster_rename(eid):
    sid = session["store_id"]
    emp = StoreEmployee.query.filter_by(id=eid, store_id=sid).first_or_404()
    new_name = (request.form.get("name") or "").strip()
    if not new_name:
        flash("Name cannot be empty.", "error")
    else:
        emp.name = new_name
        db.session.commit()
        # Historical transfers keep their snapshotted employee_name — a
        # rename only affects future dropdown picks. That's the intended
        # audit-preserving behavior.
        flash(f"Renamed to {new_name}.", "success")
    return redirect(url_for("admin_settings", tab="roster"))


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
            db.session.add(a)
            record_audit("create_store", target_type="store", target_id=s.id, details=s.slug)
            db.session.commit()
            flash(f"Store '{s.name}' created.","success"); return redirect(url_for("superadmin_stores"))
    return render_template("superadmin_store_form.html",user=user,store=None)

@app.route("/superadmin/impersonate/<int:store_id>")
@superadmin_required
def superadmin_impersonate(store_id):
    """Swap the current session into the target store's admin user.

    Used by the superadmin to debug a customer's view. The *real*
    superadmin identity is stashed in `session["impersonator_user_id"]`
    so `/superadmin/stop-impersonation` can restore it — before this,
    the only way back was a full re-login. Every start AND end of an
    impersonation is written to the audit log.
    """
    store=db.session.get(Store, store_id) or abort(404)
    admin=User.query.filter_by(store_id=store_id,role="admin").first()
    if not admin: flash("No admin for this store.","error"); return redirect(url_for("superadmin_stores"))
    record_audit("impersonate_start", target_type="store", target_id=store.id,
                 details=f"as {admin.username}")
    # Preserve the real superadmin identity so the "Exit impersonation"
    # button can restore it without a re-login. We only ever set this
    # from a route guarded by @superadmin_required, so the value is
    # trustworthy at write time; /superadmin/stop-impersonation still
    # re-validates it on read.
    session["impersonator_user_id"] = session["user_id"]
    session["user_id"]=admin.id; session["role"]=admin.role; session["store_id"]=store_id
    db.session.commit()
    flash(f"Viewing as {store.name}. Use 'Exit impersonation' to return.","success")
    return redirect(url_for("dashboard"))


@app.route("/superadmin/stop-impersonation", methods=["POST"])
def superadmin_stop_impersonation():
    """Return to the real superadmin identity after impersonation.

    Intentionally NOT guarded by @superadmin_required — while
    impersonating, session['role'] is 'admin', so the decorator would
    reject the superadmin trying to exit. Instead we verify the
    stashed impersonator_user_id still resolves to an active
    superadmin before restoring. If anything looks off, clear the
    session entirely rather than elevate the current identity.
    """
    imp_id = session.get("impersonator_user_id")
    if not imp_id:
        flash("Not currently impersonating.", "error")
        return redirect(url_for("dashboard"))
    imp = db.session.get(User, imp_id)
    if not imp or imp.role != "superadmin" or not imp.is_active:
        # Defense in depth — cookie tampering or a since-deactivated
        # superadmin account shouldn't be a path to an elevated session.
        session.clear()
        flash("Session invalid. Please sign in again.", "error")
        return redirect(url_for("login"))
    record_audit("impersonate_end", target_type="user", target_id=imp.id,
                 details=f"returning to {imp.username}")
    session["user_id"] = imp.id
    session["role"] = "superadmin"
    session["store_id"] = None
    session.pop("impersonator_user_id", None)
    db.session.commit()
    flash("Returned to superadmin.", "success")
    return redirect(url_for("dashboard"))

# ── Superadmin control panel ─────────────────────────────────
STORES_PER_PAGE = 20

@app.route("/superadmin/controls")
@superadmin_required
def superadmin_controls():
    """Tabbed superadmin hub: overview, stores, discounts, feature flags, audit, announcements."""
    user = current_user()
    active_tab = request.args.get("tab", "overview")

    # Aggregate metrics — cheap, compute once for the overview + sidebar snapshot.
    # Split BASIC and PRO into monthly + yearly so the overview shows the full
    # revenue picture. A store that hasn't been touched since the billing_cycle
    # column shipped lands in the monthly bucket (empty string falls to the
    # default case in the else branch).
    plan_rows = db.session.query(
        Store.plan, Store.billing_cycle, db.func.count(Store.id)
    ).group_by(Store.plan, Store.billing_cycle).all()

    basic_monthly = basic_yearly = pro_monthly = pro_yearly = 0
    trial_count = inactive_count = 0
    for p, cycle, n in plan_rows:
        if p == "basic":
            if cycle == "yearly": basic_yearly += n
            else:                 basic_monthly += n
        elif p == "pro":
            if cycle == "yearly": pro_yearly += n
            else:                 pro_monthly += n
        elif p == "trial":
            trial_count += n
        elif p == "inactive":
            inactive_count += n

    basic_count    = basic_monthly + basic_yearly
    pro_count      = pro_monthly + pro_yearly
    total_stores   = Store.query.count()

    retention_queue = Store.query.filter(
        Store.plan == "inactive",
        Store.data_retention_until.isnot(None),
    ).count()

    (basic_monthly_mrr, basic_yearly_mrr,
     pro_monthly_mrr,   pro_yearly_mrr,
     estimated_mrr) = _compute_mrr(basic_monthly, basic_yearly, pro_monthly, pro_yearly)

    # Stripe health only hit on the overview tab (API call costs one round trip).
    stripe_health = stripe_health_check() if active_tab == "overview" else None
    # SMTP health is free (reads _last_smtp_attempt in-process, no network).
    smtp_health = smtp_health_check() if active_tab == "overview" else None

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
    # TV display catalogs (Phase 2 of the logo rollout). Companies
    # are global; banks group by country_code in the template. Both
    # tables include inactive entries here so the curation UI can
    # reactivate / soft-delete; the operator-side picker filters
    # them out at render time.
    tv_companies = (TVCompanyCatalog.query
                     .order_by(TVCompanyCatalog.sort_order,
                               TVCompanyCatalog.display_name).all())
    tv_banks = (TVBankCatalog.query
                 .order_by(TVBankCatalog.country_code,
                           TVBankCatalog.sort_order,
                           TVBankCatalog.display_name).all())
    # Map (catalog_type, slug) → updated_at unix so the template can
    # cache-bust ?v=<unix> on the logo URLs without an extra query
    # per row.
    tv_logo_versions = {}
    for row in TVCatalogLogo.query.all():
        tv_logo_versions[(row.catalog_type, row.slug)] = int(
            row.updated_at.timestamp())
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
        basic_monthly=basic_monthly, basic_yearly=basic_yearly,
        pro_monthly=pro_monthly, pro_yearly=pro_yearly,
        basic_monthly_mrr=basic_monthly_mrr, basic_yearly_mrr=basic_yearly_mrr,
        pro_monthly_mrr=pro_monthly_mrr, pro_yearly_mrr=pro_yearly_mrr,
        trial_count=trial_count, inactive_count=inactive_count,
        retention_queue=retention_queue, estimated_mrr=estimated_mrr,
        total_stores=total_stores,
        stripe_health=stripe_health,
        smtp_health=smtp_health,
        # Add-on catalog so the per-store override row can iterate
        # every add-on the platform supports (not just the ones a
        # given store currently has).
        addons_catalog=ADDONS_CATALOG,
        # TV display catalog admin (curation tab).
        tv_companies=tv_companies,
        tv_banks=tv_banks,
        tv_logo_versions=tv_logo_versions,
        # Pagination + filter state for the Stores tab.
        q=q_text, plan_filter=plan_filter, status_filter=status_filter,
        page=page, total_pages=total_pages, stores_matching=stores_matching,
        stores_per_page=STORES_PER_PAGE,
    )

# ── Email delivery test (superadmin) ─────────────────────────
@app.route("/superadmin/send-test-email", methods=["POST"])
@superadmin_required
def superadmin_send_test_email():
    """One-click deliverability probe. Sends a plain email to the
    superadmin's own User.email (they populate it from /account/profile)
    so they can verify the SMTP env vars are wired correctly without
    waiting for a real trigger like password reset.

    No dedup, no rate limit — superadmin-only, and the worst case is
    they spam their own inbox. The response is a flash + redirect back
    to the Overview so the SMTP health card updates with the new
    _last_smtp_attempt state on the next render."""
    user = current_user()
    to_addr = (user.email or "").strip()
    if not to_addr:
        flash("Set your email on /account/profile first — "
              "nowhere to send a test to.", "warning")
        return redirect(url_for("superadmin_controls", tab="overview"))
    subject = "DineroBook test email"
    sent_at = datetime.utcnow().isoformat(timespec="seconds")
    body = (
        "This is a deliverability test from DineroBook.\n\n"
        f"Sent to: {to_addr}\n"
        f"Sent at: {sent_at}Z\n\n"
        "If you're reading this, SMTP is configured correctly and "
        "transactional email (password reset, trial reminders) will "
        "reach your users.\n"
    )
    html = render_template(
        "emails/test.html",
        preheader="Deliverability test from your DineroBook superadmin panel.",
        to_addr=to_addr, sent_at=sent_at + "Z",
        sender=os.environ.get("SMTP_FROM", "no-reply@dinerobook.com"),
        year=datetime.utcnow().year,
        base_url=os.environ.get("APP_BASE_URL", "https://dinerobook.com"),
    )
    ok = _send_email(to_addr, subject, body, html=html)
    if ok:
        flash(f"Test email sent to {to_addr}. Check your inbox in a minute.", "success")
    else:
        # _last_smtp_attempt now holds the error; it'll render on the
        # same page's SMTP health card. Keep the flash message terse —
        # the card has the detail.
        flash("Test email failed. See the Email service card for the error.", "warning")
    record_audit("send_test_email", "superadmin", None, f"to={to_addr} ok={ok}")
    db.session.commit()
    return redirect(url_for("superadmin_controls", tab="overview"))

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


@app.route("/superadmin/stores/<int:store_id>/extend-trial", methods=["POST"])
@superadmin_required
def superadmin_extend_trial(store_id):
    """Push the store's trial/grace deadlines forward by N days (default 7)."""
    store = _store_or_404(store_id)
    days = _parse_extend_days(request.form, default=7, maximum=180)
    store.trial_ends_at = _extended_deadline(store.trial_ends_at, days)
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
    days = _parse_extend_days(request.form, default=30, maximum=720)
    store.data_retention_until = _extended_deadline(
        store.data_retention_until, days)
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

@app.route("/superadmin/stores/<int:store_id>/addons/<addon_key>/toggle",
            methods=["POST"])
@superadmin_required
def superadmin_toggle_addon(store_id, addon_key):
    """Override switch for a store's add-ons. Bypasses the
    "needs paid plan" gate that admin_subscription_toggle_addon
    enforces — sometimes superadmin needs to flip an addon on for a
    pilot/comped store, or off for a non-paying one. Audit-logged
    so the override path is always attributable."""
    store = _store_or_404(store_id)
    addon = ADDONS_CATALOG.get(addon_key)
    if not addon:
        flash("Unknown add-on.", "error")
        return redirect(url_for("superadmin_controls", tab="stores"))
    keys = {k.strip() for k in (store.addons or "").split(",") if k.strip()}
    if addon_key in keys:
        keys.discard(addon_key)
        action = "remove_addon"
        msg = f"{store.name}: {addon['name']} turned off."
    else:
        keys.add(addon_key)
        action = "add_addon"
        msg = f"{store.name}: {addon['name']} activated."
    store.addons = ",".join(sorted(keys))
    record_audit(action, target_type="store", target_id=store.id,
                  details=addon_key)
    db.session.commit()
    flash(msg, "success")
    return redirect(url_for("superadmin_controls", tab="stores"))

# ── TV catalog admin (superadmin) ────────────────────────────
#
# Curate the dropdown options operators see in the country editor:
# add new MT companies / banks, rename existing ones (display_name
# only — slugs are immutable), upload nominative-use logos, and
# soft-deactivate retired entries. Companies are global; banks are
# scoped to a country (ISO-2).

# 200 KiB hard cap on uploads — covers the 50 KB typical PNG with
# headroom for retina assets, blocks accidental "I dropped a 5 MB
# JPEG" uploads. Validated server-side; the BLOB DB column would
# accept much more, but we'd rather reject early.
_TV_LOGO_MAX_BYTES = 200 * 1024

# Standard canvas every raster logo is fit-and-padded into. 600x200
# is high-enough resolution for 4K TV display + 3x retina laptops
# without cropping the brand mark; 3:1 ratio fits both wordmarks
# (e.g. "Western Union" wide) and abbreviation marks (e.g. "BBVA"
# squarish) without one looking dwarfed against the other.
# CSS at display time scales down via object-fit: contain.
_TV_LOGO_CANVAS_WIDTH  = 600
_TV_LOGO_CANVAS_HEIGHT = 200

def _normalize_logo_blob(blob, mime):
    """Standardize an uploaded logo so every catalog entry renders
    at the same visual weight on the public TV board.

    Raster (PNG/JPEG/WebP):
      - Open with Pillow, scale (preserving aspect) to fit a
        600x200 canvas via thumbnail + LANCZOS resampling.
      - Center on a transparent canvas (RGBA).
      - Save as optimized PNG. JPEG inputs that have no alpha
        come out as PNG with a transparent surrounding area.
      - Bytes-on-wire are uniform regardless of the source's
        pixel dimensions.

    SVG:
      - Pass through unchanged. The viewBox is the logical
        canvas; CSS object-fit:contain handles display scaling
        without quality loss. (Re-rasterizing SVGs through
        Pillow would defeat their purpose.)

    Falls back to (blob, mime) unchanged on any Pillow error so a
    malformed-but-acceptable upload still lands in the DB rather
    than blocking the operator with an opaque error.

    Returns (normalized_blob, normalized_mime). Raster always
    becomes "image/png"; SVG stays "image/svg+xml".
    """
    if mime == "image/svg+xml":
        return blob, mime

    try:
        from PIL import Image
    except ImportError:
        # Pillow not installed (dev shell, never in prod requirements).
        return blob, mime

    try:
        with Image.open(io.BytesIO(blob)) as src:
            src.load()  # force-decode now so a corrupt image fails fast
            # thumbnail() resizes in place, preserving aspect ratio.
            scaled = src.copy()
            scaled.thumbnail(
                (_TV_LOGO_CANVAS_WIDTH, _TV_LOGO_CANVAS_HEIGHT),
                Image.Resampling.LANCZOS,
            )
            # Convert to RGBA so we can paste over a transparent
            # canvas; JPEG inputs become RGBA.
            if scaled.mode != "RGBA":
                scaled = scaled.convert("RGBA")

            canvas = Image.new(
                "RGBA",
                (_TV_LOGO_CANVAS_WIDTH, _TV_LOGO_CANVAS_HEIGHT),
                (0, 0, 0, 0),
            )
            x = (_TV_LOGO_CANVAS_WIDTH  - scaled.width)  // 2
            y = (_TV_LOGO_CANVAS_HEIGHT - scaled.height) // 2
            canvas.paste(scaled, (x, y), scaled)

            out = io.BytesIO()
            canvas.save(out, format="PNG", optimize=True)
            return out.getvalue(), "image/png"
    except Exception:
        # Corrupt image / unsupported format / Pillow stack issue —
        # store the original bytes rather than blocking the upload.
        # The serve route still validates mime against the whitelist.
        return blob, mime

def _resolve_catalog_row(catalog_type, slug):
    """Returns the parent catalog row for a (type, slug) pair, or
    None if neither table has a match. Used by the upload + edit
    endpoints to validate the slug before they touch the DB."""
    if catalog_type == "company":
        return TVCompanyCatalog.query.filter_by(slug=slug).first()
    if catalog_type == "bank":
        return TVBankCatalog.query.filter_by(slug=slug).first()
    return None

@app.route("/superadmin/tv-catalog/<catalog_type>/<slug>/logo",
            methods=["POST"])
@superadmin_required
def superadmin_tv_catalog_upload_logo(catalog_type, slug):
    """Upload (or replace) the logo for a catalog entry."""
    if catalog_type not in ("company", "bank"):
        abort(404)
    row = _resolve_catalog_row(catalog_type, slug)
    if row is None:
        flash("Unknown catalog entry.", "error")
        return redirect(url_for("superadmin_controls", tab="tv-catalog"))

    f = request.files.get("logo")
    if not f or not f.filename:
        flash("Pick a file to upload.", "error")
        return redirect(url_for("superadmin_controls", tab="tv-catalog"))

    mime = (f.mimetype or "").lower()
    if mime not in _TV_LOGO_ALLOWED_MIMES:
        flash("File must be PNG, JPEG, WebP, or SVG.", "error")
        return redirect(url_for("superadmin_controls", tab="tv-catalog"))

    raw_blob = f.read()
    if len(raw_blob) == 0:
        flash("Uploaded file is empty.", "error")
        return redirect(url_for("superadmin_controls", tab="tv-catalog"))
    if len(raw_blob) > _TV_LOGO_MAX_BYTES:
        flash(f"Logo too large — max {_TV_LOGO_MAX_BYTES // 1024} KB.", "error")
        return redirect(url_for("superadmin_controls", tab="tv-catalog"))

    # Normalize raster uploads to a uniform 600x200 transparent
    # canvas. SVG passes through unchanged. Result: every catalog
    # logo renders at the same visual weight on the public board
    # regardless of the source image's pixel dimensions or padding.
    blob, mime = _normalize_logo_blob(raw_blob, mime)

    existing = TVCatalogLogo.query.filter_by(
        catalog_type=catalog_type, slug=slug).first()
    if existing is None:
        existing = TVCatalogLogo(catalog_type=catalog_type, slug=slug)
        db.session.add(existing)
    existing.mime_type = mime
    existing.blob      = blob
    existing.file_size = len(blob)
    existing.updated_at = datetime.utcnow()

    # Mirror the public URL into the parent row's logo_url so other
    # call sites can hit it without doing a separate logo-table
    # lookup. The ?v=<unix> query param is added by templates that
    # care about cache-busting on re-upload.
    row.logo_url = url_for("tv_catalog_logo",
                            catalog_type=catalog_type, slug=slug)

    record_audit("tv_logo_upload", target_type=catalog_type,
                  target_id=row.id,
                  details=f"{slug} ({len(blob)} bytes, {mime})")
    db.session.commit()
    flash(f"Uploaded logo for {row.display_name}.", "success")
    return redirect(url_for("superadmin_controls", tab="tv-catalog"))

@app.route("/superadmin/tv-catalog/<catalog_type>/<slug>/edit",
            methods=["POST"])
@superadmin_required
def superadmin_tv_catalog_edit(catalog_type, slug):
    """Rename, re-sort, change country code (banks only), or toggle
    is_active. Slug is intentionally NOT mutable — references on
    TVDisplayCountry / TVDisplayPayoutBank would silently break."""
    if catalog_type not in ("company", "bank"):
        abort(404)
    row = _resolve_catalog_row(catalog_type, slug)
    if row is None:
        flash("Unknown catalog entry.", "error")
        return redirect(url_for("superadmin_controls", tab="tv-catalog"))

    new_name = (request.form.get("display_name") or "").strip()[:80]
    if new_name:
        row.display_name = new_name
    try:
        row.sort_order = int(request.form.get("sort_order", row.sort_order))
    except (TypeError, ValueError):
        pass
    if catalog_type == "bank":
        new_cc = (request.form.get("country_code") or "").strip().upper()[:4]
        if new_cc:
            row.country_code = new_cc
    # Checkbox semantics: present → True, absent → False.
    row.is_active = bool(request.form.get("is_active"))

    record_audit("tv_catalog_edit", target_type=catalog_type,
                  target_id=row.id, details=slug)
    db.session.commit()
    flash(f"Saved {row.display_name}.", "success")
    return redirect(url_for("superadmin_controls", tab="tv-catalog"))

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

@app.route("/superadmin/tv-catalog/new", methods=["POST"])
@superadmin_required
def superadmin_tv_catalog_new():
    """Add a fresh catalog entry. Slug is auto-generated from the
    display_name (and country_code for banks); dedup'd with a
    numeric suffix on collision. The operator never types a slug."""
    catalog_type = (request.form.get("catalog_type") or "").strip()
    if catalog_type not in ("company", "bank"):
        flash("Pick company or bank.", "error")
        return redirect(url_for("superadmin_controls", tab="tv-catalog"))
    display_name = (request.form.get("display_name") or "").strip()[:80]
    if not display_name:
        flash("Display name is required.", "error")
        return redirect(url_for("superadmin_controls", tab="tv-catalog"))

    if catalog_type == "company":
        base_slug = _slugify_catalog_name(display_name)
    else:
        cc = (request.form.get("country_code") or "").strip().upper()[:4]
        if not cc:
            flash("Banks need a country code (ISO-2).", "error")
            return redirect(url_for("superadmin_controls", tab="tv-catalog"))
        base_slug = _slugify_bank_name(display_name, cc)

    if not base_slug:
        flash("Couldn't derive a slug from that name. Try a different one.",
              "error")
        return redirect(url_for("superadmin_controls", tab="tv-catalog"))

    slug = _next_unique_slug(catalog_type, base_slug)
    if not slug:
        flash("Too many entries with similar names — slug exhausted.",
              "error")
        return redirect(url_for("superadmin_controls", tab="tv-catalog"))

    if catalog_type == "company":
        last = (db.session.query(db.func.max(TVCompanyCatalog.sort_order))
                .scalar() or 0)
        db.session.add(TVCompanyCatalog(
            slug=slug, display_name=display_name,
            sort_order=last + 10, is_active=True,
        ))
    else:
        last = (db.session.query(db.func.max(TVBankCatalog.sort_order))
                .filter_by(country_code=cc).scalar() or 0)
        db.session.add(TVBankCatalog(
            slug=slug, display_name=display_name,
            country_code=cc,
            sort_order=last + 10, is_active=True,
        ))
    record_audit("tv_catalog_create", target_type=catalog_type,
                  target_id=0, details=slug)
    db.session.commit()
    flash(f"Added {display_name}.", "success")
    return redirect(url_for("superadmin_controls", tab="tv-catalog"))

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
    dc = db.session.get(DiscountCode, dc_id) or abort(404)
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
    """Post a banner shown to every user on every page until it expires.
    Optionally also email the announcement to every opted-in user if
    the `broadcast` checkbox is ticked."""
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
    broadcast = bool(request.form.get("broadcast"))
    a = Announcement(
        message=message[:2000], level=level,
        is_active=True, expires_at=expires_at,
        created_by=current_user().id,
        broadcast_requested=broadcast,
    )
    db.session.add(a); db.session.flush()
    record_audit("create_announcement", target_type="announcement", target_id=a.id,
                 details=f"{level}: {message[:80]}"
                         + (" [broadcast]" if broadcast else ""))
    db.session.commit()
    # Broadcast synchronously. At current scale (a few hundred users)
    # this is sub-second. If we ever grow past ~2k opted-in users,
    # convert to a queued job — the sender is already idempotent.
    if broadcast:
        try:
            sent = broadcast_announcement(a.id)
            flash(f"Announcement posted and emailed to {sent} user(s).",
                  "success")
        except Exception as e:
            app.logger.warning(f"announcement broadcast failed: {e}")
            flash("Announcement posted, but the broadcast email failed. "
                  "Check the Email service card for details.", "warning")
    else:
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
    import csv
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
    users = (User.query
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
            # Future notify_* columns should be flipped here too.

@app.route("/webhooks/resend", methods=["POST"])
def resend_webhook():
    """Resend delivery-event receiver. See comment above for the full
    shape and policy."""
    secret = os.environ.get("RESEND_WEBHOOK_SECRET", "")
    raw = request.get_data()
    svix_id        = request.headers.get("svix-id", "")
    svix_timestamp = request.headers.get("svix-timestamp", "")
    svix_signature = request.headers.get("svix-signature", "")
    if not _verify_resend_signature(secret, svix_id, svix_timestamp,
                                     svix_signature, raw):
        return jsonify({"error": "Invalid signature"}), 400

    try:
        event = request.get_json(force=True, silent=False)
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400
    event_type = (event or {}).get("type", "") or ""
    data = (event or {}).get("data", {}) or {}
    message_id = data.get("email_id") or ""
    bounce_type = ""
    if isinstance(data.get("bounce"), dict):
        bounce_type = data["bounce"].get("type", "") or ""
    recipients = data.get("to") or []
    if isinstance(recipients, str):
        recipients = [recipients]

    # One EmailEvent row per (event, recipient) tuple so we can query
    # "has this address bounced" without joining through a message.
    payload_json = ""
    try:
        payload_json = json.dumps(event)[:8000]
    except Exception:
        payload_json = ""
    for raw_to in recipients:
        to_norm = (raw_to or "").strip().lower()
        user_id = None
        if to_norm:
            matched = (db.session.query(User.id)
                       .filter(db.func.lower(User.email) == to_norm)
                       .first())
            user_id = matched[0] if matched else None
        db.session.add(EmailEvent(
            message_id=message_id[:80], to_addr=to_norm[:255],
            user_id=user_id, event_type=event_type[:40],
            bounce_type=bounce_type[:16], payload=payload_json,
        ))
        _apply_resend_side_effects(event_type, to_norm, bounce_type)
    db.session.commit()
    return jsonify({"ok": True})

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
                    # Map the Stripe price to the internal plan key.
                    # basic + basic_yearly both grant the "basic" tier;
                    # pro + pro_yearly both grant "pro". Anything unknown
                    # falls back to "pro" (safer than locking the user out
                    # of features they paid for).
                    prices = _stripe_price_ids()
                    basic_ids  = {prices["basic"], prices["basic_yearly"]} - {""}
                    yearly_ids = {prices["basic_yearly"], prices["pro_yearly"]} - {""}
                    store.plan = "basic" if price_id in basic_ids else "pro"
                    store.billing_cycle = "yearly" if price_id in yearly_ids else "monthly"
                except Exception as e:
                    app.logger.error(f"Stripe sub retrieve error: {e}")
                    store.plan = "pro"
                    store.billing_cycle = "monthly"
                store.stripe_customer_id = customer_id
                store.stripe_subscription_id = sub_id
                # Returning customer: clear cancellation + retention timer.
                store.canceled_at = None
                store.data_retention_until = None
                # Reset the trial-reminder dedup flag too, so if this
                # subscription later lapses and a NEW trial ever begins,
                # the reminder cron sends fresh instead of no-oping.
                store.trial_reminder_sent_at = None
                # Referral flow: mint the referrer's own code so they get
                # the topbar crown immediately, and apply any pending
                # referee credit from the code they signed up with.
                try:
                    ensure_referral_code(store)
                    apply_pending_referral_credits(store)
                except Exception as e:
                    app.logger.warning(f"referral hook error for store {store.id}: {e}")
                db.session.commit()

    elif event["type"] == "customer.subscription.deleted":
        sub_id = event["data"]["object"].get("id", "")
        store = Store.query.filter_by(stripe_subscription_id=sub_id).first()
        if store:
            now = datetime.utcnow()
            store.plan = "inactive"
            store.billing_cycle = ""
            store.stripe_subscription_id = ""
            store.canceled_at = now
            store.data_retention_until = now + timedelta(days=DATA_RETENTION_DAYS)
            db.session.commit()

    return jsonify({"received": True}), 200

# ── Data retention purge ─────────────────────────────────────
# Models that hold per-store data and must be wiped before the store row.
_STORE_OWNED_MODELS = [
    # TransferAudit must purge before Transfer (it has an FK to transfer.id),
    # and StoreEmployee before any row that FKs to it — we null/ignore employee
    # FKs on purge via the audit table's nullable column, but order still
    # matters for cascade sanity.
    "TransferAudit", "Transfer", "ACHBatch", "DailyReport", "DailyDrop", "CheckDeposit",
    "DailyLineItem", "MoneyTransferSummary", "ReturnCheck",
    # BankTransaction must purge before StripeBankAccount — it FKs to it.
    # BankRule + BankTransaction must purge before StripeBankAccount —
    # both FK to it.
    "MonthlyFinancial", "BankRule", "BankTransaction", "StripeBankAccount", "StoreOwnerLink",
    "StoreEmployee", "OwnerInviteCode", "Customer",
    "ReferralCode", "ReferralRedemption",
    # TVDisplay (store-keyed) — children handled by the explicit chain
    # above this loop. Listing it here covers the parent row itself.
    "TVDisplay",
    "User",
]

# Models whose store FK isn't literally named `store_id`. The default for
# anything absent here is `store_id`.
_STORE_FK_OVERRIDES = {
    "ReferralCode":       "owner_store_id",
    "ReferralRedemption": "referee_store_id",
}

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
        # User-scoped auth rows have to go before the Users themselves so
        # the User FK doesn't orphan on Postgres. Collect user ids in the
        # store, wipe their Passkey rows, then let the regular loop purge
        # the User rows.
        user_ids = [uid for (uid,) in
                    db.session.query(User.id).filter_by(store_id=s.id).all()]
        if user_ids:
            Passkey.query.filter(Passkey.user_id.in_(user_ids)).delete(
                synchronize_session=False)
            # EmailEvent.user_id is a nullable FK; we null it out for
            # purged users so the event history (useful for
            # post-purge forensics) doesn't block the User delete.
            EmailEvent.query.filter(EmailEvent.user_id.in_(user_ids)).update(
                {"user_id": None}, synchronize_session=False)
        # TV-display tables form a chain (display → country → bank →
        # rate) and only the top has store_id. Walk down explicitly so
        # the FK constraints don't reject the deletes on Postgres.
        # TVPairing also hangs off display_id, same FK story.
        # TVPendingPair is loose (no display_id — pending pairs are
        # device-side until claimed) but FK's into TVPairing via
        # claimed_pairing_id, so we have to wipe pending rows that
        # reference doomed pairings BEFORE the pairing delete.
        display_ids = [d for (d,) in
                       db.session.query(TVDisplay.id).filter_by(store_id=s.id).all()]
        if display_ids:
            doomed_pairing_ids = [p for (p,) in
                                   db.session.query(TVPairing.id).filter(
                                       TVPairing.display_id.in_(display_ids)).all()]
            if doomed_pairing_ids:
                TVPendingPair.query.filter(
                    TVPendingPair.claimed_pairing_id.in_(doomed_pairing_ids)
                ).delete(synchronize_session=False)
            TVPairing.query.filter(
                TVPairing.display_id.in_(display_ids)).delete(
                    synchronize_session=False)
            country_ids = [c for (c,) in
                           db.session.query(TVDisplayCountry.id).filter(
                               TVDisplayCountry.display_id.in_(display_ids)).all()]
            if country_ids:
                bank_ids = [b for (b,) in
                            db.session.query(TVDisplayPayoutBank.id).filter(
                                TVDisplayPayoutBank.country_id.in_(country_ids)).all()]
                if bank_ids:
                    TVDisplayRate.query.filter(
                        TVDisplayRate.bank_id.in_(bank_ids)).delete(
                            synchronize_session=False)
                TVDisplayPayoutBank.query.filter(
                    TVDisplayPayoutBank.country_id.in_(country_ids)).delete(
                        synchronize_session=False)
            TVDisplayCountry.query.filter(
                TVDisplayCountry.display_id.in_(display_ids)).delete(
                    synchronize_session=False)
        for model_name in _STORE_OWNED_MODELS:
            model = globals().get(model_name)
            if model is not None:
                fk = _STORE_FK_OVERRIDES.get(model_name, "store_id")
                model.query.filter_by(**{fk: s.id}).delete(synchronize_session=False)
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

_TRIAL_REMINDER_SUBJECT = "Your DineroBook trial ends in {days} days"

_TRIAL_REMINDER_BODY = """\
Hi {name},

Just a heads-up that your DineroBook trial for "{store_name}" ends on
{trial_end_date}. That's {days} days from today.

To keep your books, reports, and transfer history, subscribe before
then:
    {subscribe_url}

No action is required if you'd rather let the trial expire; we keep
your data for 180 days after cancellation so you can come back.

Don't want trial reminders anymore? Turn them off on your
notifications page:
    {notifications_url}

— DineroBook
"""

def _trial_reminder_recipients(store):
    """Users who should get the reminder for this store: admins +
    owners of this store with email + notify_trial_reminders=True."""
    owner_user_ids = [
        link.user_id for link in
        StoreOwnerLink.query.filter_by(store_id=store.id).all()
    ]
    conds = [User.store_id == store.id]
    if owner_user_ids:
        # Owners live in a different store's user row but link back.
        conds.append(User.id.in_(owner_user_ids))
    candidates = User.query.filter(
        User.is_active == True,
        User.role.in_(("admin", "owner")),
        User.email != "",
        User.notify_trial_reminders == True,
        db.or_(*conds),
    ).all()
    # Dedup — same user could be an owner AND an admin of this store.
    return list({u.id: u for u in candidates}.values())

def send_trial_reminders(now=None, base_url=None):
    """Mail every eligible user whose store is in expiring_soon. Returns
    the count of emails actually sent (not counting users skipped for
    no-email or notify_trial_reminders=False). Idempotent thanks to
    trial_reminder_sent_at; rerunning on the same day is a no-op."""
    now = now or datetime.utcnow()
    base_url = base_url or os.environ.get("APP_BASE_URL",
                                          "https://dinerobook.com")
    sent = 0
    for store in Store.query.filter(
        Store.plan == "trial",
        Store.trial_ends_at.isnot(None),
        Store.trial_reminder_sent_at.is_(None),
    ).all():
        if get_trial_status(store) != "expiring_soon":
            continue
        days_left = max(0, (store.trial_ends_at - now).days)
        trial_end_str = store.trial_ends_at.strftime("%B %d, %Y")
        subscribe_url = f"{base_url}/subscribe"
        notifications_url = f"{base_url}/account/notifications"
        any_sent = False
        for u in _trial_reminder_recipients(store):
            body = _TRIAL_REMINDER_BODY.format(
                name=u.full_name or u.username,
                store_name=store.name,
                trial_end_date=trial_end_str,
                days=days_left,
                subscribe_url=subscribe_url,
                notifications_url=notifications_url,
            )
            # Context processors (inject_trial_context / impersonation)
            # read request / session state, which isn't present when
            # `flask send-trial-reminders` runs from cron. Fabricate a
            # minimal request context so render_template works. The URL
            # we feed it doesn't matter — the template references nothing
            # that depends on it.
            with app.test_request_context("/"):
                html = render_template(
                    "emails/trial_reminder.html",
                    preheader=f"Your DineroBook trial for {store.name} ends on {trial_end_str}.",
                    name=u.full_name or "",
                    store_name=store.name,
                    trial_end_date=trial_end_str,
                    days=days_left,
                    subscribe_url=subscribe_url,
                    notifications_url=notifications_url,
                    year=now.year,
                    base_url=base_url,
                )
            subject = _TRIAL_REMINDER_SUBJECT.format(days=days_left)
            _send_email(u.email, subject, body, html=html)
            any_sent = True
            sent += 1
        if any_sent:
            store.trial_reminder_sent_at = now
    if sent:
        db.session.commit()
    return sent

@app.cli.command("send-trial-reminders")
def send_trial_reminders_cmd():
    """Email admins/owners of stores in expiring_soon. Run daily."""
    n = send_trial_reminders()
    print(f"Sent {n} trial reminder email(s).")

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
    """Fan out an announcement email to every opted-in user. Returns
    the count of emails actually attempted (not counting users filtered
    out). Idempotent: the first successful run stamps broadcast_sent_at
    and subsequent calls no-op."""
    base_url = base_url or os.environ.get("APP_BASE_URL",
                                          "https://dinerobook.com")
    ann = db.session.get(Announcement, announcement_id)
    if ann is None:
        return 0
    if ann.broadcast_sent_at is not None:
        return 0  # already sent — idempotent
    # First line of the message becomes the subject if it looks like
    # a sentence; otherwise use a generic subject. Cap at 100 chars.
    first_line = (ann.message or "").strip().split("\n", 1)[0]
    subject = first_line[:100] if first_line else "A message from DineroBook"

    recipients = User.query.filter(
        User.is_active == True,
        User.email != "",
        User.notify_announcement_email == True,
        User.email_bounced_at.is_(None),
    ).all()
    now = datetime.utcnow()
    notifications_url = f"{base_url}/account/notifications"
    plain_body = (
        f"Announcement from DineroBook\n\n"
        f"{ann.message}\n\n"
        f"— DineroBook ({base_url})\n\n"
        f"Don't want announcement emails? Turn them off:\n"
        f"  {notifications_url}\n"
    )
    sent = 0
    for u in recipients:
        with app.test_request_context("/"):
            html = render_template(
                "emails/announcement.html",
                preheader=ann.message[:120],
                subject=subject,
                message=ann.message,
                level=ann.level or "info",
                app_url=base_url,
                notifications_url=notifications_url,
                year=now.year,
                base_url=base_url,
            )
        _send_email(u.email, subject, plain_body, html=html)
        sent += 1
    ann.broadcast_sent_at = now
    db.session.commit()
    return sent

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
    q = User.query.filter_by(role="superadmin")
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
        RecoveryCode.query.filter_by(user_id=sa.id).delete()
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

# Sample rate matrices for the seeded display. Two countries with
# realistic-looking data so the reviewer immediately sees a useful
# rate board instead of "No country sections yet." Numbers are
# illustrative; refreshable via re-running the command.
_REVIEWER_SAMPLE_DATA = [
    {
        "country_code": "MX",
        "country_name": "Mexico",
        "mt_companies": "Maxi, Cibao, Vigo",
        "banks": [
            {"name": "Bancomer", "rates": {"Maxi": 18.36, "Cibao": 18.07, "Vigo": 18.51}},
            {"name": "Banorte",  "rates": {"Maxi": 18.41, "Cibao": 18.12, "Vigo": 18.56}},
            {"name": "Santander", "rates": {"Maxi": 18.46, "Cibao": 18.17, "Vigo": 18.61}},
        ],
    },
    {
        "country_code": "GT",
        "country_name": "Guatemala",
        "mt_companies": "Maxi, Vigo",
        "banks": [
            {"name": "Banco Industrial", "rates": {"Maxi": 7.52, "Vigo": 7.59}},
            {"name": "Banrural",         "rates": {"Maxi": 7.50, "Vigo": 7.57}},
        ],
    },
]

@app.cli.command("seed-amazon-reviewer")
@click.option("--password", default=None,
              help="Override the auto-generated password (≥ 12 chars). "
                   "Omit to generate a fresh URL-safe random.")
@click.option("--keep-data", is_flag=True,
              help="Don't reseed sample countries/banks/rates if any already "
                   "exist — useful for in-place password rotation.")
def seed_amazon_reviewer_cmd(password, keep_data):
    """Provision (or refresh) the Amazon Appstore reviewer test
    account: store + employee user + comped tv_display addon + sample
    rates. Run on the Render shell before submitting a Fire TV app
    update for review.

    Idempotent — re-running rotates the password and re-comps the
    addon. Pass --password to set a known value (≥ 12 chars), or
    omit to generate a random one."""
    REVIEWER_SLUG = "amazon-reviewer"
    REVIEWER_USERNAME = "amazon-review@dinerobook.com"
    REVIEWER_STORE_NAME = "Amazon Reviewer Sandbox"

    # 1. Find or create the store.
    store = Store.query.filter_by(slug=REVIEWER_SLUG).first()
    if store is None:
        store = Store(
            name=REVIEWER_STORE_NAME, slug=REVIEWER_SLUG,
            email=REVIEWER_USERNAME,
            plan="basic",
            trial_ends_at=datetime.utcnow() + timedelta(days=3650),
            grace_ends_at=datetime.utcnow() + timedelta(days=3650),
            is_active=True,
        )
        db.session.add(store)
        db.session.flush()
        created_store = True
    else:
        created_store = False

    # Force-comp the plan + addon every run — superadmin may have
    # toggled them off, or a previous run may have set partial state.
    store.plan = "basic"
    store.addons = "tv_display"
    store.is_active = True

    # 2. Find or create the employee user.
    user = User.query.filter_by(
        store_id=store.id, username=REVIEWER_USERNAME).first()
    if user is None:
        user = User(
            store_id=store.id, username=REVIEWER_USERNAME,
            full_name="Amazon Appstore Reviewer",
            role="employee",
            is_active=True,
        )
        db.session.add(user)
        created_user = True
    else:
        # Force role + active in case a prior run / superadmin left
        # the row in a weird state.
        user.role = "employee"
        user.is_active = True
        created_user = False

    # 3. Set password — operator-supplied or freshly random.
    if password is None:
        password = secrets.token_urlsafe(12)
    elif len(password) < 12:
        click.echo("--password must be at least 12 chars. Aborting.", err=True)
        raise click.Abort()
    user.set_password(password)

    db.session.commit()

    # 4. Ensure the TVDisplay row exists (lazy-creates with token).
    display = _ensure_tv_display(store)

    # 5. Seed sample rate data unless the operator opted out OR data
    #    already exists. Reseeding is destructive (wipes prior
    #    countries + banks + rates) so the reviewer always sees the
    #    same canonical view; --keep-data preserves whatever's there.
    has_existing_data = TVDisplayCountry.query.filter_by(
        display_id=display.id).first() is not None
    seeded_counts = {"countries": 0, "banks": 0, "rates": 0}
    if not (keep_data and has_existing_data):
        # Wipe in chain order so FKs don't reject the deletes. We
        # use synchronize_session='fetch' so SQLAlchemy properly
        # removes the deleted rows from the session identity map —
        # otherwise re-inserts on the same PKs (SQLite reuses freed
        # auto-increment PKs aggressively) trip a collision warning.
        existing_countries = TVDisplayCountry.query.filter_by(
            display_id=display.id).all()
        for c in existing_countries:
            existing_banks = TVDisplayPayoutBank.query.filter_by(
                country_id=c.id).all()
            for b in existing_banks:
                TVDisplayRate.query.filter_by(bank_id=b.id).delete(
                    synchronize_session="fetch")
            TVDisplayPayoutBank.query.filter_by(
                country_id=c.id).delete(synchronize_session="fetch")
        TVDisplayCountry.query.filter_by(
            display_id=display.id).delete(synchronize_session="fetch")
        db.session.commit()

        for sort_idx, country in enumerate(_REVIEWER_SAMPLE_DATA, start=1):
            c = TVDisplayCountry(
                display_id=display.id,
                country_code=country["country_code"],
                country_name=country["country_name"],
                mt_companies=country["mt_companies"],
                sort_order=sort_idx * 10,
            )
            db.session.add(c)
            db.session.flush()
            seeded_counts["countries"] += 1
            for bank_idx, bank in enumerate(country["banks"], start=1):
                b = TVDisplayPayoutBank(
                    country_id=c.id, bank_name=bank["name"],
                    sort_order=bank_idx * 10,
                )
                db.session.add(b)
                db.session.flush()
                seeded_counts["banks"] += 1
                for company, rate in bank["rates"].items():
                    db.session.add(TVDisplayRate(
                        bank_id=b.id, mt_company=company, rate=rate))
                    seeded_counts["rates"] += 1
        display.last_updated_at = datetime.utcnow()
        db.session.commit()

    # 6. Print everything the reviewer needs.
    base_url = os.environ.get("BASE_URL", "https://dinerobook.com")
    login_url = f"{base_url.rstrip('/')}/login/{REVIEWER_SLUG}"
    click.echo("")
    click.echo("✅ Amazon Reviewer account ready")
    click.echo("")
    click.echo(f"   Login URL:   {login_url}")
    click.echo(f"   Username:    {REVIEWER_USERNAME}")
    click.echo(f"   Password:    {password}")
    click.echo(f"   Role:        employee  (cannot reach superadmin / billing)")
    click.echo(f"   Store:       {REVIEWER_STORE_NAME}  (slug: {REVIEWER_SLUG})")
    click.echo(f"   Plan:        basic  (comped — no Stripe billing)")
    click.echo(f"   Add-ons:     tv_display")
    if not (keep_data and has_existing_data):
        click.echo(f"   Sample data: {seeded_counts['countries']} countries, "
                   f"{seeded_counts['banks']} banks, {seeded_counts['rates']} rate cells")
    else:
        click.echo("   Sample data: untouched (--keep-data was set)")
    click.echo("")
    click.echo("   Submit these to Amazon as the test credentials. The")
    click.echo("   reviewer signs in, navigates to TV Display in the")
    click.echo("   sidebar, clicks 'Generate code', and pairs the test")
    click.echo("   Fire TV. The board will show the seeded sample rates.")
    click.echo("")
    if created_store: click.echo("   (Store was created on this run.)")
    if created_user:  click.echo("   (User was created on this run.)")

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
# Column additions applied to existing installs on boot. Each entry is
#   (table_name, column_name, DDL snippet after ADD COLUMN)
# Kept here so a single helper can migrate any table.
_ADDED_COLUMNS = [
    ("store",    "addons",               "VARCHAR(255) DEFAULT ''"),
    ("store",    "canceled_at",          "TIMESTAMP NULL"),
    ("store",    "data_retention_until", "TIMESTAMP NULL"),
    ("transfer", "federal_tax",          "FLOAT DEFAULT 0"),
    ("transfer", "sender_phone",         "VARCHAR(40) DEFAULT ''"),
    ("transfer", "customer_id",          "INTEGER NULL"),
    ("transfer", "sender_phone_country", "VARCHAR(8) DEFAULT ''"),
    ("transfer", "sender_address",       "VARCHAR(255) DEFAULT ''"),
    ("transfer", "sender_dob",           "DATE NULL"),
    ("store",    "companies",            "VARCHAR(500) DEFAULT ''"),
    ("mt_summary","federal_tax",         "FLOAT DEFAULT 0"),
    # Processed-by attribution. Nullable so old transfers stay valid; the
    # transfer form enforces a non-empty value for new saves.
    ("transfer", "employee_id",          "INTEGER NULL"),
    ("transfer", "employee_name",        "VARCHAR(120) DEFAULT ''"),
    ("store",    "referred_by_code_id",  "INTEGER NULL"),
    ("store",    "referee_credit_applied_at", "TIMESTAMP NULL"),
    # Per-store federal tax rate — 0.01 = 1%. Existing stores get 0.01 via
    # the DEFAULT; admins can change via Settings → Store.
    ("store",    "federal_tax_rate",     "FLOAT DEFAULT 0.01 NOT NULL"),
    # 2FA (TOTP) columns on user. Mandatory for superadmin; optional/unused
    # for other roles today. Nullable so existing rows stay valid on upgrade.
    ("user",     "totp_secret",          "VARCHAR(64) NULL"),
    ("user",     "totp_enrolled_at",     "TIMESTAMP NULL"),
    # Service performed: Money Transfer (default, taxed) vs Bill Payment /
    # Top Up / Recharge (no federal tax). Existing rows backfill to
    # "Money Transfer" via the DEFAULT, which preserves their current tax
    # state because the tax was already computed at save time.
    ("transfer", "service_type",         "VARCHAR(30) DEFAULT 'Money Transfer' NOT NULL"),
    # Billing cadence. "monthly" or "yearly" for paid subscribers; ""
    # for trial / inactive. Backfilled by the Stripe webhook on the
    # next activation/renewal for any store that upgrades or
    # reactivates after this column ships.
    ("store",    "billing_cycle",        "VARCHAR(10) DEFAULT ''"),
    # Daily-book lock. When locked_at is not NULL the report + its
    # line-item tables reject writes until an admin explicitly unlocks.
    ("daily_report", "locked_at",        "TIMESTAMP NULL"),
    ("daily_report", "locked_by",        "INTEGER NULL"),
    # Per-user profile fields. Email is the headline addition — today
    # username doubles as email for most accounts but isn't validated
    # as one, and the password-reset flow currently uses username
    # which gets messy when the username isn't an email. phone +
    # timezone are quality-of-life. last_login_at is read-only
    # (login routes set it) and surfaces as a "you last signed in
    # from X" signal on the Security page.
    ("user",     "email",                "VARCHAR(255) DEFAULT ''"),
    ("user",     "phone",                "VARCHAR(40) DEFAULT ''"),
    ("user",     "timezone",             "VARCHAR(60) DEFAULT ''"),
    ("user",     "last_login_at",        "TIMESTAMP NULL"),
    # Notification preferences. Opt-out defaults (reminder emails are
    # the kind of thing users want by default; only silence them
    # explicitly). Employees and superadmin ignore the trial column
    # since they aren't tied to a trialing store.
    ("user",     "notify_trial_reminders", "BOOLEAN DEFAULT TRUE"),
    # Trial-reminder dedup. Stamped the first time the reminder
    # cron sends an email for a given trial; cleared on resubscribe
    # (so a second trial, e.g. after reactivation, gets a fresh
    # reminder). Without this the cron would spam daily once the
    # store enters expiring_soon.
    ("store",    "trial_reminder_sent_at", "TIMESTAMP NULL"),
    # Email deliverability suppression. When Resend posts an
    # `email.bounced` webhook with bounce_type=hard for this user's
    # address, we stamp this column. `_send_email()` skips any
    # recipient whose matching User row is stamped, so we stop
    # hammering Resend with guaranteed-failing addresses. Cleared by
    # a superadmin "clear suppression" action (not yet built — one
    # for later when we have a user who fixes their mailbox and
    # wants to un-bounce).
    ("user",     "email_bounced_at",     "TIMESTAMP NULL"),
    # Announcement broadcast — per-user opt-in flag + per-announcement
    # "send requested" + dedup stamp. Opt-in default False because
    # announcements fan out to every user (unlike trial reminders
    # which only hit the user's own store).
    ("user",         "notify_announcement_email", "BOOLEAN DEFAULT FALSE"),
    ("announcement", "broadcast_requested",       "BOOLEAN DEFAULT FALSE"),
    ("announcement", "broadcast_sent_at",         "TIMESTAMP NULL"),
    # UI theme preference (dark | light). Default dark to match the
    # historical behavior — users opt in to light explicitly.
    ("user",         "theme_preference",          "VARCHAR(8) DEFAULT 'dark'"),
    # Return-check workflow ↔ daily-book payback line item link.
    # Auto-created line items carry the source ReturnCheck.id so we
    # can update / delete the shadow row when the return check is
    # edited or reopened.
    ("daily_line_item", "return_check_id",        "INTEGER NULL"),
    # TV Display companion-app pairing (Fire TV / Google TV).
    # DEPRECATED columns — the pair-code state moved to the
    # TVPendingPair table when we inverted the flow. Left in the
    # schema because CLAUDE.md forbids dropping columns from a
    # running DB; safe to remove via a backfill migration later.
    ("tv_display",     "pair_code",              "VARCHAR(8) DEFAULT ''"),
    ("tv_display",     "pair_code_expires_at",   "TIMESTAMP NULL"),
    # Phase 2 bank-transaction sync — rate-limit accounting on Store.
    # Each Stripe Transaction.list call is billed, so manual syncs are
    # gated by a per-store cooldown (15 min) and daily cap (5/day).
    ("store",          "bank_sync_last_at",      "TIMESTAMP NULL"),
    ("store",          "bank_sync_count_today",  "INTEGER DEFAULT 0"),
    ("store",          "bank_sync_count_date",   "DATE NULL"),
    # Phase 3 reconcile — back-link from BankTransaction to the
    # DailyLineItem we created when the row was categorized into a
    # daily-book bucket. Lets "Un-reconcile" delete the line item.
    ("bank_transaction", "daily_line_item_id",   "INTEGER NULL"),
    # Single consolidated bank-charges P&L column. Replaces the
    # Nizari-specific 210/230 split in the UI. The legacy columns stay
    # in the schema for historic data; the read-time sum on the
    # monthly_report page rolls them into the total.
    ("monthly_financial", "bank_charges_total",  "REAL DEFAULT 0"),
    # Operator-set nickname for a connected bank account. When set the
    # transactions list and P&L breakdown show this instead of the
    # ••<last4>. Forward-compat for stores that may add a second
    # account at the same bank — distinct nicknames > opaque last4s.
    ("stripe_bank_account", "nickname",          "VARCHAR(60) DEFAULT ''"),
]

def _ensure_added_columns():
    """Apply the _ADDED_COLUMNS migrations. Idempotent and safe on every boot.

    Table names are ALWAYS quoted — `user` is a Postgres reserved word
    (it aliases CURRENT_USER), so `ALTER TABLE user …` throws a syntax
    error in PG even though the table exists. Quoting (`"user"`) makes
    the reserved-word issue go away; sqlite accepts the quotes too.

    Each ALTER runs in its own transaction on Postgres so one failure
    doesn't abort the others — and we log the specific column that
    failed instead of a silent "column migration skipped"."""
    try:
        dialect = db.engine.dialect.name
    except Exception as e:
        app.logger.warning(f"column migration skipped (no engine): {e}")
        return

    if dialect == "sqlite":
        try:
            with db.engine.connect() as conn:
                existing = {}
                for table, _, _ in _ADDED_COLUMNS:
                    if table not in existing:
                        rows = conn.exec_driver_sql(
                            f'PRAGMA table_info("{table}");')
                        existing[table] = [r[1] for r in rows]
                for table, name, ddl in _ADDED_COLUMNS:
                    if name not in existing.get(table, []):
                        try:
                            conn.exec_driver_sql(
                                f'ALTER TABLE "{table}" ADD COLUMN {name} {ddl}')
                        except Exception as e:
                            app.logger.warning(
                                f"sqlite ADD COLUMN failed for {table}.{name}: {e}")
                conn.commit()
        except Exception as e:
            app.logger.warning(f"sqlite column migration skipped: {e}")
        return

    # Postgres path. Each ALTER in its own transaction — so a failure on
    # one doesn't poison the rest (PG aborts the whole tx on any error).
    for table, name, ddl in _ADDED_COLUMNS:
        try:
            with db.engine.begin() as conn:
                conn.exec_driver_sql(
                    f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS {name} {ddl}')
        except Exception as e:
            app.logger.warning(f"pg ADD COLUMN failed for {table}.{name}: {e}")

# Legacy tables that have been removed from the model registry but may
# still exist in production databases. DROP TABLE IF EXISTS is idempotent
# on every restart — safe to leave forever.
_DROPPED_TABLES = ["simplefin_config"]

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
        if not FeatureFlag.query.filter_by(key=key).first():
            db.session.add(FeatureFlag(
                key=key, label=label, description=description,
                enabled_by_default=enabled,
            ))
    db.session.commit()

# ── TV Display catalog seed ──────────────────────────────────
#
# Curated default lists for the TV-display country editor's
# company-column picker and bank-row picker. Idempotent — only
# inserts entries whose slug doesn't already exist, so the
# superadmin can edit / disable / re-sort without the next boot
# clobbering their changes.
#
# Slugs are URL-safe lowercase identifiers; display_name is what
# operators see in the picker and on the public board. logo_url
# stays empty here (Phase 1 ships text-only; Phase 2 wires up the
# upload flow).
_DEFAULT_TV_COMPANIES = [
    # (slug, display_name, sort_order)
    ("intermex",       "Intermex",         10),
    ("maxi",           "Maxi",             20),
    ("barri",          "Barri",            30),
    ("vigo",           "Vigo",             40),
    ("ria",            "RIA",              50),
    ("moneygram",      "MoneyGram",        60),
    ("western_union",  "Western Union",    70),
    ("cibao",          "Cibao Express",    80),
    ("sigue",          "Sigue",            90),
    ("dolex",          "Dolex",           100),
    ("boss_revolution","Boss Revolution", 110),
    ("xoom",           "Xoom",            120),
]

# Banks scoped per country. Country codes are ISO-2 uppercase.
# Each tuple is (slug, display_name, country_code, sort_order).
_DEFAULT_TV_BANKS = [
    # ── Mexico ───────────────────────────────────────────────
    ("mx_bbva_bancomer", "BBVA Bancomer",    "MX", 10),
    ("mx_banorte",       "Banorte",          "MX", 20),
    ("mx_santander",     "Santander México", "MX", 30),
    ("mx_banamex",       "Citibanamex",      "MX", 40),
    ("mx_hsbc",          "HSBC México",      "MX", 50),
    ("mx_scotiabank",    "Scotiabank",       "MX", 60),
    ("mx_bancoppel",     "Bancoppel",        "MX", 70),
    ("mx_banco_azteca",  "Banco Azteca",     "MX", 80),
    ("mx_inbursa",       "Inbursa",          "MX", 90),
    ("mx_elektra",       "Elektra",          "MX",100),
    ("mx_walmart",       "Walmart",          "MX",110),
    ("mx_soriana",       "Soriana",          "MX",120),

    # ── Guatemala ────────────────────────────────────────────
    ("gt_industrial",    "Banco Industrial", "GT", 10),
    ("gt_banrural",      "Banrural",         "GT", 20),
    ("gt_bac",           "BAC Credomatic",   "GT", 30),
    ("gt_gtcontinental", "G&T Continental",  "GT", 40),
    ("gt_bantrab",       "Bantrab",          "GT", 50),
    ("gt_vivibanco",     "Vivibanco",        "GT", 60),

    # ── Honduras ─────────────────────────────────────────────
    ("hn_atlantida",     "Banco Atlántida",  "HN", 10),
    ("hn_banpais",       "Banpais",          "HN", 20),
    ("hn_ficohsa",       "Ficohsa",          "HN", 30),
    ("hn_bac",           "BAC Credomatic",   "HN", 40),
    ("hn_occidente",     "Banco de Occidente","HN",50),
    ("hn_azteca",        "Banco Azteca",     "HN", 60),

    # ── El Salvador ──────────────────────────────────────────
    ("sv_agricola",      "Banco Agrícola",   "SV", 10),
    ("sv_cuscatlan",     "Banco Cuscatlán",  "SV", 20),
    ("sv_davivienda",    "Davivienda",       "SV", 30),
    ("sv_bac",           "BAC Credomatic",   "SV", 40),
    ("sv_hipotecario",   "Banco Hipotecario","SV", 50),

    # ── Dominican Republic ───────────────────────────────────
    ("do_banreservas",   "Banreservas",          "DO", 10),
    ("do_popular",       "Banco Popular Dominicano","DO", 20),
    ("do_bhd",           "BHD León",             "DO", 30),
    ("do_santa_cruz",    "Banco Santa Cruz",     "DO", 40),
    ("do_cibao",         "Asociación Cibao",     "DO", 50),
]

# Curated country list for the TV-display country picker. Phase 3
# of the logo rollout — replaces the free-text country_name +
# country_code inputs with a single dropdown of common destinations
# our customers send remittances to.
#
# Order is intentional, not alphabetical: the heaviest US→LATAM
# corridors appear first so the typical operator picks from the
# top of the list. Add more here as new corridors come online.
#
# (iso2, country_name) — flag emoji is computed from iso2 by the
# existing _country_flag_emoji() helper; we don't store it.
_TV_COUNTRY_PICKER = [
    ("MX", "Mexico"),
    ("GT", "Guatemala"),
    ("HN", "Honduras"),
    ("SV", "El Salvador"),
    ("DO", "Dominican Republic"),
    ("NI", "Nicaragua"),
    ("CR", "Costa Rica"),
    ("PA", "Panama"),
    ("CO", "Colombia"),
    ("EC", "Ecuador"),
    ("PE", "Peru"),
    ("VE", "Venezuela"),
    ("CU", "Cuba"),
    ("HT", "Haiti"),
    ("JM", "Jamaica"),
    ("BR", "Brazil"),
    ("AR", "Argentina"),
    ("CL", "Chile"),
    ("BO", "Bolivia"),
    ("PY", "Paraguay"),
    ("UY", "Uruguay"),
    ("PH", "Philippines"),
    ("IN", "India"),
    ("PK", "Pakistan"),
    ("BD", "Bangladesh"),
    ("VN", "Vietnam"),
    ("NG", "Nigeria"),
    ("GH", "Ghana"),
    ("KE", "Kenya"),
    ("ET", "Ethiopia"),
]


def _seed_tv_catalogs():
    """Pre-load the curated MT-company + bank pickers. Idempotent —
    re-running only inserts entries with new slugs, so superadmin
    edits are preserved across deploys."""
    for slug, display_name, sort_order in _DEFAULT_TV_COMPANIES:
        if not TVCompanyCatalog.query.filter_by(slug=slug).first():
            db.session.add(TVCompanyCatalog(
                slug=slug, display_name=display_name,
                sort_order=sort_order, is_active=True,
            ))
    for slug, display_name, country_code, sort_order in _DEFAULT_TV_BANKS:
        if not TVBankCatalog.query.filter_by(slug=slug).first():
            db.session.add(TVBankCatalog(
                slug=slug, display_name=display_name,
                country_code=country_code,
                sort_order=sort_order, is_active=True,
            ))
    db.session.commit()

def _seed_tv_logos_from_disk():
    """One-shot importer: scan static/seed-logos/{companies,banks}/
    for files named <slug>.{svg,png,jpg,jpeg,webp} and import any
    that aren't already in TVCatalogLogo. Idempotent — re-running
    only inserts new entries; existing logos (uploaded via the
    superadmin UI or a previous boot) are left alone.

    The intent: drop logo files into a directory, redeploy, and
    they auto-load. Lets a designer / contractor populate the
    catalog by file-drop without clicking through the upload UI
    46 times. Operators can still upload + replace via the UI;
    that path takes precedence (we only import when no logo row
    exists for the slug)."""
    seed_dir = os.path.join(app.root_path, "static", "seed-logos")
    if not os.path.isdir(seed_dir):
        return 0

    # MIME type by file extension. Keep this set in sync with
    # _TV_LOGO_ALLOWED_MIMES (the upload-side whitelist).
    ext_to_mime = {
        ".svg":  "image/svg+xml",
        ".png":  "image/png",
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }

    imported = 0
    # Plural directory names — "company" → "companies" is irregular,
    # so spell them out explicitly rather than naïve concat.
    type_to_dir = {"company": "companies", "bank": "banks"}
    for catalog_type, sub_name in type_to_dir.items():
        sub = os.path.join(seed_dir, sub_name)
        if not os.path.isdir(sub):
            continue
        for filename in os.listdir(sub):
            path = os.path.join(sub, filename)
            if not os.path.isfile(path):
                continue
            slug, ext = os.path.splitext(filename)
            slug = slug.strip().lower()
            ext = ext.lower()
            mime = ext_to_mime.get(ext)
            if not mime or not slug:
                continue
            # Skip files that don't match a known catalog row —
            # silently, since dropping logos for entries we'll add
            # later shouldn't crash the boot.
            parent = (TVCompanyCatalog if catalog_type == "company"
                       else TVBankCatalog).query.filter_by(slug=slug).first()
            if parent is None:
                continue
            # Don't override an operator's existing upload.
            if TVCatalogLogo.query.filter_by(
                    catalog_type=catalog_type, slug=slug).first() is not None:
                continue
            try:
                with open(path, "rb") as fh:
                    raw_blob = fh.read()
            except OSError:
                continue
            if not raw_blob or len(raw_blob) > _TV_LOGO_MAX_BYTES:
                continue
            # Same normalization the upload route runs — drop-in
            # files end up at the standard 600x200 PNG canvas (or
            # pass through for SVG).
            blob, normalized_mime = _normalize_logo_blob(raw_blob, mime)
            db.session.add(TVCatalogLogo(
                catalog_type=catalog_type, slug=slug,
                mime_type=normalized_mime,
                blob=blob, file_size=len(blob),
                updated_at=datetime.utcnow(),
            ))
            # Mirror the public URL into the parent row's logo_url
            # so non-superadmin code can resolve without a logo-table
            # lookup. Hardcoded path (not url_for) because this seed
            # runs inside app_context but not request_context, where
            # url_for would refuse to build a path without SERVER_NAME.
            parent.logo_url = f"/tv/logo/{catalog_type}/{slug}"
            imported += 1
    if imported:
        db.session.commit()
    return imported

def _backfill_tv_country_codes():
    """One-shot helper: walk TVDisplayCountry, fill in missing
    country_code for rows whose country_name matches an entry in the
    curated picker. Runs on every boot but is a no-op once every row
    has a code (idempotent — only matches rows where country_code is
    NULL or empty).

    Why: pre-PR-C rows were created via free-text inputs where the
    operator could type the name without an ISO-2. The flag emoji
    is computed from country_code, so those legacy rows render
    flagless on the public board until we backfill."""
    name_to_iso = {name.lower(): iso for iso, name in _TV_COUNTRY_PICKER}
    # Common synonyms / variations the operator might have typed.
    # Lower-case keys; keep the list short — we want safety, not
    # heuristics that misclassify.
    name_to_iso.update({
        "republica dominicana": "DO",
        "dominican republic":   "DO",
        "el salvador":          "SV",
        "costa rica":            "CR",
    })
    fixed = 0
    rows = TVDisplayCountry.query.filter(
        db.or_(TVDisplayCountry.country_code.is_(None),
               TVDisplayCountry.country_code == "")
    ).all()
    for row in rows:
        guess = name_to_iso.get((row.country_name or "").strip().lower())
        if guess:
            row.country_code = guess
            fixed += 1
    if fixed:
        db.session.commit()
    return fixed

def _rename_maxi_transfer_to_maxi():
    """One-time idempotent backfill: rename legacy 'Maxi Transfer' to 'Maxi'
    in every place a company name is persisted. Safe on every boot — after
    the first run, nothing matches and the update is a no-op."""
    try:
        Transfer.query.filter_by(company="Maxi Transfer").update({"company": "Maxi"})
        ACHBatch.query.filter_by(company="Maxi Transfer").update({"company": "Maxi"})
        MoneyTransferSummary.query.filter_by(company="Maxi Transfer").update({"company": "Maxi"})
        # Store.companies is a comma-separated string — split, replace, rejoin.
        for s in Store.query.filter(Store.companies.like("%Maxi Transfer%")).all():
            parts = [p.strip() for p in (s.companies or "").split(",") if p.strip()]
            s.companies = ",".join(["Maxi" if p == "Maxi Transfer" else p for p in parts])
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.warning(f"Maxi Transfer rename backfill skipped: {e}")

def init_db():
    with app.app_context():
        db.create_all()
        _ensure_added_columns()
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
        _seed_tv_catalogs()
        # Backfill country_code on legacy TVDisplayCountry rows so
        # the flag emoji renders. Idempotent — no-op once all rows
        # have a code.
        try:
            n_fixed = _backfill_tv_country_codes()
            if n_fixed:
                app.logger.info(f"Backfilled country_code on {n_fixed} TV-display country rows.")
        except Exception as e:
            app.logger.warning(f"TV country-code backfill skipped: {e}")
        # Auto-import logos that operators dropped into the
        # static/seed-logos/{companies,banks}/ directory. Idempotent —
        # never overrides UI-uploaded logos, never crashes on a
        # missing directory.
        try:
            n_imported = _seed_tv_logos_from_disk()
            if n_imported:
                app.logger.info(f"Imported {n_imported} TV logos from static/seed-logos/.")
        except Exception as e:
            app.logger.warning(f"TV logo seed-disk import skipped: {e}")
        if not User.query.filter_by(username="superadmin",store_id=None).first():
            sa=User(username="superadmin",full_name="Platform Owner",role="superadmin",store_id=None)
            sa.set_password(os.environ.get("SUPERADMIN_PASSWORD","super2025!")); db.session.add(sa); db.session.commit()
            print("✅ Superadmin: superadmin / super2025!")
        # No demo store on fresh boot — this is a live SaaS, the operator
        # creates their own stores. The superadmin seed above is the only
        # row a fresh DB needs. (2FA is mandatory and enforced at login.)

init_db()

if __name__=="__main__":
    port=int(os.environ.get("PORT",5000))
    print(f"🚀 DineroBook → http://0.0.0.0:{port}")
    app.run(host="0.0.0.0",port=port,debug=False)
