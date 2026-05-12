"""Bank-side mutation handlers.

Extracted from ``app.py`` as part of the D2 Blueprint split. Thirteen
POST handlers covering the bank-connection lifecycle, reconcile
actions, and BankRule CRUD:

  Stripe Financial Connections lifecycle:
    POST  /bank/stripe/connect            → JSON {clientSecret, ...}
    GET   /bank/stripe/return             → flash + redirect
    POST  /bank/stripe/refresh            → refresh balances
    POST  /bank/stripe/sync-transactions  → pull new BankTransactions
    POST  /bank/stripe/nickname/<id>      → set/clear nickname
    POST  /bank/stripe/disconnect/<id>    → disable account

  Per-transaction reconcile:
    POST  /bank/transactions/<id>/categorize    → tag + create daily line
    POST  /bank/transactions/<id>/uncategorize  → untag + drop line
    POST  /bank/transactions/<id>/move-date     → re-date daily line

  BankRule CRUD (delegates parsing/validation to
  api.Modules.BankSync.Services.rules):
    POST  /bank/rules/new
    POST  /bank/rules/<id>/edit
    POST  /bank/rules/<id>/toggle
    POST  /bank/rules/<id>/delete

Helpers stay in app.py and are pulled in via late imports.

Endpoint-name churn:
  url_for("bank_stripe_connect")           → url_for("bank_mutations.bank_stripe_connect")
  url_for("bank_stripe_return")            → url_for("bank_mutations.bank_stripe_return")
  url_for("bank_stripe_refresh")           → url_for("bank_mutations.bank_stripe_refresh")
  url_for("bank_stripe_sync_transactions") → url_for("bank_mutations.bank_stripe_sync_transactions")
  url_for("bank_transaction_categorize")   → url_for("bank_mutations.bank_transaction_categorize")
  url_for("bank_transaction_uncategorize") → url_for("bank_mutations.bank_transaction_uncategorize")
  url_for("bank_transaction_move_date")    → url_for("bank_mutations.bank_transaction_move_date")
  url_for("bank_rule_new")                 → url_for("bank_mutations.bank_rule_new")
  url_for("bank_rule_edit")                → url_for("bank_mutations.bank_rule_edit")
  url_for("bank_rule_toggle")              → url_for("bank_mutations.bank_rule_toggle")
  url_for("bank_rule_delete")              → url_for("bank_mutations.bank_rule_delete")
  url_for("bank_stripe_set_nickname")      → url_for("bank_mutations.bank_stripe_set_nickname")
  url_for("bank_stripe_disconnect")        → url_for("bank_mutations.bank_stripe_disconnect")
"""
from __future__ import annotations

from datetime import datetime, timedelta

from flask import (
    Blueprint, abort, flash, jsonify, redirect, request, session, url_for,
)


bp = Blueprint("bank_mutations", __name__)


@bp.route("/bank/stripe/connect", methods=["POST"])
def bank_stripe_connect():
    """Create a Stripe Financial Connections session and return its
    client_secret as JSON. The browser then opens the Stripe-hosted FC
    modal via stripe.js (collectFinancialConnectionsAccounts), which
    settles the linking flow and POSTs the user back to
    /bank/stripe/return?session_id=<id> on success.

    Stripe's FC API does NOT expose a server-side hosted URL — the
    browser drives the modal directly with the client_secret."""
    from app import (
        MAX_BANK_ACCOUNTS_PER_STORE, StripeBankAccount, app as flask_app,
        current_store, ensure_stripe_customer, pro_required, stripe,
        stripe_is_configured, stripe_publishable_key,
    )

    @pro_required
    def _h():
        if not stripe_is_configured():
            return jsonify({
                "error": "Stripe isn't configured yet — ask the platform admin.",
            }), 503
        if not stripe_publishable_key():
            return jsonify({
                "error": (
                    "STRIPE_PUBLISHABLE_KEY is not set; the FC modal "
                    "can't initialize."
                ),
            }), 503
        store = current_store()
        existing_count = StripeBankAccount.query.filter_by(
            store_id=store.id, enabled=True,
        ).count()
        if existing_count >= MAX_BANK_ACCOUNTS_PER_STORE:
            return jsonify({
                "error": (
                    f"You've reached the {MAX_BANK_ACCOUNTS_PER_STORE}-"
                    "account limit. Disconnect an account first to free "
                    "up a slot."
                ),
            }), 409
        try:
            customer_id = ensure_stripe_customer(store)
            fc_session = stripe.financial_connections.Session.create(
                account_holder={"type": "customer", "customer": customer_id},
                permissions=["balances", "transactions"],
                prefetch=["balances", "transactions"],
                filters={"countries": ["US"]},
                return_url=url_for(
                    "bank_mutations.bank_stripe_return", _external=True,
                ),
            )
            session["fc_session_id"] = fc_session.id
            return jsonify({
                "clientSecret": fc_session.client_secret,
                "sessionId": fc_session.id,
                "publishableKey": stripe_publishable_key(),
                "returnUrl": url_for(
                    "bank_mutations.bank_stripe_return",
                    session_id=fc_session.id,
                ),
            })
        except stripe.error.StripeError as e:
            flask_app.logger.error(f"FC session create failed: {e}")
            msg = e.user_message or str(e)
            return jsonify({
                "error": f"Could not start the bank connection: {msg}",
            }), 502

    return _h()


