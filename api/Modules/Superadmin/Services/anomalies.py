"""Platform anomaly detector.

Surfaced on the superadmin Overview tab. Returns a list of
`{kind, severity, store, description, href}` dicts ranked by
severity so the most-urgent items float to the top.

Each rule is independent and side-effect free; the entry point
`compute_platform_anomalies(db)` is safe to call on every page
render — the underlying queries are GROUP BYs over `transfer` /
`daily_report`, both indexed on `store_id`.

Severity scale:
  "high"   — money is moving in unusual ways; admin should look now
  "medium" — something has changed; worth asking the operator about
  "low"    — informational; user-facing copy: "FYI"

New rules go here as `_anomaly_*` helpers called from
`compute_platform_anomalies` in priority order.
"""
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from api.Modules.Billing.Models import Store


# ── Quiet-store rule ───────────────────────────────────────
ANOMALY_QUIET_LOOKBACK_ACTIVE_DAYS = 30   # store was "active" if it had transfers in this window
ANOMALY_QUIET_LOOKBACK_QUIET_DAYS  = 3    # ...but none in the most recent N days
ANOMALY_QUIET_MIN_PRIOR_TRANSFERS  = 5    # ignore tiny stores so we don't yell about idle trials

# ── Over/short rule ────────────────────────────────────────
ANOMALY_OVERSHORT_LOOKBACK_DAYS    = 7
ANOMALY_OVERSHORT_MEDIUM_THRESHOLD = 100.0   # |over_short| >= this = medium
ANOMALY_OVERSHORT_HIGH_THRESHOLD   = 200.0   # |over_short| >= this = high

# ── Cancellation-spike rule ────────────────────────────────
# When the platform sees an unusual burst of paid-store
# cancellations in a short window we surface every store in
# the burst so the operator can reach out individually.
ANOMALY_CANCELLATION_LOOKBACK_HOURS = 24
ANOMALY_CANCELLATION_SPIKE_THRESHOLD = 3

# ── Password-reset-spike rule ──────────────────────────────
# Per-user: more than N reset requests in the lookback window
# is either credential stuffing or a confused operator clicking
# repeatedly — either way it surfaces.
ANOMALY_PASSWORD_RESET_LOOKBACK_HOURS = 24
ANOMALY_PASSWORD_RESET_PER_USER_THRESHOLD = 5

# Cap the result list so the overview card stays scannable.
_MAX_ANOMALIES_RETURNED = 25


def _store_href(store) -> str:
    """SPA store-detail URL, or empty string when called with no
    store. ``/app/superadmin/stores/<slug>`` is the canonical
    detail page."""
    if store is None:
        return ""
    return f"/app/superadmin/stores/{store.slug}"


def quiet_store_anomalies(db: Session, today: date) -> list[dict]:
    """Stores that USED to be active but have gone silent.

    Only flags stores on a paid plan or active trial — inactive /
    cancelled stores aren't anomalies.
    """
    from api.Modules.Transfers.Models import Transfer

    cutoff_active = today - timedelta(days=ANOMALY_QUIET_LOOKBACK_ACTIVE_DAYS)
    cutoff_quiet  = today - timedelta(days=ANOMALY_QUIET_LOOKBACK_QUIET_DAYS)
    rows = (
        db.query(
            Transfer.store_id,
            func.count(Transfer.id),
            func.max(Transfer.send_date),
        )
        .filter(Transfer.send_date >= cutoff_active)
        .group_by(Transfer.store_id)
        .all()
    )
    if not rows:
        return []
    store_ids = [r[0] for r in rows]
    stores = {
        s.id: s for s in
        db.query(Store).filter(Store.id.in_(store_ids)).all()
    }
    out: list[dict] = []
    for sid, count, last_date in rows:
        if int(count or 0) < ANOMALY_QUIET_MIN_PRIOR_TRANSFERS:
            continue
        if not last_date or last_date >= cutoff_quiet:
            continue
        store = stores.get(sid)
        if not store or not store.is_active:
            continue
        if store.plan == "inactive":
            continue
        days_silent = (today - last_date).days
        out.append({
            "kind":        "quiet_store",
            "severity":    "medium",
            "store":       store,
            "description": (
                f"{count} transfers in the last 30 days but "
                f"none in {days_silent} days — last on "
                f"{last_date.strftime('%b %d')}."
            ),
            "href":        _store_href(store),
        })
    return out


