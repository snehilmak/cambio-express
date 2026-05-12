"""Superadmin SPA-cutover redirects.

Extracted from ``app.py`` as part of the D2 Blueprint split. Five
small 301 redirects pointing at the platform-side React pages:

  GET /superadmin/reports            301 → /app/superadmin/reports
                                      (categorised report index)
  GET /superadmin/reports/audit-log  301 → /app/superadmin/audit-log
                                      (legacy URL kept alive — the
                                      SPA mounts the page at
                                      /app/superadmin/audit-log,
                                      no /reports/ prefix)
  GET /superadmin/stores             301 → /app/superadmin/stores
  GET/POST /superadmin/stores/new    301 → /app/superadmin/stores/new
  GET /superadmin/controls           301 → /app/superadmin/controls
                                      (preserves ?tab=; ?tab=audit
                                      bounces to the audit-log
                                      redirect above)

The per-drilldown superadmin BI reports (~20 routes under
``/superadmin/reports/<slug>``) and every mutating POST under
``/superadmin/*`` still live in ``app.py``; this blueprint only
covers the standalone GET-redirect surface.

Endpoint-name churn:
  url_for("superadmin_reports")
    → url_for("superadmin_redirects.superadmin_reports")
  url_for("superadmin_audit_log")
    → url_for("superadmin_redirects.superadmin_audit_log")
  url_for("superadmin_stores")
    → url_for("superadmin_redirects.superadmin_stores")
  url_for("superadmin_new_store")
    → url_for("superadmin_redirects.superadmin_new_store")
  url_for("superadmin_controls")
    → url_for("superadmin_redirects.superadmin_controls")
"""
from __future__ import annotations

from flask import Blueprint, redirect, request, url_for


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


@bp.route("/superadmin/stores")
def superadmin_stores():
    """301 → /app/superadmin/stores. SPA reads
    /api/v2/superadmin/stores (paginated, filterable). The
    /superadmin/stores/new + per-store mutate routes stay alive in
    app.py."""
    from app import superadmin_required
    return superadmin_required(
        lambda: redirect("/app/superadmin/stores", code=301)
    )()


@bp.route("/superadmin/stores/new", methods=["GET", "POST"])
def superadmin_new_store():
    """301 → /app/superadmin/stores/new. The React form POSTs to
    /api/v2/superadmin/stores which mirrors the legacy field set +
    records the same `create_store` audit entry."""
    from app import superadmin_required
    return superadmin_required(
        lambda: redirect("/app/superadmin/stores/new", code=301)
    )()


@bp.route("/superadmin/controls")
def superadmin_controls():
    """301 → /app/superadmin/controls. The platform-controls hub
    moved to React; the SPA reads /api/v2/dashboard/summary,
    /api/v2/superadmin/{stores,discounts,reports}, and
    /api/v2/feature-flags. The legacy ``?tab=audit`` query still
    bounces to /superadmin/audit-log so old bookmarks keep working.

    All POST mutation endpoints (extend-trial, toggle-active,
    discounts CRUD, feature-flags CRUD, etc.) stay live in
    app.py as direct callers."""
    from app import superadmin_required

    @superadmin_required
    def _h():
        if request.args.get("tab") == "audit":
            return redirect(
                url_for("superadmin_redirects.superadmin_audit_log"),
            )
        qs = (
            request.query_string.decode("latin-1")
            if request.query_string else ""
        )
        target = "/app/superadmin/controls" + (f"?{qs}" if qs else "")
        return redirect(target, code=301)

    return _h()
