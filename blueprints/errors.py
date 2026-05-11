"""Flask error handlers — 404 + 500 pages.

Extracted from ``app.py`` as part of the D2 Blueprint split (see
``blueprints/__init__.py``). No behavior change — same templates,
same status codes, same logging.

Error handlers attach to the live ``Flask`` app via
``@app.errorhandler``, not to a Blueprint (Blueprint-scoped error
handlers only fire for requests that matched a route in that
Blueprint). The ``register(app)`` function below wires them up.

``current_user()`` and the two error templates still live in
``app.py``; we pass the helper in to avoid a circular import.
"""
from __future__ import annotations

import traceback
from typing import Callable

from flask import Flask, render_template, request


def register(app: Flask, current_user: Callable):
    """Attach 404 + 500 error handlers to the given Flask app.

    ``current_user`` is the request-scoped user accessor from
    ``app.py``. Passing it in keeps this module independent of the
    monolith so it can move into ``api/`` later without rewriting.
    """

    def _render_error(code: int, message: str, user):
        # Logged-out visitors get the standalone error_public.html
        # — no sidebar/topbar so a typo like /APP doesn't render the
        # admin chrome and look like a half-loaded dashboard.
        # Logged-in visitors keep the in-app error.html with their
        # normal shell (so the "Back to Dashboard" button routes
        # correctly).
        if user is None:
            return render_template(
                "error_public.html",
                code=code, message=message,
                request_path=request.path,
            ), code
        return render_template(
            "error.html", user=user, code=code, message=message,
        ), code

    @app.errorhandler(404)
    def not_found(_e):
        return _render_error(404, "Page not found.", current_user())

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
