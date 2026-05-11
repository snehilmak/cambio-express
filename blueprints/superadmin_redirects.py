"""Superadmin SPA-cutover redirects.

Extracted from ``app.py`` as part of the D2 Blueprint split. Two
small 301 redirects pointing at the platform-side React pages:

  GET /superadmin/reports            301 → /app/superadmin/reports
                                      (categorised report index)
  GET /superadmin/reports/audit-log  301 → /app/superadmin/audit-log
                                      (legacy URL kept alive — the
                                      SPA mounts the page at
                                      /app/superadmin/audit-log,
                                      no /reports/ prefix)

The per-drilldown superadmin BI reports (~20 routes under
``/superadmin/reports/<slug>``) still live in ``app.py`` because
they register from a large data-driven registry; this blueprint
only covers the standalone landing redirects.

Endpoint-name churn:
  url_for("superadmin_reports")
    → url_for("superadmin_redirects.superadmin_reports")
  url_for("superadmin_audit_log")
    → url_for("superadmin_redirects.superadmin_audit_log")
"""
from __future__ import annotations

from flask import Blueprint, redirect


bp = Blueprint("superadmin_redirects", __name__)


@bp.route("/superadmin/reports")
def superadmin_reports():
    """301 → /app/superadmin/reports. The SPA reads the categories
    envelope from /api/v2/superadmin/reports. Per-report drilldowns
    (`/superadmin/reports/<slug>`) still render legacy Flask
    templates; the SPA index links straight back into those URLs
    on click so navigation stays continuous during the cutover."""
    from app import superadmin_required
    return superadmin_required(
        lambda: redirect("/app/superadmin/reports", code=301)
    )()


@bp.route("/superadmin/reports/audit-log")
def superadmin_audit_log():
    """301 → /app/superadmin/audit-log. The React page reads the
    feed via /api/v2/superadmin/audit-log (paginated + filterable —
    wider than the legacy 100-row limit). Stub keeps
    url_for(...) working in still-Jinja chrome + bounces old
    bookmarks."""
    from app import superadmin_required
    return superadmin_required(
        lambda: redirect("/app/superadmin/audit-log", code=301)
    )()
