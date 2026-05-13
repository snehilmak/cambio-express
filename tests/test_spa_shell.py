"""SPA-1 — the Starlette ``spa_app`` serves the React/Vite SPA at /app/*.

Pins the contract that lets the SPA coexist with the legacy Jinja
site during the migration:

  • /app/                 → 200, serves index.html
  • /app                  → 200, serves index.html (same as /app/ —
                            the trailing slash isn't load-bearing
                            because React Router's basename matches
                            either form)
  • /app/<any-path>       → 200, serves index.html (SPA fallback so
                            React Router can handle client-side
                            routes after a hard refresh)
  • /app/assets/<file>    → 200 with immutable cache header
  • /                     → 301 to /app/ (regression guard so the
                            SPA mount doesn't accidentally shadow
                            the legacy root redirect)

When `frontend/dist/index.html` doesn't exist (i.e. the SPA wasn't
built), `/app/` returns a 503 with a helpful message. We test
that branch explicitly so the deploy-misconfiguration story stays
clear.
"""
import os
import shutil
from pathlib import Path

import pytest


REPO_ROOT  = Path(__file__).resolve().parent.parent
SPA_DIR    = REPO_ROOT / "frontend" / "dist"
SPA_INDEX  = SPA_DIR / "index.html"
SPA_ASSETS = SPA_DIR / "assets"


def _spa_built() -> bool:
    return SPA_INDEX.exists()


# Ensure a deterministic shell-bundle exists for the routes that
# depend on it. We don't run the real Vite build inside the test —
# slow, and CI doesn't have Node guaranteed yet. Instead the test
# fixture writes a stub index.html + asset, and tears them down
# only if it created them.


@pytest.fixture
def stub_spa_build():
    """Write a stub frontend/dist build for tests that need it.
    No-op if a real build is already present (so the test can run
    after a real `npm run build` without clobbering the artifact)."""
    created_index = False
    created_assets_dir = False
    created_asset_file = False
    if not SPA_INDEX.exists():
        SPA_DIR.mkdir(parents=True, exist_ok=True)
        SPA_INDEX.write_text(
            '<!doctype html><html data-theme="dark">'
            '<head><title>DineroBook</title></head>'
            '<body><div id="root"></div>'
            '<script type="module" src="/app/assets/index.js"></script>'
            '</body></html>'
        )
        created_index = True
    if not SPA_ASSETS.exists():
        SPA_ASSETS.mkdir(parents=True, exist_ok=True)
        created_assets_dir = True
    asset_file = SPA_ASSETS / "index.js"
    if not asset_file.exists():
        asset_file.write_text("// stub asset for tests\nconsole.log('ok');\n")
        created_asset_file = True
    yield
    # Only clean up files we actually created — never delete a real
    # `npm run build` artifact left by a developer.
    if created_asset_file:
        asset_file.unlink(missing_ok=True)
    if created_assets_dir and SPA_ASSETS.exists() and not any(SPA_ASSETS.iterdir()):
        shutil.rmtree(SPA_ASSETS, ignore_errors=True)
    if created_index:
        SPA_INDEX.unlink(missing_ok=True)
        # Drop the dist dir if we created it AND it ends up empty.
        if SPA_DIR.exists() and not any(SPA_DIR.iterdir()):
            shutil.rmtree(SPA_DIR, ignore_errors=True)


def test_spa_shell_serves_index_html(client, stub_spa_build):
    r = client.get("/app/")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert '<div id="root">' in body, (
        "SPA shell must include the React root mount point; "
        f"got body starting with: {body[:200]!r}"
    )
    assert r.headers.get("Content-Type", "").startswith("text/html")
    # No-store on the shell is mandatory — Vite content-hashes asset
    # filenames, so the only way the browser sees a new build is if
    # it always re-fetches index.html.
    assert "no-store" in r.headers.get("Cache-Control", ""), (
        f"Cache-Control should disable caching on the shell; got "
        f"{r.headers.get('Cache-Control')!r}"
    )


def test_spa_shell_fallback_for_client_routes(client, stub_spa_build):
    """An arbitrary client-side route must serve the same shell so
    React Router can handle it after a hard refresh."""
    r = client.get("/app/transfers/123/edit")
    assert r.status_code == 200
    assert '<div id="root">' in r.get_data(as_text=True)


def test_spa_shell_no_slash_serves_index(client, stub_spa_build):
    """Bare /app (no trailing slash) must serve the same SPA shell
    as /app/. The historical 301 redirect was a Flask-era artifact;
    under Starlette ``spa_app`` both URLs resolve to index.html and
    React Router's basename (``/app``) matches either form."""
    r = client.get("/app", follow_redirects=False)
    assert r.status_code == 200
    assert '<div id="root">' in r.get_data(as_text=True)


def test_spa_asset_served_with_immutable_cache(client, stub_spa_build):
    r = client.get("/app/assets/index.js")
    assert r.status_code == 200
    cc = r.headers.get("Cache-Control", "")
    # Vite content-hashes asset filenames so a 1-year immutable
    # cache is safe — a new build emits a new filename.
    assert "max-age=31536000" in cc and "immutable" in cc, (
        f"Cache-Control must be immutable + 1y; got {cc!r}"
    )


def test_spa_asset_404_for_missing_file(client, stub_spa_build):
    r = client.get("/app/assets/does-not-exist.js")
    assert r.status_code == 404


def test_legacy_root_redirects_to_app(client):
    """Regression guard: mounting the SPA at /app must not affect
    the legacy `/` route — which is now a 301 to /app/. The Jinja
    landing template was retired alongside this redirect; what
    matters here is that / still resolves (not 404, which would
    indicate the SPA mount accidentally shadowed it)."""
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (301, 302), (
        f"GET / should redirect; got {r.status_code}"
    )
    assert r.headers["Location"].startswith("/app"), (
        f"GET / should redirect to /app/...; got {r.headers['Location']!r}"
    )


def test_missing_spa_build_returns_503(client, monkeypatch):
    """If `frontend/dist/index.html` doesn't exist, /app/ returns a
    503 with a clear "build the SPA" message — surfaces the
    deploy-misconfiguration story instead of a confusing 404."""
    from api import spa as spa_module
    bogus_index = "/tmp/_dinerobook_spa_index_that_does_not_exist.html"
    if os.path.exists(bogus_index):
        os.remove(bogus_index)
    monkeypatch.setattr(spa_module, "_SPA_INDEX", bogus_index)
    r = client.get("/app/")
    assert r.status_code == 503
    body = r.get_data(as_text=True)
    assert "SPA bundle missing" in body
