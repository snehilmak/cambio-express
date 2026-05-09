"""Tests for the legacy /privacy Flask route.

The privacy policy page was retired in favour of the React SPA route
at /app/privacy. The Flask stub that remains is a 301 redirect so:

  - Stripe's saved privacy URL (Financial Connections + Checkout
    both link here from their hosted screens) keeps working.
  - Old bookmarks and incoming links don't 404.
  - `url_for('privacy')` from any still-Jinja template resolves.

The body of the policy is now rendered by frontend/src/routes/Privacy.tsx;
visual regressions belong with the SPA, not here.
"""


def test_privacy_redirects_to_spa(client):
    resp = client.get("/privacy", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/privacy"


def test_privacy_redirect_works_with_cutover_off(client, monkeypatch):
    """Even if the SPA cutover redirect layer is disabled (emergency
    rollback flag), the /privacy route's own 301 must still fire —
    Stripe's hosted screens link directly at this URL and we cannot
    revert that link without a Stripe-side change."""
    import app as app_module

    monkeypatch.setattr(app_module, "SPA_CUTOVER_ENABLED", False)
    resp = client.get("/privacy", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/privacy"
