"""Miscellaneous legacy → SPA redirects.

Extracted from ``app.py`` as part of the D2 Blueprint split. Three
simple 301 redirects that don't fit any of the topic-specific
blueprints:

  GET /dashboard       301 → /app/dashboard (or /app/owner/dashboard
                         when the session role is owner). `login_required`
                         preserves two contracts the legacy view relied
                         on: anonymous → /login and expired-trial admins
                         → /subscribe.
  GET /reports         301 → /app/reports (admin Report Center)
  GET /owner/reports   301 → /app/owner/reports (owner Report Center)

The per-drilldown report routes still live in app.py because they
register from a large data-driven registry; this blueprint only
handles the categorised landing pages.

Endpoint-name churn:
  url_for("dashboard")     → url_for("spa_redirects.dashboard")
  url_for("reports")       → url_for("spa_redirects.reports")
  url_for("owner_reports") → url_for("spa_redirects.owner_reports")
"""
from __future__ import annotations

from flask import Blueprint, redirect, session


bp = Blueprint("spa_redirects", __name__)


@bp.route("/dashboard")
def dashboard():
    """Legacy /dashboard 301s to the SPA. The SPA's /app/dashboard
    fetches /api/v2/dashboard/summary, which returns a role-shaped
    payload (admin / employee / superadmin). Owner sessions land at
    /app/owner/dashboard.

    `login_required` preserves two contracts the legacy view relied
    on: anonymous → /login and expired-trial admins → /subscribe.
    Without it, expired stores would skip past the paywall by
    following the bare 301 to the SPA."""
    from app import login_required

    @login_required
    def _h():
        if session.get("role") == "owner":
            return redirect("/app/owner/dashboard", code=301)
        return redirect("/app/dashboard", code=301)

    return _h()


@bp.route("/reports")
def reports():
    """Legacy /reports → 301 to /app/reports (categorized
    accordion). The SPA fetches the categories from
    /api/v2/reports; per-report drilldowns still hit Flask
    templates by their dedicated routes."""
    return redirect("/app/reports", code=301)


@bp.route("/owner/reports")
def owner_reports():
    """Legacy /owner/reports → 301 to /app/owner/reports. Same
    categorized accordion, different drilldown routing (every
    `report_<x>` admin endpoint has an `owner_report_<x>` mirror
    that filters to every store under the owner umbrella)."""
    return redirect("/app/owner/reports", code=301)
