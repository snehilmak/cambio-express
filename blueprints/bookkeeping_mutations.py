"""Bookkeeping mutation handlers.

Extracted from ``app.py`` as part of the D2 Blueprint split. Thirteen
mutation routes covering the daily-book editor + return-checks
ledger:

  Daily editor (5 routes — all now thin 301 redirects to the SPA
  editor; the real mutation work moved to
  /api/v2/daily/<store>/<date>/* and lives in
  api/Modules/DailyBook/):
    GET/POST  /daily/<ds>
    POST      /daily/<ds>/line-items/<kind>/new
    POST      /daily/<ds>/line-items/<kind>/<item_id>/delete
    POST      /daily/<ds>/lock
    POST      /daily/<ds>/unlock

  Return-checks (8 routes — these still do real form-POST work
  because the return-checks ledger is one of the few admin
  surfaces that hasn't been ported to React yet):
    POST  /return-checks/new
    POST  /return-checks/<rc_id>/payment
    POST  /return-checks/<rc_id>/payment/<pid>/delete
    POST  /return-checks/<rc_id>/loss
    POST  /return-checks/<rc_id>/fraud
    POST  /return-checks/<rc_id>/reopen
    POST  /return-checks/<rc_id>/edit
    POST  /return-checks/<rc_id>/delete

Every handler redirects to
``bookkeeping_redirects.return_checks`` (or the SPA equivalent for
daily) so the post-action URL stays stable.

Helpers stay in app.py and are pulled in via late imports:
  ``_get_owned_return_check``, ``_create_daily_payback_for``,
  ``_delete_daily_paybacks_for_payment``, ``_close_as_writeoff``,
  ``_PAYMENT_METHODS``, ``ReturnCheck``, ``ReturnCheckPayment``,
  ``DailyLineItem``, ``current_user``, ``admin_required``, ``db``.

Endpoint-name churn:
  url_for("daily_report")           → url_for("bookkeeping_mutations.daily_report")
  url_for("daily_line_item_new")    → url_for("bookkeeping_mutations.daily_line_item_new")
  url_for("daily_line_item_delete") → url_for("bookkeeping_mutations.daily_line_item_delete")
  url_for("daily_report_lock")      → url_for("bookkeeping_mutations.daily_report_lock")
  url_for("daily_report_unlock")    → url_for("bookkeeping_mutations.daily_report_unlock")
  url_for("return_check_new")       → url_for("bookkeeping_mutations.return_check_new")
  url_for("return_check_payment_new") → url_for("bookkeeping_mutations.return_check_payment_new")
  url_for("return_check_payment_delete") → url_for("bookkeeping_mutations.return_check_payment_delete")
  url_for("return_check_loss")      → url_for("bookkeeping_mutations.return_check_loss")
  url_for("return_check_fraud")     → url_for("bookkeeping_mutations.return_check_fraud")
  url_for("return_check_reopen")    → url_for("bookkeeping_mutations.return_check_reopen")
  url_for("return_check_edit")      → url_for("bookkeeping_mutations.return_check_edit")
  url_for("return_check_delete")    → url_for("bookkeeping_mutations.return_check_delete")
"""
from __future__ import annotations

from datetime import date, datetime

from flask import Blueprint, flash, redirect, request, session, url_for


bp = Blueprint("bookkeeping_mutations", __name__)


# ── Daily editor (SPA-redirect shims) ─────────────────────────

@bp.route("/daily/<string:ds>", methods=["GET", "POST"])
def daily_report(ds: str):
    """301 → /app/daily/edit?date=<ds>. The per-day editor (with the
    full daily-book + MT-summary spreadsheet) moved to React; the SPA
    PUTs to /api/v2/daily/<store>/<date> with the same locked-fields
    contract (server still derives line-item totals + the MT grand
    total + bounces locked-day writes). Both verbs redirect."""
    from app import admin_required

    @admin_required
    def _h():
        return redirect(f"/app/daily/edit?date={ds}", code=301)

    return _h()


