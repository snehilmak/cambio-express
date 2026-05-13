"""HTTP integration tests for /api/v2/superadmin/reports.

The report-center index moved to React in PR #398. This endpoint
returns the same categories envelope the legacy Jinja partial
(`_report_center.html`) consumed — categories with reports, each
report carrying a Flask drilldown URL until the per-report pages
migrate too.

Auth: superadmin only. Anything else gets 403.
"""


def _login_admin(client, store_id):
    resp = client.post(
        "/api/v2/auth/login",
        json={"username": "admin@test.com",
              "password": "testpass123!",
              "store_id": store_id},
    )
    return resp.get_json()["access_token"]


def _login_superadmin(client):
    from tests.conftest import login_superadmin
    return login_superadmin(client)


# ── Auth gating ─────────────────────────────────────────────


def test_reports_requires_jwt(client):
    resp = client.get("/api/v2/superadmin/reports")
    assert resp.status_code == 401


def test_reports_403_for_admin(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.get(
        "/api/v2/superadmin/reports",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── Envelope shape ──────────────────────────────────────────


def test_reports_returns_six_categories(client):
    token = _login_superadmin(client)
    resp = client.get(
        "/api/v2/superadmin/reports",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "categories" in body
    keys = [c["key"] for c in body["categories"]]
    # Order matters — the SPA renders top-down, so platform-health
    # must come first.
    assert keys == [
        "platform_health", "revenue", "stripe", "trial",
        "feature_adoption", "support",
    ]


def test_each_category_has_label_icon_reports(client):
    """Every category must carry a label, an inline-SVG icon, and a
    non-empty list of reports — otherwise the SPA would render a
    blank accordion."""
    token = _login_superadmin(client)
    body = client.get(
        "/api/v2/superadmin/reports",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    for cat in body["categories"]:
        assert isinstance(cat["label"], str) and cat["label"]
        assert "<svg" in cat["icon"]
        assert isinstance(cat["reports"], list)
        assert len(cat["reports"]) > 0


def test_every_report_has_url_and_status_ready(client):
    """Every superadmin report has been wired to its Flask drilldown,
    so `url` is non-null + `status` is `ready`. Coming-soon rows
    would surface here as `status='coming_soon'` + `url=None`; the
    test pins the current state."""
    token = _login_superadmin(client)
    body = client.get(
        "/api/v2/superadmin/reports",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    for cat in body["categories"]:
        for r in cat["reports"]:
            assert r["status"] == "ready", \
                f"{cat['key']}/{r['key']} unexpectedly coming_soon"
            assert r["url"] is not None, \
                f"{cat['key']}/{r['key']} has no drilldown URL"
            # Drilldowns live under either the legacy /superadmin/
            # Jinja routes or the SPA's /app/superadmin/ — both are
            # valid destinations for a report card.
            assert (
                r["url"].startswith("/superadmin/")
                or r["url"].startswith("/app/superadmin/")
            ), f"{cat['key']}/{r['key']} url={r['url']!r}"


def test_reports_includes_audit_log_card(client):
    """The Support / Audit category must include a card pointing at
    the audit log — that's the most-used drilldown and a regression
    here would silently drop it from the index."""
    token = _login_superadmin(client)
    body = client.get(
        "/api/v2/superadmin/reports",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    support = next(c for c in body["categories"] if c["key"] == "support")
    audit = next(r for r in support["reports"] if r["key"] == "audit_log")
    assert audit["label"] == "Superadmin Audit Log"
    # The audit-log GET itself 301s to /app/superadmin/audit-log; the
    # *legacy* report-center URL still points at the Flask-side
    # endpoint name, which is fine — the bounce happens transparently.
    assert audit["url"]