@bp.route("/bank/stripe/return")
def bank_stripe_return():
    """Called by the browser after the FC modal finishes. Accepts
    session_id from the query string (Stripe.js path) or falls back to
    the server-side session value (for browsers that lose the query
    after a redirect chain)."""
    from app import (
        INITIAL_SYNC_DAYS_BACK, MAX_BANK_ACCOUNTS_PER_STORE,
        StripeBankAccount, _upsert_fc_account, app as flask_app,
        current_store, db, pro_required, refresh_bank_balances, stripe,
        sync_bank_transactions,
    )

    @pro_required
    def _h():
        sid = session["store_id"]
        fc_session_id = (
            request.args.get("session_id")
            or session.pop("fc_session_id", None)
        )
        if not fc_session_id:
            flash("No active bank-link session found.", "error")
            return redirect(url_for("bank_redirects.bank"))
        session.pop("fc_session_id", None)
        try:
            fc_session = stripe.financial_connections.Session.retrieve(
                fc_session_id, expand=["accounts"],
            )
            accounts = (
                fc_session.accounts.data
                if hasattr(fc_session, "accounts") else []
            )
            if not accounts:
                flash("No accounts were linked.", "error")
                return redirect(url_for("bank_redirects.bank"))
            existing_ids = {
                row.stripe_account_id for row in
                StripeBankAccount.query.filter_by(
                    store_id=sid, enabled=True,
                ).all()
            }
            slots_remaining = (
                MAX_BANK_ACCOUNTS_PER_STORE - len(existing_ids)
            )
            kept = 0
            skipped = 0
            for acct_summary in accounts:
                already_linked = acct_summary.id in existing_ids
                if not already_linked and slots_remaining <= 0:
                    skipped += 1
                    continue
                full = (
                    stripe.financial_connections.Account.retrieve(
                        acct_summary.id,
                    )
                )
                _upsert_fc_account(sid, full)
                try:
                    stripe.financial_connections.Account.subscribe(
                        acct_summary.id, features=["transactions"],
                    )
                except stripe.error.StripeError as e:
                    flask_app.logger.warning(
                        f"FC transactions subscribe failed for "
                        f"{acct_summary.id}: {e}",
                    )
                try:
                    stripe.financial_connections.Account.refresh_account(
                        acct_summary.id, features=["transactions"],
                    )
                except stripe.error.StripeError as e:
                    flask_app.logger.warning(
                        f"FC transactions refresh failed for "
                        f"{acct_summary.id}: {e}",
                    )
                if not already_linked:
                    slots_remaining -= 1
                kept += 1
            db.session.commit()
            try:
                refresh_bank_balances(current_store())
            except Exception as e:
                flask_app.logger.warning(
                    f"post-connect refresh failed: {e}",
                )
            try:
                initial_since = datetime.combine(
                    (datetime.utcnow() - timedelta(
                        days=INITIAL_SYNC_DAYS_BACK,
                    )).date(),
                    datetime.min.time(),
                )
                sync_bank_transactions(
                    current_store(), since=initial_since,
                )
            except Exception as e:
                flask_app.logger.warning(
                    f"post-connect initial txn sync failed: {e}",
                )
            if skipped:
                flash(
                    (
                        f"Connected {kept} account(s); skipped {skipped} "
                        f"because the per-store limit is "
                        f"{MAX_BANK_ACCOUNTS_PER_STORE}. Disconnect an "
                        "existing account to free a slot."
                    ),
                    "warning",
                )
            else:
                flash(
                    f"Connected {kept} account(s) via Stripe.", "success",
                )
        except stripe.error.StripeError as e:
            flask_app.logger.error(f"FC session retrieve failed: {e}")
            flash(
                f"Stripe error while completing the link: "
                f"{e.user_message or str(e)}",
                "error",
            )
        return redirect(url_for("bank_redirects.bank"))

    return _h()


