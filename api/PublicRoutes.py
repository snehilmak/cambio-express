"""Starlette app for root-mounted public routes.

Replaces the five Flask ``blueprints/`` files that handled the
non-``/app`` and non-``/api/v2`` surface:

* ``GET /``                          PWA-aware bounce to /app/login/<slug>
                                     or /app/
* ``GET /privacy``                   301 → /app/privacy
* ``GET /sw.js``                     Service worker
* ``GET /offline``                   Offline page
* ``GET /tv/logo/<type>/<slug>``     Catalog logo BLOB
* ``GET /tv/<token>``                Public TV rate board (shared)
* ``GET /tv/device/<dt>``            Per-device TV rate board
* ``POST /api/tv-pair/init``         Mint a pair-code
* ``GET  /api/tv-pair/status``       Poll a pair-code

Mounted via ``asgi.py``. Production routing now dispatches these
exact paths to this Starlette app instead of Flask. Tests reach
the same routes through ``asgi:asgi_app`` (the
``httpx.ASGITransport`` client) — no Flask test-client needed.
"""
from __future__ import annotations

import os

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import (
    FileResponse, JSONResponse, RedirectResponse, Response,
)
from starlette.routing import Route
from starlette.templating import Jinja2Templates

from api.Core.Database import SessionLocal
from api.Core.Clock import utc_now


_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.normpath(os.path.join(_HERE, ".."))
_TEMPLATES_DIR = os.path.join(_REPO_ROOT, "templates")
_STATIC_DIR = os.path.join(_REPO_ROOT, "static")


# Templates are the same Jinja files Flask was rendering. The two
# ``url_for('static', filename=X)`` calls in ``offline.html`` and
# ``tv_display_public.html`` need a stand-in here — we register a
# small global that mirrors the Flask helper for the static
# endpoint (the only ``url_for`` use in those templates).
_templates = Jinja2Templates(directory=_TEMPLATES_DIR)


def _url_for_shim(endpoint: str, **values) -> str:
    """Jinja ``url_for`` stand-in for the public templates.

    Flask's ``url_for('static', filename='X')`` returns
    ``/static/X``. The TV-display + offline templates use this
    only for static assets (favicon, CSS); no other endpoints are
    referenced from these templates, so this shim's surface is
    deliberately tiny."""
    if endpoint == "static":
        filename = values.get("filename", "")
        return f"/static/{filename}" if filename else "/static/"
    raise NotImplementedError(
        f"url_for({endpoint!r}) is not supported in the public template "
        f"renderer. Hardcode the URL or extend _url_for_shim.")


# Starlette's ``Jinja2Templates`` injects its own ``url_for`` that
# resolves against Starlette's routing table. Public templates use
# ``url_for('static', filename=…)`` which is a Flask-ism; the
# Starlette-side lookup raises ``NoMatchFound``. Override with our
# shim (direct assignment, not setdefault, so we win over the
# framework injection).
_templates.env.globals["url_for"] = _url_for_shim
# ``STATIC_VERSION`` is used by templates to cache-bust static
# assets. The Flask context processor populates it; we mirror the
# behaviour with a stable per-process value (the request-time value
# isn't load-bearing — it changes per-deploy, not per-request).
_templates.env.globals["STATIC_VERSION"] = os.environ.get("STATIC_VERSION", "1")
# The TV-display template renders country flags via the
# ``country_flag_html`` Jinja helper that Flask registers on its
# global env. Mirror that on the public-routes env so the same
# template works under both renderers.
from api.Templating import country_flag_html as _country_flag_html  # noqa: E402

_templates.env.globals["country_flag_html"] = _country_flag_html


# Long-lived cookie persisting the last store-slug an employee
# signed in to so the PWA shortcut at "/" knows where to bounce.
LAST_STORE_SLUG_COOKIE = "ds_last_store"


# ── Landing routes ───────────────────────────────────────────────


async def landing(request: Request) -> Response:
    """301 → /app/. PWA preservation: when an installed-PWA
    employee opens their shortcut (which points at /), we honor
    the ``ds_last_store`` cookie and bounce straight to
    /app/login/<slug>."""
    from api.Modules.Tenancy.Models import Store

    slug = request.cookies.get(LAST_STORE_SLUG_COOKIE)
    if slug:
        with SessionLocal() as s:
            store = s.query(Store).filter_by(slug=slug).first()
            if store and store.is_active:
                return RedirectResponse(
                    f"/app/login/{store.slug}", status_code=302,
                )
    return RedirectResponse("/app/", status_code=301)