@bp.route(
    "/daily/<string:ds>/line-items/<string:kind>/new",
    methods=["POST"],
)
def daily_line_item_new(ds: str, kind: str):
    """301 → /app/daily/edit?date=<ds>. The legacy AJAX endpoint
    (drops / check-deposits widget) moved to React; the SPA POSTs
    to /api/v2/daily/<store>/<date>/line-items with the same locked-
    day + return-payback gates enforced server-side. Anyone still
    holding the old form URL lands on the SPA editor."""
    from app import admin_required

    @admin_required
    def _h():
        return redirect(f"/app/daily/edit?date={ds}", code=301)

    return _h()


@bp.route(
    "/daily/<string:ds>/line-items/<string:kind>/<int:item_id>/delete",
    methods=["POST"],
)
def daily_line_item_delete(ds: str, kind: str, item_id: int):
    """301 → /app/daily/edit?date=<ds>. Delete moved to the SPA
    (DELETE /api/v2/daily/<store>/<date>/line-items/<id>). The
    return-check-linkage guard lives in the Service so the SPA-side
    and Return-Checks-side delete paths can't drift."""
    from app import admin_required

    @admin_required
    def _h():
        return redirect(f"/app/daily/edit?date={ds}", code=301)

    return _h()


@bp.route("/daily/<string:ds>/lock", methods=["POST"])
def daily_report_lock(ds: str):
    """301 → /app/daily/edit?date=<ds>. Lock moved to the SPA (POST
    /api/v2/daily/<store>/<date>/lock). Audit-log row writing moved
    with it — see api/Modules/DailyBook/Controllers
    `_audit_daily_lock_action`."""
    from app import admin_required

    @admin_required
    def _h():
        return redirect(f"/app/daily/edit?date={ds}", code=301)

    return _h()


@bp.route("/daily/<string:ds>/unlock", methods=["POST"])
def daily_report_unlock(ds: str):
    """301 → /app/daily/edit?date=<ds>. Same migration as lock — the
    SPA POSTs to /api/v2/daily/<store>/<date>/unlock and the audit
    row lands on that side."""
    from app import admin_required

    @admin_required
    def _h():
        return redirect(f"/app/daily/edit?date={ds}", code=301)

    return _h()


# ── Return-checks ledger (real form-POST handlers) ────────────

@bp.route("/return-checks/new", methods=["POST"])
def return_check_new():
    from app import (
        ReturnCheck, admin_required, current_user, db,
    )

    @admin_required
    def _h():
        sid = session["store_id"]
        user = current_user()
        bounced_on_s = (request.form.get("bounced_on") or "").strip()
        customer = (request.form.get("customer_name") or "").strip()
        amount_s = (request.form.get("amount") or "").strip()
        if not bounced_on_s or not customer or not amount_s:
            flash("Date, customer, and amount are required.", "error")
            return redirect(url_for(
                "bookkeeping_redirects.return_checks",
            ))
        try:
            bounced_on = datetime.strptime(
                bounced_on_s, "%Y-%m-%d",
            ).date()
        except ValueError:
            flash("Invalid bounce date.", "error")
            return redirect(url_for(
                "bookkeeping_redirects.return_checks",
            ))
        try:
            amount = float(amount_s)
        except ValueError:
            flash("Invalid amount.", "error")
            return redirect(url_for(
                "bookkeeping_redirects.return_checks",
            ))
        if amount <= 0:
            flash("Amount must be greater than zero.", "error")
            return redirect(url_for(
                "bookkeeping_redirects.return_checks",
            ))

        rc = ReturnCheck(
            store_id=sid,
            bounced_on=bounced_on,
            customer_name=customer[:120],
            check_number=(
                request.form.get("check_number") or ""
            ).strip()[:40],
            payer_bank=(
                request.form.get("payer_bank") or ""
            ).strip()[:120],
            amount=amount,
            notes=(request.form.get("notes") or "").strip(),
            status="pending",
            created_by=user.id,
        )
        db.session.add(rc)
        db.session.commit()
        flash(
            f"Return check logged for {rc.customer_name} "
            f"(${rc.amount:,.2f}).",
            "success",
        )
        return redirect(url_for(
            "bookkeeping_redirects.return_checks",
        ))

    return _h()