@bp.route("/bank/stripe/refresh", methods=["POST"])
def bank_stripe_refresh():
    """Manually refresh all connected account balances."""
    from app import current_store, pro_required, refresh_bank_balances

    @pro_required
    def _h():
        n, last_error = refresh_bank_balances(current_store())
        if n and not last_error:
            flash(f"Refreshed {n} account(s).", "success")
        elif n and last_error:
            flash(
                f"Refreshed {n} account(s); one or more failed: "
                f"{last_error}",
                "warning",
            )
        elif last_error:
            flash(f"Refresh failed: {last_error}", "error")
        else:
            flash("Nothing to refresh.", "error")
        return redirect(url_for("bank_redirects.bank"))

    return _h()


@bp.route("/bank/stripe/sync-transactions", methods=["POST"])
def bank_stripe_sync_transactions():
    """Pull new transactions for every connected account, gated by the
    per-store rate-limiter so we don't blow through Stripe billing.
    Each Transaction.list call is metered, and a single click can fan
    out to up to MAX_BANK_ACCOUNTS_PER_STORE accounts."""
    from app import (
        MAX_BANK_SYNCS_PER_DAY, _can_sync_bank_transactions,
        _record_bank_sync, current_store, db, pro_required,
        sync_bank_transactions,
    )

    @pro_required
    def _h():
        store = current_store()
        allowed, reason, _ = _can_sync_bank_transactions(store)
        if not allowed:
            flash(reason, "error")
            return redirect(url_for("bank_redirects.bank"))
        new_rows, total, last_error = sync_bank_transactions(store)
        _record_bank_sync(store)
        db.session.commit()
        if last_error and not total:
            flash(f"Sync failed: {last_error}", "error")
        elif last_error:
            flash(
                f"Synced {new_rows} new transaction(s); one or more "
                f"accounts errored: {last_error}",
                "warning",
            )
        else:
            used = store.bank_sync_count_today
            remaining = MAX_BANK_SYNCS_PER_DAY - used
            flash(
                (
                    f"Synced {new_rows} new transaction(s) "
                    f"({remaining} sync(s) remaining today)."
                ),
                "success" if total else "info",
            )
        return redirect(url_for("bank_redirects.bank"))

    return _h()


# ── Reconcile actions ───────────────────────────────────────

@bp.route(
    "/bank/transactions/<int:txn_id>/categorize", methods=["POST"],
)
def bank_transaction_categorize(txn_id: int):
    from app import (
        BankTransaction, _bank_category_label,
        _categorize_bank_transaction, _is_valid_bank_category, db,
        pro_required,
    )

    @pro_required
    def _h():
        sid = session["store_id"]
        txn = BankTransaction.query.filter_by(
            id=txn_id, store_id=sid,
        ).first_or_404()
        target = (request.form.get("kind") or "").strip()
        if not target:
            flash("Pick a category before saving.", "error")
            return redirect(
                request.referrer
                or url_for("bank_redirects.bank_transactions"),
            )
        if not _is_valid_bank_category(target, sid):
            flash("Unknown category.", "error")
            return redirect(
                request.referrer
                or url_for("bank_redirects.bank_transactions"),
            )
        override_date = None
        raw_date = (request.form.get("report_date") or "").strip()
        if raw_date:
            try:
                override_date = datetime.strptime(
                    raw_date, "%Y-%m-%d",
                ).date()
            except ValueError:
                flash("Invalid date.", "error")
                return redirect(
                    request.referrer
                    or url_for("bank_redirects.bank_transactions"),
                )
        _categorize_bank_transaction(
            txn, target, rule=None, post_to_daily=True,
            report_date=override_date,
        )
        db.session.commit()
        flash(
            f"Categorized as {_bank_category_label(target)}.",
            "success",
        )
        return redirect(
            request.referrer
            or url_for("bank_redirects.bank_transactions"),
        )

    return _h()


