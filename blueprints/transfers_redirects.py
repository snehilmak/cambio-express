"""Transfers SPA-cutover redirects.

Extracted from ``app.py`` as part of the D2 Blueprint split. Four
pure 301 redirects pointing at the React Transfers pages:

  GET      /transfers            301 → /app/transfers (filtered list)
  GET/POST /transfers/new        301 → /app/transfers/new (create form)
  GET/POST /transfers/<int>/edit 301 → /app/transfers/<id>/edit
  POST     /transfers/<int>/delete 301 → /app/transfers (admin_required;
                                          legacy form-POST delete handler)

The real create/edit/delete/audit logic lives in
``api/Modules/Transfers/Controllers + Services`` and is exercised
by the SPA at ``/app/transfers/*``.

The `/transfers` GET route has a small extra: when the session is
missing a `store_id`, flash an error and bounce back to the
dashboard (no-store error path). The legacy `partial=1` AJAX marker
is also stripped on redirect so a deep-link from a cached page
lands cleanly in the SPA.

Endpoint-name churn:
  url_for("transfers")        → url_for("transfers_redirects.transfers")
  url_for("new_transfer")     → url_for("transfers_redirects.new_transfer")
  url_for("edit_transfer")    → url_for("transfers_redirects.edit_transfer")
  url_for("delete_transfer")  → url_for("transfers_redirects.delete_transfer")
"""
from __future__ import annotations

from flask import (
    Blueprint, flash, redirect, request, session, url_for,
)


bp = Blueprint("transfers_redirects", __name__)


@bp.route("/transfers")
def transfers():
    """301 → /app/transfers. Without a store context bounce to
    /dashboard with a flash — the SPA would also blow up trying to
    request /api/v2/transfers, so we catch that here. Query string
    preserved minus the legacy `partial=1` marker."""
    from app import login_required

    @login_required
    def _h():
        if not session.get("store_id"):
            flash("Select a store first.", "error")
            return redirect(url_for("spa_redirects.dashboard"))
        qs = (
            request.query_string.decode("latin-1")
            if request.query_string else ""
        )
        if qs:
            qs = "&".join(p for p in qs.split("&") if p != "partial=1")
        target = "/app/transfers" + (f"?{qs}" if qs else "")
        return redirect(target, code=301)

    return _h()


@bp.route("/transfers/new", methods=["GET", "POST"])
def new_transfer():
    """301 → /app/transfers/new. SPA POSTs to /api/v2/transfers
    directly. Both verbs redirect — any in-flight Jinja form
    submission lands the user on the SPA create page (their data
    is lost, but the SPA forms have been the canonical path for
    weeks)."""
    from app import login_required
    return login_required(
        lambda: redirect("/app/transfers/new", code=301)
    )()


@bp.route("/transfers/<int:tid>/edit", methods=["GET", "POST"])
def edit_transfer(tid: int):
    """301 → /app/transfers/<tid>/edit. SPA PUTs to
    /api/v2/transfers/<id> directly with the same federal-tax
    recompute, customer-upsert, and TransferAudit behaviour the
    legacy POST handled."""
    from app import login_required
    return login_required(
        lambda: redirect(f"/app/transfers/{tid}/edit", code=301)
    )()


@bp.route("/transfers/<int:tid>/delete", methods=["POST"])
def delete_transfer(tid: int):
    """301 → /app/transfers. SPA DELETEs /api/v2/transfers/<id>
    with the same admin-role guard + audit-log row + cross-store
    404. Audit-log invariant (`action='delete',
    target_type='transfer'`) is preserved on the API side."""
    from app import admin_required

    @admin_required
    def _h():
        return redirect("/app/transfers", code=301)

    return _h()