@bp.route("/return-checks/<int:rc_id>/payment", methods=["POST"])
def return_check_payment_new(rc_id: int):
    """Log one installment of repayment.

    Validates the amount fits within the still-outstanding balance.
    On a fully-paid parent we auto-flip status='recovered' so the
    admin doesn't have to click a separate "close" button — and the
    P&L doesn't double-count: the closing event simply marks WHEN it
    became fully recovered, the actual recovered $ already counted at
    the payment level.
    """
    from app import (
        ReturnCheckPayment, _PAYMENT_METHODS,
        _create_daily_payback_for, _get_owned_return_check,
        admin_required, current_user, db,
    )

    @admin_required
    def _h():
        rc, err = _get_owned_return_check(rc_id)
        if err is not None:
            return err
        if rc.status in ("loss", "fraud"):
            flash(
                "This return check is closed (loss/fraud) — reopen it "
                "first.",
                "error",
            )
            return redirect(url_for(
                "bookkeeping_redirects.return_checks",
            ))

        amt_s = (request.form.get("amount") or "").strip()
        paid_s = (request.form.get("paid_on") or "").strip()
        method = (
            request.form.get("payment_method") or ""
        ).strip().lower()
        note = (request.form.get("note") or "").strip()
        if method and method not in _PAYMENT_METHODS:
            method = "other"
        try:
            amt = float(amt_s)
        except ValueError:
            flash("Invalid payment amount.", "error")
            return redirect(url_for(
                "bookkeeping_redirects.return_checks",
            ))
        remaining = rc.remaining
        if amt <= 0:
            flash(
                "Payment amount must be greater than zero.", "error",
            )
            return redirect(url_for(
                "bookkeeping_redirects.return_checks",
            ))
        if amt > remaining + 0.005:
            flash(
                f"Payment $ {amt:,.2f} exceeds remaining balance "
                f"${remaining:,.2f}. Lower the amount or split into "
                f"multiple payments.",
                "error",
            )
            return redirect(url_for(
                "bookkeeping_redirects.return_checks",
            ))
        try:
            paid_on = (
                datetime.strptime(paid_s, "%Y-%m-%d").date()
                if paid_s else date.today()
            )
        except ValueError:
            flash("Invalid payment date.", "error")
            return redirect(url_for(
                "bookkeeping_redirects.return_checks",
            ))

        user = current_user()
        payment = ReturnCheckPayment(
            return_check_id=rc.id,
            amount=amt,
            paid_on=paid_on,
            payment_method=method,
            note=note[:200],
            created_by=user.id if user else None,
        )
        prior_total = rc.recovered_total
        db.session.add(payment)
        db.session.flush()
        _create_daily_payback_for(rc, payment)
        new_total = prior_total + amt
        if new_total + 0.005 >= float(rc.amount or 0.0):
            rc.status = "recovered"
            rc.status_changed_on = paid_on
        db.session.commit()
        flash(
            f"Logged ${amt:,.2f} payment for {rc.customer_name}"
            + (f" via {method}" if method else "") + ".",
            "success",
        )
        return redirect(url_for(
            "bookkeeping_redirects.return_checks",
        ))

    return _h()


