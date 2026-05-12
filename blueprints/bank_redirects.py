"""Bank-sync SPA-cutover redirects.

Extracted from ``app.py`` as part of the D2 Blueprint split. Three
pure 301 redirects pointing at the React Bank pages:

  GET /bank                  301 → /app/bank
                              (Stripe FC accounts landing)
  GET /bank/transactions     301 → /app/bank-transactions
                              (transaction ledger; preserves query
                               string minus `partial=1`)
  GET /bank/rules            301 → /app/bank/rules
                              (auto-categorize rules CRUD)

The mutating sibling routes
(/bank/stripe/{connect,return,refresh,sync-transactions,
nickname/<id>,disconnect/<id>},
/bank/transactions/<id>/{categorize,uncategorize,move-date},
/bank/rules/{new,<id>/{edit,toggle,delete}}) stay in app.py for
now — those are real form-POST handlers that still drive the live
mutation surface and 302 back to /bank → which 301s to /app/bank
via this blueprint.

Endpoint-name churn:
  url_for("bank")              → url_for("bank_redirects.bank")
  url_for("bank_transactions") → url_for("bank_redirects.bank_transactions")
  url_for("bank_rules")        → url_for("bank_redirects.bank_rules")
"""
from __future__ import annotations

from flask import Blueprint, redirect, request


bp = Blueprint("bank_redirects", __name__)


@bp.route("/bank")
def bank():
    """301 → /app/bank. The SPA reads
    /api/v2/bank/{accounts,transactions} and drives the Stripe
    Financial Connections modal via dynamically-loaded Stripe.js.
    Legacy form-POST endpoints
    (/bank/stripe/{refresh,sync-transactions,nickname/<id>,
    disconnect/<id>}) stay live and the SPA submits forms to them;
    they 302 back to /bank → 301 → /app/bank."""
    from app import pro_required
    return pro_required(lambda: redirect("/app/bank", code=301))()


@bp.route("/bank/transactions")
def bank_transactions():
    """301 → /app/bank-transactions. SPA reads
    /api/v2/bank-sync/transactions (paginated + filtered) and does
    its own debounced live-search. Query string (account / date /
    q / page) preserved minus `partial=1`, the legacy AJAX-only
    marker the SPA never sends."""
    from app import pro_required

    @pro_required
    def _h():
        qs = (
            request.query_string.decode("latin-1")
            if request.query_string else ""
        )
        if qs:
            qs = "&".join(p for p in qs.split("&") if p != "partial=1")
        target = "/app/bank-transactions" + (f"?{qs}" if qs else "")
        return redirect(target, code=301)

    return _h()


@bp.route("/bank/rules")
def bank_rules():
    """301 → /app/bank/rules. Rules CRUD moved to React; the SPA
    reads/writes via /api/v2/bank/rules. Legacy form-POST handlers
    (new / edit / toggle / delete) stay live as fallback callers
    and 302 back to /bank/rules → 301 → /app."""
    from app import pro_required
    return pro_required(lambda: redirect("/app/bank/rules", code=301))()
