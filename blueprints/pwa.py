"""PWA chrome — service worker + offline page.

Extracted from ``app.py`` as part of the D2 Blueprint split (see
``blueprints/__init__.py``). No behavior change — these two routes
serve the same responses as before.

  /sw.js     The service worker JavaScript. Must be served from
             the site root so its default scope covers every path.
             We don't auth-gate it (anonymous visitors can register
             it from the landing page) and we cap its cache so a
             stale SW doesn't pin a stale UI.
  /offline   Plain offline page. Precached by the service worker
             so the browser still has something to render when the
             network is gone.
"""
from flask import Blueprint, render_template, send_from_directory


bp = Blueprint("pwa", __name__)


@bp.route("/sw.js")
def service_worker():
    resp = send_from_directory(
        "static", "sw.js", mimetype="application/javascript",
    )
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp


@bp.route("/offline")
def offline():
    return render_template("offline.html")