@bp.route(
    "/return-checks/<int:rc_id>/payment/<int:pid>/delete",
    methods=["POST"],
)
def return_check_payment_delete(rc_id: int, pid: int):
    """Remove one installment. Drops the shadow daily-book line item
    and, if the parent was auto-flipped to 'recovered' but the
    deletion now leaves the balance > 0, walks status back to
    'pending' so the row reappears in the active list."""
    from app import (
        ReturnCheckPayment, _delete_daily_paybacks_for_payment,
        _get_owned_return_check, admin_required, db,
    )

    @admin_required
    def _h():
        rc, err = _get_owned_return_check(rc_id)
        if err is not None:
            return err
        payment = db.session.get(ReturnCheckPayment, pid)
        if payment is None or payment.return_check_id != rc.id:
            flash("Payment not found.", "error")
            return redirect(url_for(
                "bookkeeping_redirects.return_checks",
            ))
        _delete_daily_paybacks_for_payment(
            rc, payment.amount, payment.paid_on,
        )
        db.session.delete(payment)
        db.session.flush()
        if (
            rc.status == "recovered"
            and rc.recovered_total + 0.005 < float(rc.amount or 0.0)
        ):
            rc.status = "pending"
            rc.status_changed_on = None
        db.session.commit()
        flash("Payment removed.", "success")
        return redirect(url_for(
            "bookkeeping_redirects.return_checks",
        ))

    return _h()


@bp.route("/return-checks/<int:rc_id>/loss", methods=["POST"])
def return_check_loss(rc_id: int):
    from app import _close_as_writeoff, admin_required

    @admin_required
    def _h():
        return _close_as_writeoff(rc_id, "loss")

    return _h()


@bp.route("/return-checks/<int:rc_id>/fraud", methods=["POST"])
def return_check_fraud(rc_id: int):
    from app import _close_as_writeoff, admin_required

    @admin_required
    def _h():
        return _close_as_writeoff(rc_id, "fraud")

    return _h()


@bp.route("/return-checks/<int:rc_id>/reopen", methods=["POST"])
def return_check_reopen(rc_id: int):
    """Undo a recover / loss / fraud — returns the row to pending.
    Payments themselves are NOT deleted (they represent real money
    that came in); only the closing status is reverted. To remove an
    individual payment, use the payment-delete route."""
    from app import _get_owned_return_check, admin_required, db

    @admin_required
    def _h():
        rc, err = _get_owned_return_check(rc_id)
        if err is not None:
            return err
        rc.status = "pending"
        rc.status_changed_on = None
        db.session.commit()
        flash(f"Reopened: {rc.customer_name}.", "success")
        return redirect(url_for(
            "bookkeeping_redirects.return_checks",
        ))

    return _h()


@bp.route("/return-checks/<int:rc_id>/edit", methods=["POST"])
def return_check_edit(rc_id: int):
    from app import _get_owned_return_check, admin_required, db

    @admin_required
    def _h():
        rc, err = _get_owned_return_check(rc_id)
        if err is not None:
            return err
        customer = (request.form.get("customer_name") or "").strip()
        if customer:
            rc.customer_name = customer[:120]
        rc.check_number = (
            request.form.get("check_number") or ""
        ).strip()[:40]
        rc.payer_bank = (
            request.form.get("payer_bank") or ""
        ).strip()[:120]
        rc.notes = (request.form.get("notes") or "").strip()
        if rc.status == "pending":
            amt_s = (request.form.get("amount") or "").strip()
            if amt_s:
                try:
                    amt = float(amt_s)
                    if amt > 0:
                        rc.amount = amt
                except ValueError:
                    pass
            on_s = (request.form.get("bounced_on") or "").strip()
            if on_s:
                try:
                    rc.bounced_on = datetime.strptime(
                        on_s, "%Y-%m-%d",
                    ).date()
                except ValueError:
                    pass
        db.session.commit()
        flash("Return check updated.", "success")
        return redirect(url_for(
            "bookkeeping_redirects.return_checks",
        ))

    return _h()


@bp.route("/return-checks/<int:rc_id>/delete", methods=["POST"])
def return_check_delete(rc_id: int):
    from app import (
        DailyLineItem, _get_owned_return_check, admin_required, db,
    )

    @admin_required
    def _h():
        rc, err = _get_owned_return_check(rc_id)
        if err is not None:
            return err
        DailyLineItem.query.filter_by(
            store_id=rc.store_id,
            return_check_id=rc.id,
            kind="return_payback",
        ).delete(synchronize_session=False)
        db.session.delete(rc)
        db.session.commit()
        flash("Return check deleted.", "success")
        return redirect(url_for(
            "bookkeeping_redirects.return_checks",
        ))

    return _h()
