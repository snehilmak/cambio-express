"""Bookkeeping-list SPA-cutover redirects.

Extracted from ``app.py`` as part of the D2 Blueprint split. Nine
pure 301 redirects pointing at the React Daily / Monthly / Return-
Checks / ACH-Batches pages:

  GET      /daily                          301 → /app/daily
                                            (preserves ?year=&month=)
  GET      /monthly                        301 → /app/monthly
  GET/POST /monthly/<int:y>/<int:m>        301 → /app/monthly/edit
                                            ?year=&month=
  GET      /monthly/new                    301 → /app/monthly/edit
                                            (current month)
  GET      /return-checks                  301 → /app/return-checks
                                            (preserves query string)
  GET      /batches                        301 → /app/batches
                                            (preserves ?sort=&dir=)
  GET/POST /batches/new                    301 → /app/batches/new
  GET/POST /batches/<int:bid>/edit         301 → /app/batches/<id>/edit
  GET      /batches/<int:bid>/transfers    301 → /app/batches/<id>/edit
                                            (legacy detail page folded
                                            into edit on the SPA)

The mutating sibling routes (/daily/<ds>/{lock,unlock,line-items/*},
/return-checks/{new,/payment,/loss,…}, etc.) stay in app.py for
now — those are real form-POST handlers that still drive the live
mutation surface; they get migrated as a coordinated batch in a
follow-up.

Endpoint-name churn:
  url_for("daily_list")        → url_for("bookkeeping_redirects.daily_list")
  url_for("monthly_list")      → url_for("bookkeeping_redirects.monthly_list")
  url_for("monthly_report")    → url_for("bookkeeping_redirects.monthly_report")
  url_for("monthly_new")       → url_for("bookkeeping_redirects.monthly_new")
  url_for("return_checks")     → url_for("bookkeeping_redirects.return_checks")
  url_for("batches")           → url_for("bookkeeping_redirects.batches")
  url_for("new_batch")         → url_for("bookkeeping_redirects.new_batch")
  url_for("edit_batch")        → url_for("bookkeeping_redirects.edit_batch")
  url_for("batch_transfers")   → url_for("bookkeeping_redirects.batch_transfers")
"""
from __future__ import annotations

from datetime import date

from flask import Blueprint, redirect, request


bp = Blueprint("bookkeeping_redirects", __name__)


@bp.route("/daily")
def daily_list():
    """301 → /app/daily. SPA reads /api/v2/daily/period?from=&to= for
    the same in-period rows. Query string (year + month) preserved
    so a deep-link to a specific month lands on the right calendar."""
    from app import admin_required

    @admin_required
    def _h():
        qs = (
            request.query_string.decode("latin-1")
            if request.query_string else ""
        )
        target = "/app/daily" + (f"?{qs}" if qs else "")
        return redirect(target, code=301)

    return _h()


@bp.route("/monthly")
def monthly_list():
    """301 → /app/monthly. SPA reads /api/v2/monthly/months for the
    index and /api/v2/monthly/<y>/<m> for each entry."""
    from app import admin_required
    return admin_required(lambda: redirect("/app/monthly", code=301))()


@bp.route("/monthly/<int:year>/<int:month>", methods=["GET", "POST"])
def monthly_report(year: int, month: int):
    """301 → /app/monthly/edit?year=&month=. SPA PUTs to
    /api/v2/monthly/<y>/<m> with the same locked-fields contract."""
    from app import admin_required
    return admin_required(
        lambda: redirect(
            f"/app/monthly/edit?year={year}&month={month}", code=301,
        )
    )()


@bp.route("/monthly/new")
def monthly_new():
    """301 → /app/monthly/edit?year=<this year>&month=<this month>."""
    from app import admin_required

    @admin_required
    def _h():
        today = date.today()
        return redirect(
            f"/app/monthly/edit?year={today.year}&month={today.month}",
            code=301,
        )

    return _h()


@bp.route("/return-checks")
def return_checks():
    """301 → /app/return-checks. Query string preserved so a deep
    link with filters lands cleanly. The mutating routes
    (/return-checks/new, /payment, /loss, etc.) stay alive
    intentionally so in-flight Jinja form-submits during rollout
    still work."""
    from app import admin_required

    @admin_required
    def _h():
        qs = (
            request.query_string.decode("latin-1")
            if request.query_string else ""
        )
        target = "/app/return-checks" + (f"?{qs}" if qs else "")
        return redirect(target, code=301)

    return _h()


@bp.route("/batches")
def batches():
    """301 → /app/batches. Query string (sort + dir) preserved so a
    deep-link like ``?sort=ach_date&dir=asc`` lands the SPA in the
    same sort state."""
    from app import admin_required

    @admin_required
    def _h():
        qs = (
            request.query_string.decode("latin-1")
            if request.query_string else ""
        )
        target = "/app/batches" + (f"?{qs}" if qs else "")
        return redirect(target, code=301)

    return _h()


@bp.route("/batches/new", methods=["GET", "POST"])
def new_batch():
    """301 → /app/batches/new. SPA POSTs to /api/v2/batches
    directly."""
    from app import admin_required
    return admin_required(
        lambda: redirect("/app/batches/new", code=301)
    )()


@bp.route("/batches/<int:bid>/edit", methods=["GET", "POST"])
def edit_batch(bid: int):
    """301 → /app/batches/<bid>/edit. SPA's BatchForm.tsx PATCHes
    /api/v2/batches/<id>."""
    from app import admin_required
    return admin_required(
        lambda: redirect(f"/app/batches/{bid}/edit", code=301)
    )()


@bp.route("/batches/<int:bid>/transfers")
def batch_transfers(bid: int):
    """301 → /app/batches/<bid>/edit. The legacy "batch detail"
    template was a separate page; the SPA folds the same content
    into the edit screen."""
    from app import admin_required
    return admin_required(
        lambda: redirect(f"/app/batches/{bid}/edit", code=301)
    )()