async def privacy(request: Request) -> Response:
    """301 → /app/privacy. The SPA owns the public privacy
    policy now."""
    return RedirectResponse("/app/privacy", status_code=301)


# ── PWA chrome ────────────────────────────────────────────────────


async def service_worker(request: Request) -> Response:
    """Serve ``static/sw.js`` with PWA-friendly headers.

    Service worker must live at the site root so its default scope
    covers every path; ``Service-Worker-Allowed`` declares the same.
    """
    return FileResponse(
        os.path.join(_STATIC_DIR, "sw.js"),
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache",
            "Service-Worker-Allowed": "/",
        },
    )


async def offline(request: Request) -> Response:
    """The plain offline page the service worker pre-caches."""
    return _templates.TemplateResponse(
        request=request, name="offline.html",
    )


# ── TV logo serve ─────────────────────────────────────────────────


_LOGO_ALLOWED_MIMES = {
    "image/png", "image/jpeg", "image/webp", "image/svg+xml",
}


async def tv_catalog_logo(request: Request) -> Response:
    """Stream the BLOB for a catalog logo. Year-long immutable
    cache; templates cache-bust by appending ``?v=<unix>``."""
    catalog_type = request.path_params["catalog_type"]
    slug = request.path_params["slug"]
    if catalog_type not in ("company", "bank"):
        return Response(status_code=404)
    from api.Modules.TVDisplay.Models import TVCatalogLogo
    with SessionLocal() as s:
        row = (s.query(TVCatalogLogo)
                .filter_by(catalog_type=catalog_type, slug=slug)
                .first())
        if not row or row.mime_type not in _LOGO_ALLOWED_MIMES:
            return Response(status_code=404)
        blob = row.blob
        mime = row.mime_type
    return Response(
        content=blob,
        media_type=mime,
        headers={
            "Content-Length": str(len(blob)),
            # Year-long immutable cache. Templates append ?v=<unix>
            # so a re-upload changes the URL → fresh fetch on next
            # render.
            "Cache-Control": "public, max-age=31536000, immutable",
            # Block image-format sniffing — the served bytes match
            # the whitelisted mime exactly.
            "X-Content-Type-Options": "nosniff",
        },
    )


# ── TV rate board (public) ────────────────────────────────────────


async def tv_public_display(request: Request) -> Response:
    """Fullscreen rate board, no auth. Anyone with the URL sees it."""
    token = request.path_params["token"]
    from api.Modules.Billing.Services import store_has_addon
    from api.Modules.Tenancy.Models import Store
    from api.Modules.TVDisplay.Models import TVDisplay
    from api.Modules.TVDisplay.Services import build_tv_board_context

    with SessionLocal() as s:
        display = (s.query(TVDisplay)
                    .filter_by(public_token=token).first())
        if display is None:
            return Response(status_code=404)
        store = s.get(Store, display.store_id)
        if not store or not store_has_addon(store, "tv_display"):
            return Response(status_code=404)
        ctx = build_tv_board_context(display, store, s)
        # TemplateResponse renders inside the with-block so the
        # ORM rows in ``ctx`` are still session-bound when Jinja
        # accesses their attributes.
        return _templates.TemplateResponse(
            request=request, name="tv_display_public.html", context=ctx,
        )


async def tv_device_display(request: Request) -> Response:
    """Per-device rate-board URL handed to a Fire TV companion app
    after a successful pair-code redeem. Bumps
    ``TVPairing.last_seen_at`` on render."""
    device_token = request.path_params["device_token"]
    from api.Modules.Billing.Services import store_has_addon
    from api.Modules.Tenancy.Models import Store
    from api.Modules.TVDisplay.Models import TVDisplay, TVPairing
    from api.Modules.TVDisplay.Services import build_tv_board_context

    with SessionLocal() as s:
        pairing = (s.query(TVPairing)
                    .filter_by(device_token=device_token).first())
        if not pairing or pairing.revoked_at is not None:
            return Response(status_code=404)
        display = s.get(TVDisplay, pairing.display_id)
        if not display:
            return Response(status_code=404)
        store = s.get(Store, display.store_id)
        if not store or not store_has_addon(store, "tv_display"):
            return Response(status_code=404)
        pairing.last_seen_at = utc_now()
        s.commit()
        ctx = build_tv_board_context(display, store, s)
        return _templates.TemplateResponse(
            request=request, name="tv_display_public.html", context=ctx,
        )


# ── Pair-code JSON API ────────────────────────────────────────────


