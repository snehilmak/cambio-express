"""Tenancy — Models.

The multi-tenant primitives: who owns the system, who works for which
store, how owners link multiple stores together.

* ``Store``             — one row per business that bought DineroBook.
                          Carries plan / billing / addon / trial /
                          retention state.
* ``User``              — every login account, scoped to a store
                          (or NULL for superadmin). Carries 2FA
                          state, notification toggles, profile
                          fields.
* ``StoreEmployee``     — the per-store roster of employee NAMES
                          (separate from login accounts — all in-store
                          employees share one User login).
* ``StoreOwnerLink``    — many-to-many between umbrella owners and
                          the stores they oversee.
* ``OwnerConnectCode``  — owner-minted invite code a store admin
                          redeems to connect their store.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON, Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer,
    String, UniqueConstraint,
)
from api.Core.PasswordHash import check_password_hash, generate_password_hash

from api.Core.Database import Base


class Store(Base):
    __tablename__ = "store"
    id            = Column(Integer, primary_key=True)
    name          = Column(String(120), nullable=False)
    slug          = Column(String(60), unique=True, nullable=False)
    email         = Column(String(120), default="")
    phone         = Column(String(40), default="")
    address       = Column(String(255), default="")
    plan          = Column(String(30), default="trial")
    # Billing cadence for paid plans. "" for trial / inactive; "monthly"
    # or "yearly" for basic / pro. Set from the Stripe price_id in the
    # checkout webhook. Lets the superadmin overview split paid counts
    # by cycle and compute a precise MRR.
    billing_cycle = Column(String(10), default="")
    stripe_customer_id     = Column(String(60), default="")
    stripe_subscription_id = Column(String(60), default="")
    # Phase 2 bank-transaction sync rate-limit. Each Transaction.list
    # call costs per-account; we cap manual syncs at MAX_BANK_SYNCS_PER_DAY
    # and require BANK_SYNC_COOLDOWN_MINUTES between them.
    bank_sync_last_at      = Column(DateTime, nullable=True)
    bank_sync_count_today  = Column(Integer, default=0)
    bank_sync_count_date   = Column(Date, nullable=True)
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=datetime.utcnow)
    trial_ends_at = Column(DateTime, nullable=True)
    grace_ends_at = Column(DateTime, nullable=True)
    addons        = Column(String(255), default="")
    canceled_at           = Column(DateTime, nullable=True)
    data_retention_until  = Column(DateTime, nullable=True)
    # Superadmin store freeze (PR C). When ``frozen_at`` is set the store
    # is suspended by the platform operator (abuse, dispute, non-payment
    # follow-up) — DISTINCT from trial-expired and from retention-pause.
    # The SPA gates a frozen store's users to a "suspended, contact
    # support" screen. Cleared by the superadmin unfreeze action.
    # ``frozen_reason`` is operator context shown in the audit log + the
    # superadmin UI (not surfaced to the store's users).
    frozen_at             = Column(DateTime, nullable=True)
    frozen_reason         = Column(String(200), default="")
    # Trial-reminder dedup. send_trial_reminders() stamps this the
    # first time it sends; cleared on checkout.session.completed so a
    # second trial (post-reactivation) gets its own fresh reminder.
    trial_reminder_sent_at = Column(DateTime, nullable=True)
    # Daily-summary digest dedup. Stamped by the
    # ``send_daily_summaries`` cron after a successful pass — a
    # re-run on the same date is a no-op. Set NEVER cleared (once
    # we've sent for a date, we've sent).
    daily_summary_sent_for = Column(Date, nullable=True)
    # Same idempotency marker for the missed-shift digest cron.
    # Set by ``Notifications/Services/missed_shifts.run`` after a
    # store's digest is processed for a given date.
    missed_shifts_sent_for = Column(Date, nullable=True)
    # Comma-separated list of money-transfer companies this store works
    # with. Empty string falls through to DEFAULT_MT_COMPANIES. Resolve
    # via store_mt_companies(store) — never read this column directly.
    companies     = Column(String(500), default="")
    # Federal tax rate (decimal — 0.01 = 1%) applied to every transfer at
    # save time. The transfer form treats Federal Tax as read-only and the
    # server always recomputes from send_amount × this rate, so employees
    # can't tamper with it. Admins override via Settings → Store if their
    # state or vendor has a different rate.
    federal_tax_rate = Column(Float, default=0.01, nullable=False)
    # Receipt customization. Stamped onto every printed transfer
    # receipt under /app/transfers/{id}/receipt. All three default
    # to "" so an unconfigured store falls back to the plain
    # receipt layout (store name + system footer).
    #   - receipt_logo_url: public URL of the store's logo image
    #     for the receipt header. Empty → use the store name as a
    #     text wordmark.
    #   - receipt_footer:   free-form text printed at the bottom
    #     of every receipt. Refund policy, compliance line,
    #     thank-you. Trimmed to keep the printable area on one
    #     thermal-printer page.
    #   - receipt_tax_id:   federal tax ID / EIN / VAT — printed
    #     near the header when set. Some jurisdictions require it.
    receipt_logo_url = Column(String(500), default="")
    receipt_footer   = Column(String(500), default="")
    receipt_tax_id   = Column(String(40),  default="")
    legal_name       = Column(String(200), default="")
    ein              = Column(String(20),  default="")
    business_address = Column(String(500), default="")
    # IANA timezone (e.g. ``America/Chicago``). Used as a fallback
    # for date / time rendering when the viewing user hasn't set
    # their own ``User.timezone``. Empty string means "unset" —
    # the renderer keeps falling back (to the browser default).
    # Admins set this on /app/settings so daily-book timestamps,
    # audit-log entries, etc. render in store-local time for
    # operators who haven't customized their profile.
    timezone         = Column(String(60), default="")
    # Weekly business-hours schedule. JSON list of exactly 7
    # entries (one per ISO weekday, Mon-Sun) — see
    # ``api/Modules/Admin/Services/store_hours.py`` for the
    # canonical shape + validation. NULL means "not configured"
    # — the settings page hydrates a sane default (Mon-Sat
    # 09:00-18:00 / Sun closed) so the operator can save in one
    # click.
    store_hours      = Column(JSON, nullable=True)
    # When True, the transfer create / update endpoints refuse
    # saves outside the configured ``store_hours`` window. The
    # soft yellow warning on the New Transfer form fires
    # independently — this toggle is what escalates the warning
    # into a hard 422 gate. Default False so existing stores
    # keep working without opt-in.
    enforce_business_hours = Column(Boolean, default=False)
    # Anti-buddy-punching gate — when True, every clock-in /
    # clock-out demands a fresh WebAuthn assertion from the
    # roster member's registered passkey (Windows Hello,
    # Touch ID, Face ID, hardware key). Default False so
    # existing stores keep working without enrollment; the
    # admin flips it on once every active roster member has
    # registered via /app/admin/timeclock/credentials.
    timeclock_require_passkey = Column(Boolean, default=False)
    # Geofence gate (anti-buddy-punching companion to the
    # passkey toggle). When ``timeclock_require_geofence`` is
    # True, every clock-in / clock-out has to include the
    # cashier's lat/lng and land within ``radius_m`` of the
    # store's pinned location. The passkey gate proves "this
    # is the right person"; the geofence proves "they're
    # physically at the store". Admin pins the location once
    # by tapping "Use current location" at the store terminal.
    timeclock_geofence_lat       = Column(Float, nullable=True)
    timeclock_geofence_lng       = Column(Float, nullable=True)
    timeclock_geofence_radius_m  = Column(Integer, default=100)
    timeclock_require_geofence   = Column(Boolean, default=False)
    # Lateness threshold in store-local minutes: the payroll
    # history page flags an entry as "late" only when the
    # ``entry.clock_in_at`` exceeds the matching shift's
    # ``start_time`` by this many minutes.  Default 5 — small
    # enough to catch real lateness, big enough to absorb the
    # cashier walking from the door to the terminal.
    timeclock_late_minutes_threshold = Column(Integer, default=5)
    # Referral: the ReferralCode this store used when signing up (if any).
    # Set once at signup from ?ref=<code>, never mutated afterwards. We
    # use this on the first paid conversion to apply credits to both
    # sides of the referral. ``use_alter=True`` breaks the
    # Store↔ReferralCode dependency cycle during create_all / drop_all —
    # the table is created without the FK first, then the FK is added
    # via ALTER TABLE.
    referred_by_code_id = Column(Integer,
        ForeignKey("referral_code.id", use_alter=True,
                    name="fk_store_referred_by_code"),
        nullable=True)
    referee_credit_applied_at = Column(DateTime, nullable=True)


class User(Base):
    __tablename__ = "user"
    id            = Column(Integer, primary_key=True)
    store_id      = Column(Integer, ForeignKey("store.id"), nullable=True)
    username      = Column(String(80), nullable=False)
    password_hash = Column(String(200), nullable=False)
    role          = Column(String(20), default="employee")
    full_name     = Column(String(120), default="")
    created_at    = Column(DateTime, default=datetime.utcnow)
    is_active     = Column(Boolean, default=True)
    # TOTP-based 2FA. Mandatory for superadmin (see _needs_totp_enroll /
    # _totp_is_enrolled); other roles ignore these columns today. The
    # secret is base32 and stored plaintext — the DB itself is the
    # trust boundary.
    totp_secret      = Column(String(64), nullable=True)
    totp_enrolled_at = Column(DateTime, nullable=True)
    # Profile fields. email is freeform on save (we coerce-strip-lower);
    # validation lives in _update_user_profile.
    email            = Column(String(255), default="")
    phone            = Column(String(40), default="")
    timezone         = Column(String(60), default="")
    last_login_at    = Column(DateTime, nullable=True)
    # UI theme preference. Dark is the design-system default; users
    # who want light explicitly opt in via /account/profile. Stored
    # per-user (not per-device) so the preference follows the user
    # across browsers / devices. Logged-out pages always render dark.
    theme_preference = Column(String(8), default="dark")
    # Notification preferences. Opt-out (default True) for the one we
    # ship in v1 — a trial-ending reminder. Adding more toggles is one
    # column per channel here + the matching sender.
    notify_trial_reminders = Column(Boolean, default=True)
    # Announcement broadcast emails are higher-volume (every superadmin
    # announcement fans out to every opted-in user), so opt-in by default.
    notify_announcement_email = Column(Boolean, default=False)
    # Locked-day digest fires when an admin locks the daily book. Goes
    # to owners + admins of the store. Default True (mirrors the
    # trial-reminder opt-out pattern) — close-outs are a high-signal
    # event the owner usually wants to see.
    notify_locked_day_digest = Column(Boolean, default=True)
    # Daily-summary digest fires nightly via the
    # ``send_daily_summaries`` cron — one email per store with the
    # previous day's transfer count + receipts + disbursements +
    # over/short. Goes to admins + linked owners. Opt-out (default
    # True) so close-out numbers reach owners by morning.
    notify_daily_summary = Column(Boolean, default=True)
    # Per-kind push-channel toggles. Default True — once a user
    # enables browser notifications at the channel level (via
    # ``/api/v2/auth/push/subscribe``), every kind is on by
    # default and the user opts out individually. Mirrors the
    # email pattern above so the two channels stay symmetric.
    notify_trial_reminders_push    = Column(Boolean, default=True)
    notify_announcement_push       = Column(Boolean, default=True)
    notify_locked_day_digest_push  = Column(Boolean, default=True)
    notify_daily_summary_push      = Column(Boolean, default=True)
    notify_high_variance           = Column(Boolean, default=False)
    notify_high_variance_push      = Column(Boolean, default=False)
    notify_store_offline           = Column(Boolean, default=False)
    notify_store_offline_push      = Column(Boolean, default=False)
    # Deliverability suppression — stamped when Resend reports a hard
    # bounce on this user's email. ``_send_email()`` skips suppressed
    # recipients.
    email_bounced_at    = Column(DateTime, nullable=True)
    __table_args__ = (
        UniqueConstraint("store_id", "username"),
        # Cross-store username lookup. The unique constraint above
        # leads with `store_id`, so it can't serve queries that
        # filter on `username` alone — `verify_password_cross_store`
        # (the generic `/login` POST), `find_user_by_username`
        # (CLI password reset / superadmin recovery), and the
        # signup duplicate-check (`User.username == email`) all
        # scan the table without this index.
        Index("ix_user_username", "username"),
    )
    def set_password(self, pw: str) -> None:
        # ``password_hash`` is declared via SQLAlchemy 1.x
        # ``Column[str]``; the instrumented attribute accepts a
        # bare string at runtime but mypy reads the class-level
        # declaration. setattr keeps the assignment typed.
        setattr(self, "password_hash", generate_password_hash(pw))

    def check_password(self, pw: str) -> bool:
        # SQLAlchemy 1.x-style ``Column[str]`` reads as ``Column[str]``
        # instead of ``str``, even though the runtime value is a
        # bare string. Cast at the boundary to keep callers typed.
        return check_password_hash(str(self.password_hash), pw)


class StoreEmployee(Base):
    """Admin-managed list of employee NAMES per store — not login
    accounts.

    All in-store employees share a single login (the store's employee
    User account). This table holds the roster of real people whose
    names can be picked from the "Processed by" dropdown on the
    transfer form. Admins deactivate (never delete) entries so
    historical attribution survives.
    """

    __tablename__ = "store_employee"
    id         = Column(Integer, primary_key=True)
    store_id   = Column(Integer, ForeignKey("store.id"), nullable=False, index=True)
    name       = Column(String(120), nullable=False)
    is_active  = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    # Pay rate in USD/hour for the paystub computation. Default
    # 0.0 means "rate not configured" — the paystub view shows
    # the gross-pay column as a dash and the admin sets the
    # value from the Team settings page. A negative rate doesn't
    # make sense; the admin endpoint enforces ``>= 0``.
    hourly_rate = Column(Float, default=0.0, nullable=False)


class StoreOwnerLink(Base):
    __tablename__ = "store_owner_link"
    id        = Column(Integer, primary_key=True)
    owner_id  = Column(Integer, ForeignKey("user.id"), nullable=False)
    store_id  = Column(Integer, ForeignKey("store.id"), nullable=False, index=True)
    linked_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("owner_id", "store_id"),)


class OwnerConnectCode(Base):
    """Owner-generated invite code that a store admin redeems to link
    their store to the owner's umbrella.

    Flow:
        1. Owner signs up (free; can have zero linked stores).
        2. Owner mints a code from /owner/connect — 8 chars, 7-day TTL.
        3. Owner gives the code to a store admin out of band (phone, email).
        4. Store admin enters the code on /admin/settings → Owner tab.
        5. Server creates a StoreOwnerLink, marks the code used.

    Disconnect is owner-side only: /owner/unlink/<store_id>. The store
    admin sees a read-only "Connected to <Owner Name>" message and a
    note to contact the owner if they need to disconnect.
    """

    __tablename__ = "owner_connect_code"
    id               = Column(Integer, primary_key=True)
    owner_id         = Column(Integer, ForeignKey("user.id"), nullable=False)
    code             = Column(String(8), unique=True, nullable=False)
    created_at       = Column(DateTime, default=datetime.utcnow)
    expires_at       = Column(DateTime, nullable=False)
    used_at          = Column(DateTime, nullable=True)
    used_by_user_id  = Column(Integer, ForeignKey("user.id"), nullable=True)
    used_by_store_id = Column(Integer, ForeignKey("store.id"), nullable=True)
    revoked_at       = Column(DateTime, nullable=True)


__all__ = [
    "OwnerConnectCode", "Store", "StoreEmployee", "StoreOwnerLink", "User",
]