def big_over_short_anomalies(db: Session, today: date) -> list[dict]:
    """Daily reports in the last week with |over_short| over the
    threshold. Big variance = either a counting mistake or
    something worse; either way superadmin should know.
    """
    from api.Core.Money import to_cents
    from api.Modules.DailyBook.Models import DailyReport

    cutoff = today - timedelta(days=ANOMALY_OVERSHORT_LOOKBACK_DAYS)
    rows = (
        db.query(DailyReport)
          .filter(DailyReport.report_date >= cutoff)
          .filter(
              func.abs(DailyReport.over_short_cents)
              >= to_cents(ANOMALY_OVERSHORT_MEDIUM_THRESHOLD)
          )
          .order_by(func.abs(DailyReport.over_short_cents).desc())
          .limit(20)
          .all()
    )
    if not rows:
        return []
    store_ids = list({r.store_id for r in rows})
    stores = {
        s.id: s for s in
        db.query(Store).filter(Store.id.in_(store_ids)).all()
    }
    out: list[dict] = []
    for r in rows:
        store = stores.get(r.store_id)
        if not store or not store.is_active:
            continue
        magnitude = abs(r.over_short)
        severity = (
            "high"
            if magnitude >= ANOMALY_OVERSHORT_HIGH_THRESHOLD
            else "medium"
        )
        direction = "over" if r.over_short > 0 else "short"
        out.append({
            "kind":        "big_over_short",
            "severity":    severity,
            "store":       store,
            "description": (
                f"Daily book on {r.report_date.strftime('%b %d')}"
                f" closed ${magnitude:,.2f} {direction}."
            ),
            "href":        _store_href(store),
        })
    return out


def cancellation_spike_anomalies(
    db: Session, now: datetime,
) -> list[dict]:
    """Stores cancelled in the last ``ANOMALY_CANCELLATION_LOOKBACK_HOURS``
    window — surfaced together when the platform count crosses the
    spike threshold.

    Three cancellations in a single day is unusual for a small SaaS
    and warrants a personal reach-out per store. Below threshold
    this rule is silent (single cancellations are normal noise).
    Returns one anomaly row per store in the burst so each name
    shows up in the operator's feed.
    """
    cutoff = now - timedelta(hours=ANOMALY_CANCELLATION_LOOKBACK_HOURS)
    recent = (
        db.query(Store)
          .filter(Store.canceled_at.isnot(None))
          .filter(Store.canceled_at >= cutoff)
          .order_by(Store.canceled_at.desc())
          .limit(50)
          .all()
    )
    total = len(recent)
    if total < ANOMALY_CANCELLATION_SPIKE_THRESHOLD:
        return []
    out: list[dict] = []
    for s in recent:
        when = s.canceled_at.strftime("%b %d %H:%M UTC")
        out.append({
            "kind":        "cancellation_spike",
            "severity":    "high",
            "store":       s,
            "description": (
                f"Cancelled {when} — platform saw {total} "
                f"cancellations in the last "
                f"{ANOMALY_CANCELLATION_LOOKBACK_HOURS}h."
            ),
            "href":        _store_href(s),
        })
    return out


def password_reset_spike_anomalies(
    db: Session, now: datetime,
) -> list[dict]:
    """Users with an unusually large number of password-reset
    requests in the lookback window.

    Could be credential stuffing, an account-takeover attempt, a
    failing-email-deliverability issue, or a confused operator. The
    superadmin should see the username so they can investigate.
    Returns one anomaly row per affected user, attached to that
    user's store so the standard impersonation / drill links work.
    """
    from api.Modules.Auth.Models import PasswordResetToken
    from api.Modules.Tenancy.Models import User

    cutoff = now - timedelta(hours=ANOMALY_PASSWORD_RESET_LOOKBACK_HOURS)
    rows = (
        db.query(
            PasswordResetToken.user_id,
            func.count(PasswordResetToken.id),
        )
        .filter(PasswordResetToken.created_at >= cutoff)
        .group_by(PasswordResetToken.user_id)
        .having(
            func.count(PasswordResetToken.id)
            >= ANOMALY_PASSWORD_RESET_PER_USER_THRESHOLD
        )
        .all()
    )
    if not rows:
        return []
    user_ids = [r[0] for r in rows]
    users = {
        u.id: u for u in
        db.query(User).filter(User.id.in_(user_ids)).all()
    }
    store_ids = [u.store_id for u in users.values() if u.store_id]
    stores = (
        {
            s.id: s for s in
            db.query(Store).filter(Store.id.in_(store_ids)).all()
        }
        if store_ids else {}
    )
    out: list[dict] = []
    for uid, count in rows:
        user = users.get(uid)
        if user is None:
            continue
        store = stores.get(user.store_id) if user.store_id else None
        out.append({
            "kind":        "password_reset_spike",
            "severity":    "medium",
            "store":       store,
            "description": (
                f"User {user.username} requested {count} password "
                f"resets in the last "
                f"{ANOMALY_PASSWORD_RESET_LOOKBACK_HOURS}h."
            ),
            "href":        _store_href(store),
        })
    return out


def compute_platform_anomalies(db: Session) -> list[dict]:
    """Aggregate every anomaly rule into a single ranked list.

    Highest severity first; within a severity tier, source order
    is preserved (the detector returns most-recent-first inside
    each rule). Capped at 25 to keep the overview card scannable
    — if the queue runs over, the truncation is a signal in
    itself.
    """
    today = date.today()
    now = datetime.utcnow()
    anomalies: list[dict] = []
    anomalies.extend(cancellation_spike_anomalies(db, now))
    anomalies.extend(big_over_short_anomalies(db, today))
    anomalies.extend(quiet_store_anomalies(db, today))
    anomalies.extend(password_reset_spike_anomalies(db, now))
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    anomalies.sort(key=lambda a: severity_rank.get(a["severity"], 99))
    return anomalies[:_MAX_ANOMALIES_RETURNED]