async def tv_pair_init(request: Request) -> JSONResponse:
    """The Fire TV app calls this on launch. Creates a
    ``TVPendingPair`` with a fresh code + device_token and returns
    both."""
    from api.Modules.TVDisplay.Models import TVPendingPair
    from api.Modules.TVDisplay.Services.pair_code import (
        PAIR_CODE_LIFETIME, generate_device_token, generate_pair_code,
    )

    payload: dict = {}
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}
    device_label = (payload.get("device_label") or "").strip()[:80]
    now = utc_now()

    with SessionLocal() as s:
        # Loop on code collision (rare with a 387M space, free to retry).
        code = None
        for _ in range(8):
            code = generate_pair_code()
            if not s.query(TVPendingPair).filter_by(code=code).first():
                break

        pending = TVPendingPair(
            code=code,
            device_token=generate_device_token(s),
            device_label=device_label,
            created_at=now,
            expires_at=now + PAIR_CODE_LIFETIME,
        )
        s.add(pending)
        s.commit()
        body = {
            "code":         pending.code,
            "device_token": pending.device_token,
            "expires_at":   pending.expires_at.isoformat() + "Z",
            "ttl_seconds":  int(PAIR_CODE_LIFETIME.total_seconds()),
        }
    return JSONResponse(body)


async def tv_pair_status(request: Request) -> JSONResponse:
    """The Fire TV polls this with its device_token. Always 200 so
    the Fire TV can branch off the JSON. Unknown tokens get
    treated as "expired" so a fresh /init is the recovery path."""
    from api.Modules.Billing.Services import store_has_addon
    from api.Modules.Tenancy.Models import Store
    from api.Modules.TVDisplay.Models import TVDisplay, TVPairing, TVPendingPair

    token = (request.query_params.get("token") or "").strip()
    if not token:
        return JSONResponse({"status": "expired"})

    with SessionLocal() as s:
        # Already claimed?
        pairing = (s.query(TVPairing)
                    .filter_by(device_token=token, revoked_at=None)
                    .first())
        if pairing is not None:
            display = s.get(TVDisplay, pairing.display_id)
            store = s.get(Store, display.store_id) if display else None
            if display and store and store_has_addon(store, "tv_display"):
                # The per-device rate-board URL the Fire TV will load.
                # The Flask helper used ``url_for("tv_board.tv_device_display",
                # _external=True)``; we build the same URL with the
                # request's scheme + host. The path is stable.
                base = f"{request.url.scheme}://{request.url.netloc}"
                display_url = f"{base}/tv/device/{token}"
                title = display.title or "Money Transfer Rates"
                store_name = store.name
                return JSONResponse({
                    "status":      "claimed",
                    "display_url": display_url,
                    "store_name":  store_name,
                    "title":       title,
                })
            # Pairing exists but addon is gone — same as expired.
            return JSONResponse({"status": "expired"})

        pending = (s.query(TVPendingPair)
                    .filter_by(device_token=token).first())
        if not pending:
            return JSONResponse({"status": "expired"})
        if pending.expires_at < utc_now():
            return JSONResponse({"status": "expired"})
        if pending.claimed_at is not None:
            # Pending row was claimed but the resulting TVPairing
            # was already revoked, or the addon was yanked. Re-init.
            return JSONResponse({"status": "expired"})
        # Still pending. Return the code so the Fire TV can
        # re-display it after a process death / config change.
        ttl = int((pending.expires_at - utc_now()).total_seconds())
        return JSONResponse({
            "status":      "pending",
            "code":        pending.code,
            "ttl_seconds": max(0, ttl),
        })


# ── App assembly ──────────────────────────────────────────────────


public_app = Starlette(routes=[
    Route("/", landing, methods=["GET"]),
    Route("/privacy", privacy, methods=["GET"]),
    Route("/sw.js", service_worker, methods=["GET"]),
    Route("/offline", offline, methods=["GET"]),
    Route("/tv/logo/{catalog_type}/{slug}", tv_catalog_logo, methods=["GET"]),
    Route("/tv/device/{device_token}", tv_device_display, methods=["GET"]),
    Route("/tv/{token}", tv_public_display, methods=["GET"]),
    Route("/api/tv-pair/init", tv_pair_init, methods=["POST"]),
    Route("/api/tv-pair/status", tv_pair_status, methods=["GET"]),
])


# Paths the dispatcher should route here instead of Flask. Kept as
# a list (not a regex) so adding routes only requires touching one
# place. Order matters for nothing — ``asgi.py`` checks
# membership.
PUBLIC_ROUTE_PATHS = {
    "/", "/privacy", "/sw.js", "/offline",
    "/api/tv-pair/init", "/api/tv-pair/status",
}
PUBLIC_ROUTE_PREFIXES = ("/tv/",)
