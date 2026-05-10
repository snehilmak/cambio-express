"""Guard that the new content.css (dark+neon overrides for legacy
content-area classes) is linked on authenticated app pages so every
card/table/stat/badge picks up the new styling without per-template
edits."""






def test_transfers_page_redirects_to_spa(logged_in_client):
    """The legacy /transfers Jinja page is gone (PR #404); the SPA at
    /app/transfers loads its own bundle. Pinning the redirect
    contract is enough — the design system CSS is exercised in
    tests/test_brand_logo_static.py and the SPA bundle is built
    via Vite."""
    resp = logged_in_client.get("/transfers", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/transfers"


