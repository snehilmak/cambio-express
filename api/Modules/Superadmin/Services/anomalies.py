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

The detector is intentionally narrow today — quiet stores and big
over/short variances. New rules go here as `_anomaly_*` helpers
called from `compute_platform_anomalies` in priority order.
"""
from datetime import date, timedelta

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

# Cap the result list so the overview card stays scannable.
_MAX_ANOMALIES_RETURNED = 25


def _store_href(store) -> str:
    """Build the impersonation URL for a store. Falls back to ""
    when called outside a Flask request context (CLI / tests)."""
    if store is None:
        return ""
    try:
        from flask import url_for
        return url_for(
            "superadmin_extras.superadmin_impersonate",
            store_id=store.id,
        )
    except RuntimeError:
        # No active request context. Caller can post-process.
        return ""


def quiet_store_anomalies(db: Session, today: date) -> list[dict]:
    """Stores that USED to be active but have gone silent.

    Only flags stores on a paid plan or active trial — inactive /
    cancelled stores aren't anomalies.
    """
    # Models pulled lazily so the Service can be imported before
    # app.py finishes wiring up the Transfer model registry.
    from app import Transfer

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
    from app import DailyReport

    cutoff = today - timedelta(days=ANOMALY_OVERSHORT_LOOKBACK_DAYS)
    rows = (
        db.query(DailyReport)
          .filter(DailyReport.report_date >= cutoff)
          .filter(
              func.abs(DailyReport.over_short)
              >= ANOMALY_OVERSHORT_MEDIUM_THRESHOLD
          )
          .order_by(func.abs(DailyReport.over_short).desc())
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


def compute_platform_anomalies(db: Session) -> list[dict]:
    """Aggregate every anomaly rule into a single ranked list.

    Highest severity first; within a severity tier, source order
    is preserved (the detector returns most-recent-first inside
    each rule). Capped at 25 to keep the overview card scannable
    — if the queue runs over, the truncation is a signal in
    itself.
    """
    today = date.today()
    anomalies: list[dict] = []
    anomalies.extend(big_over_short_anomalies(db, today))
    anomalies.extend(quiet_store_anomalies(db, today))
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    anomalies.sort(key=lambda a: severity_rank.get(a["severity"], 99))
    return anomalies[:_MAX_ANOMALIES_RETURNED]