@bp.route(
    "/bank/transactions/<int:txn_id>/uncategorize", methods=["POST"],
)
def bank_transaction_uncategorize(txn_id: int):
    from app import (
        BankTransaction, _uncategorize_bank_transaction, db,
        pro_required,
    )

    @pro_required
    def _h():
        sid = session["store_id"]
        txn = BankTransaction.query.filter_by(
            id=txn_id, store_id=sid,
        ).first_or_404()
        _uncategorize_bank_transaction(txn)
        db.session.commit()
        flash("Uncategorized; daily-book line removed.", "success")
        return redirect(
            request.referrer
            or url_for("bank_redirects.bank_transactions"),
        )

    return _h()


@bp.route(
    "/bank/transactions/<int:txn_id>/move-date", methods=["POST"],
)
def bank_transaction_move_date(txn_id: int):
    """Re-date the linked DailyLineItem. Use case: the bank posted
    the transaction next morning (e.g. RDC dropped at 9 PM) but the
    cash-handling event belongs on the previous day's book."""
    from app import (
        BankTransaction, DailyLineItem, db, pro_required,
    )

    @pro_required
    def _h():
        sid = session["store_id"]
        txn = BankTransaction.query.filter_by(
            id=txn_id, store_id=sid,
        ).first_or_404()
        if not txn.daily_line_item_id:
            flash(
                "This transaction isn't linked to a daily-book line.",
                "error",
            )
            return redirect(
                request.referrer
                or url_for("bank_redirects.bank_transactions"),
            )
        raw = (request.form.get("report_date") or "").strip()
        if not raw:
            flash("Pick a date.", "error")
            return redirect(
                request.referrer
                or url_for("bank_redirects.bank_transactions"),
            )
        try:
            new_date = datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid date.", "error")
            return redirect(
                request.referrer
                or url_for("bank_redirects.bank_transactions"),
            )
        line = db.session.get(DailyLineItem, txn.daily_line_item_id)
        if line is None:
            txn.daily_line_item_id = None
            db.session.commit()
            flash(
                "Linked line not found; cleared the link.", "warning",
            )
            return redirect(
                request.referrer
                or url_for("bank_redirects.bank_transactions"),
            )
        line.report_date = new_date
        db.session.commit()
        flash(f"Moved to {new_date.isoformat()}.", "success")
        return redirect(
            request.referrer
            or url_for("bank_redirects.bank_transactions"),
        )

    return _h()


# ── Rules CRUD ──────────────────────────────────────────────

@bp.route("/bank/rules/new", methods=["POST"])
def bank_rule_new():
    """Create a BankRule. Validation, account-scope check, and the
    INSERT itself live in api.Modules.BankSync.Services.rules; this
    route handles the Flask form-redirect + flash glue."""
    from api.Modules.BankSync.Services import (
        RuleValidationError, create_rule, parse_rule_form,
    )
    from app import _is_valid_bank_category, db, pro_required

    @pro_required
    def _h():
        sid = session["store_id"]
        try:
            fields = parse_rule_form(
                db.session, request.form, sid,
                _is_valid_bank_category,
            )
        except RuleValidationError as e:
            flash(str(e), "error")
            return redirect(url_for("bank_redirects.bank_rules"))
        create_rule(db.session, sid, fields)
        db.session.commit()
        flash("Rule created.", "success")
        return redirect(url_for("bank_redirects.bank_rules"))

    return _h()


