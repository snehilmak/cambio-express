"""Admin settings hub SPA migration contract.

The /admin/settings GET 301s to /app/settings (Settings.tsx
covers store-info + team + change-password + passkeys + the
billing-portal redirect). The POST handler stays live for the
legacy multi-tab form-submit paths (`_tab=store|companies`)
plus the sub-routes (/admin/settings/roster/*, /team/<uid>,
/owner/redeem). Companies-tab + owner-access-tab UI haven't
been ported to Settings.tsx yet — those mutation endpoints
remain reachable for direct callers.
"""


def test_admin_settings_get_redirects_to_spa(logged_in_client):
    resp = logged_in_client.get("/admin/settings", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/settings"


def test_admin_settings_security_tab_still_redirects_to_account_security(
    logged_in_client,
):
    """The Security tab graduated to /account/security long ago
    (per-user page reachable from every role). The ?tab=security
    bookmark still 301s straight to /account/security to avoid
    bouncing through /app/settings."""
    resp = logged_in_client.get(
        "/admin/settings?tab=security", follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/account/security")


def test_admin_settings_post_store_info_still_mutates(logged_in_client):
    """The legacy form-POST mutation surface stays live so
    /admin/settings/team/<uid> + roster/* + owner/redeem still
    work for the few features Settings.tsx hasn't ported yet."""
    from app import Store, db, app as flask_app
    resp = logged_in_client.post("/admin/settings", data={
        "_tab": "store",
        "store_name": "Round-Trip Store",
        "email": "rt@test.com",
        "phone": "555-0001",
    }, follow_redirects=False)
    # Success → 302 to /admin/settings?tab=store (which itself 301s).
    assert resp.status_code in (302, 303)
    with flask_app.app_context():
        s = Store.query.filter_by(slug="test-store").first()
        assert s.name == "Round-Trip Store"
        assert s.email == "rt@test.com"
