"""Admin SPA-cutover redirects.

Extracted from ``app.py`` as part of the D2 Blueprint split. Five
pure 301 redirects pointing at the React admin pages:

  GET      /admin/tax-export             301 → /app/admin/tax-export
                                          (preserves ?year=)
  GET/POST /admin/users                  301 → /app/admin/users
                                          (preserves query string)
  GET      /admin/audit-log              301 → /app/admin/audit-log
                                          (preserves filter +
                                          pagination query string)
  GET/POST /admin/users/new              301 → /app/admin/users/new
  GET/POST /admin/users/<int:uid>/edit   301 → /app/admin/users/<uid>/edit

The /admin/tax-export.zip route (which actually streams the
multi-MB CSV bundle) stays in app.py — it's not a redirect, and
moving it would haul along the dozen `_tax_pack_*_csv` helpers.

/admin/settings has a mutating POST path that stays in app.py too;
only its GET case was already redirecting to /app/settings.

Endpoint-name churn:
  url_for("admin_tax_export") → url_for("admin_redirects.admin_tax_export")
  url_for("admin_users")      → url_for("admin_redirects.admin_users")
  url_for("admin_audit_log")  → url_for("admin_redirects.admin_audit_log")
  url_for("admin_new_user")   → url_for("admin_redirects.admin_new_user")
  url_for("admin_edit_user")  → url_for("admin_redirects.admin_edit_user")
"""
from __future__ import annotations

from flask import Blueprint, redirect, request


bp = Blueprint("admin_redirects", __name__)


@bp.route("/admin/tax-export")
def admin_tax_export():
    """301 → /app/admin/tax-export. Year choices come from
    /api/v2/admin/tax-export/years. The actual ZIP build still
    lives at /admin/tax-export.zip (stays in app.py — that
    composes a swathe of `_tax_pack_*_csv` helpers)."""
    from app import admin_required

    @admin_required
    def _h():
        qs = (
            request.query_string.decode("latin-1")
            if request.query_string else ""
        )
        target = "/app/admin/tax-export" + (f"?{qs}" if qs else "")
        return redirect(target, code=301)

    return _h()


@bp.route("/admin/users", methods=["GET", "POST"])
def admin_users():
    """301 → /app/admin/users. SPA POSTs to /api/v2/admin/users[...]
    directly."""
    from app import admin_required

    @admin_required
    def _h():
        qs = (
            request.query_string.decode("latin-1")
            if request.query_string else ""
        )
        target = "/app/admin/users" + (f"?{qs}" if qs else "")
        return redirect(target, code=301)

    return _h()


@bp.route("/admin/audit-log")
def admin_audit_log():
    """301 → /app/admin/audit-log. Filter + pagination logic now
    lives behind /api/v2/admin/audit-log (target, action, user,
    page query params preserved through the redirect)."""
    from app import admin_required

    @admin_required
    def _h():
        qs = (
            request.query_string.decode("latin-1")
            if request.query_string else ""
        )
        target = "/app/admin/audit-log" + (f"?{qs}" if qs else "")
        return redirect(target, code=301)

    return _h()


@bp.route("/admin/users/new", methods=["GET", "POST"])
def admin_new_user():
    """301 → /app/admin/users/new. SPA POSTs to /api/v2/admin/users
    directly."""
    from app import admin_required
    return admin_required(
        lambda: redirect("/app/admin/users/new", code=301)
    )()


@bp.route("/admin/users/<int:uid>/edit", methods=["GET", "POST"])
def admin_edit_user(uid: int):
    """301 → /app/admin/users/<uid>/edit. SPA PATCHes to
    /api/v2/admin/users/<uid> directly."""
    from app import admin_required
    return admin_required(
        lambda: redirect(f"/app/admin/users/{uid}/edit", code=301)
    )()
