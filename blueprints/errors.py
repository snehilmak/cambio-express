"""Flask error handlers — 404 + 500.

Returns a minimal plain-HTML page (no Jinja chrome — the legacy
chrome templates were retired with the Jinja UI). The SPA owns
in-app errors via its own React error boundary; this is only the
fallback for stray Flask requests (webhooks, /static, etc.) that
404 or 500 outside the SPA.

Logged-in visitors get a "← Open the app" link to /app/dashboard;
anyone else gets a link to /app/.

Error handlers attach to the live ``Flask`` app via
``@app.errorhandler``, not to a Blueprint (Blueprint-scoped error
handlers only fire for requests that matched a route in that
Blueprint). The ``register(app)`` function below wires them up.
"""
from __future__ import annotations

import traceback
from typing import Callable

from flask import Flask, request


_ERROR_PAGE = """<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8" />
<title>{code} · DineroBook</title>
<meta name="viewport" content="width=device-width,initial-scale=1" />
<style>
  body {{ background: #0a0a0a; color: #f5f5f5; font-family: 'Inter', system-ui, sans-serif; margin: 0; padding: 0; min-height: 100vh; display: grid; place-items: center; }}
  .card {{ max-width: 32rem; padding: 2.5rem 2rem; text-align: center; }}
  h1 {{ font-family: 'Space Grotesk', sans-serif; font-size: 3rem; margin: 0 0 0.5rem; color: #3fff00; letter-spacing: -0.02em; }}
  p  {{ color: #a3a3a3; margin: 0 0 1.5rem; line-height: 1.55; }}
  code {{ font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; color: #d4d4d4; }}
  a  {{ color: #3fff00; text-decoration: none; font-weight: 600; }}
  a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
  <div class="card">
    <h1>{code}</h1>
    <p>{message}</p>
    <p><code>{path}</code></p>
    <p><a href="{back_url}">{back_label} →</a></p>
  </div>
</body>
</html>
"""


def register(app: Flask, current_user: Callable):
    """Attach 404 + 500 error handlers to the given Flask app.

    ``current_user`` is the request-scoped user accessor from
    ``app.py``; if it ever returns a non-None value (i.e. the
    legacy cookie session is still in play during the auth
    retirement window), we point them back at /app/dashboard.
    Anyone else lands on /app/.
    """

    def _render_error(code: int, message: str, user):
        try:
            authed = user is not None
        except Exception:
            authed = False
        back_url = "/app/dashboard" if authed else "/app/"
        back_label = "Open the dashboard" if authed else "Open the app"
        body = _ERROR_PAGE.format(
            code=code,
            message=message,
            path=request.path,
            back_url=back_url,
            back_label=back_label,
        )
        return body, code, {"Content-Type": "text/html; charset=utf-8"}

    @app.errorhandler(404)
    def not_found(_e):
        try:
            u = current_user()
        except Exception:
            u = None
        return _render_error(404, "Page not found.", u)

    @app.errorhandler(500)
    def server_error(e):
        app.logger.error(f"500 error: {e}\n{traceback.format_exc()}")
        try:
            u = current_user()
        except Exception:
            u = None
        return _render_error(
            500, "Something went wrong. Please try again.", u,
        )