@bp.route("/bank/rules/<int:rule_id>/edit", methods=["POST"])
def bank_rule_edit(rule_id: int):
    """Update a BankRule. Cross-store rule_id 404s."""
    from api.Modules.BankSync.Services import (
        RuleNotFoundError, RuleValidationError, parse_rule_form,
        update_rule,
    )
    from app import _is_valid_bank_category, db, pro_required

    @pro_required
    def _h():
        sid = session["store_id"]
        try:
            fields = parse_rule_form(
                db.session, request.form, sid,
                _is_valid_bank_category,
            )
        except RuleValidationError as e:
            flash(str(e), "error")
            return redirect(url_for("bank_redirects.bank_rules"))
        try:
            update_rule(db.session, rule_id, sid, fields)
        except RuleNotFoundError:
            abort(404)
        db.session.commit()
        flash("Rule updated.", "success")
        return redirect(url_for("bank_redirects.bank_rules"))

    return _h()


@bp.route("/bank/rules/<int:rule_id>/toggle", methods=["POST"])
def bank_rule_toggle(rule_id: int):
    from api.Modules.BankSync.Services import (
        RuleNotFoundError, toggle_rule,
    )
    from app import db, pro_required

    @pro_required
    def _h():
        sid = session["store_id"]
        try:
            rule = toggle_rule(db.session, rule_id, sid)
        except RuleNotFoundError:
            abort(404)
        db.session.commit()
        flash(
            f"Rule {'enabled' if rule.enabled else 'disabled'}.",
            "success",
        )
        return redirect(url_for("bank_redirects.bank_rules"))

    return _h()


@bp.route("/bank/rules/<int:rule_id>/delete", methods=["POST"])
def bank_rule_delete(rule_id: int):
    from api.Modules.BankSync.Services import (
        RuleNotFoundError, delete_rule,
    )
    from app import db, pro_required

    @pro_required
    def _h():
        sid = session["store_id"]
        try:
            delete_rule(db.session, rule_id, sid)
        except RuleNotFoundError:
            abort(404)
        db.session.commit()
        flash("Rule deleted.", "success")
        return redirect(url_for("bank_redirects.bank_rules"))

    return _h()


@bp.route("/bank/stripe/nickname/<int:acct_id>", methods=["POST"])
def bank_stripe_set_nickname(acct_id: int):
    """Set or clear the operator-defined nickname on a connected bank
    account. Empty input reverts to the ••<last4> label."""
    from app import StripeBankAccount, db, pro_required

    @pro_required
    def _h():
        sid = session["store_id"]
        acct = StripeBankAccount.query.filter_by(
            id=acct_id, store_id=sid,
        ).first_or_404()
        nickname = (request.form.get("nickname") or "").strip()[:60]
        acct.nickname = nickname
        db.session.commit()
        flash(
            ("Nickname saved." if nickname else "Nickname cleared."),
            "success",
        )
        return redirect(url_for("bank_redirects.bank"))

    return _h()


@bp.route("/bank/stripe/disconnect/<int:acct_id>", methods=["POST"])
def bank_stripe_disconnect(acct_id: int):
    """Disconnect a single Stripe FC account. We both mark it
    disabled locally and tell Stripe to revoke, so the account stops
    counting toward the per-account billing line as well."""
    from app import (
        StripeBankAccount, app as flask_app, db, pro_required, stripe,
        stripe_is_configured,
    )

    @pro_required
    def _h():
        sid = session["store_id"]
        row = StripeBankAccount.query.filter_by(
            id=acct_id, store_id=sid,
        ).first_or_404()
        try:
            if stripe_is_configured():
                stripe.financial_connections.Account.disconnect(
                    row.stripe_account_id,
                )
        except stripe.error.StripeError as e:
            flask_app.logger.warning(
                f"FC disconnect API call failed (continuing locally): "
                f"{e}",
            )
        row.enabled = False
        row.disconnected_at = datetime.utcnow()
        db.session.commit()
        flash("Bank account disconnected.", "success")
        return redirect(url_for("bank_redirects.bank"))

    return _h()
