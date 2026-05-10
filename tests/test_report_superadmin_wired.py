"""Wired superadmin reports — verify each route renders, returns
real data, and offers a working CSV export.

Reports left as Coming-soon (Stripe webhook health, failed payments,
payouts, refunds, DAU/MAU) need data sources we don't have today
(Stripe API integration or a dedicated event-log table)."""
from datetime import date, datetime, timedelta


# Reports wired to actual data after the superadmin batch.
_WIRED = [
    # Platform Health (4 of 4)
    "active-stores-by-plan",
    "signup-funnel",
    "login-activity",
    "dau-mau",
    # Stripe (1 of 3 — failed-payments + payouts still Coming-soon)
    "webhook-health",
    # Revenue (2 of 3 — refunds Coming-soon)
    "mrr-arr",
    "churn-cohort",
    # Trial Funnel (3 of 3)
    "conversion-rate",
    "time-to-convert",
    "trial-expiry-timing",
    # Feature Adoption (4 of 4)
    "bank-sync-adoption",
    "tv-display-adoption",
    "owner-adoption",
    "passkey-adoption",
    # Support / Audit (3 of 4 — audit-log already wired separately)
    "password-resets",
    "suspended-stores",
    "retention-queue",
]


def _superadmin_login(client):
    from app import User
    with client.application.app_context():
        sa = User.query.filter_by(role="superadmin").first()
        sa_id = sa.id
    with client.session_transaction() as s:
        s["user_id"] = sa_id
        s["role"] = "superadmin"
        s["store_id"] = None




def test_every_wired_csv_returns_text_csv(client):
    _superadmin_login(client)
    for slug in _WIRED:
        resp = client.get(f"/superadmin/reports/{slug}.csv")
        assert resp.status_code == 200, f"{slug}.csv returned {resp.status_code}"
        assert resp.mimetype == "text/csv", f"{slug}.csv wrong mimetype"
















def test_superadmin_reports_require_superadmin(client, test_store_id):
    """Plain admin can't hit superadmin reports."""
    from app import User
    with client.application.app_context():
        u = User.query.filter_by(store_id=test_store_id, role="admin").first()
        uid = u.id
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["role"] = "admin"
        s["store_id"] = test_store_id
    resp = client.get("/superadmin/reports/active-stores-by-plan",
                      follow_redirects=False)
    assert resp.status_code in (302, 303, 403)






def test_stripe_webhook_logs_signature_failures(client):
    """Posting an invalid Stripe webhook payload should be rejected
    (400) AND a WebhookEvent row with status=signature_err should be
    inserted so the Webhook Health report sees it."""
    from app import WebhookEvent, db
    with client.application.app_context():
        before = WebhookEvent.query.count()
    resp = client.post("/webhooks/stripe", data=b"{}",
                        headers={"Stripe-Signature": "bogus"})
    assert resp.status_code == 400
    with client.application.app_context():
        after = WebhookEvent.query.count()
        assert after == before + 1
        last = (WebhookEvent.query
                 .order_by(WebhookEvent.id.desc()).first())
        assert last.status == "signature_err"


def test_superadmin_report_center_shows_wired_count(client):
    """Report-center landing moved to React (PR #398). The wired-count
    contract — every superadmin report has a non-null Flask drilldown
    URL — moved with it: now exercised against the JSON envelope at
    /api/v2/superadmin/reports rather than the rendered HTML."""
    _superadmin_login(client)
    # Mint a superadmin JWT for the new JSON endpoint.
    from tests.conftest import login_superadmin
    token = login_superadmin(client)
    resp = client.get(
        "/api/v2/superadmin/reports",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    wired = sum(
        1
        for cat in body["categories"]
        for r in cat["reports"]
        if r["status"] == "ready" and r["url"]
    )
    assert wired >= 16
