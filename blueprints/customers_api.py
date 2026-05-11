"""Customer-autocomplete JSON API.

Extracted from ``app.py`` as part of the D2 Blueprint split. Two
JSON endpoints powering the transfer-form autocomplete UI:

  GET /api/customers/search
      sender-field autocomplete. Returns
      ``{matches: [...], suggestions: [...]}`` — substring matches
      plus difflib-based fuzzy near-misses to catch typos before the
      cashier creates a duplicate Customer.

  GET /api/customers/<int:cid>/recent-recipients
      last N distinct recipients this customer has sent to. Powers
      the "recent recipients" chip row above the recipient_name
      input on the transfer form.

Both delegate to
``api.Modules.Customers.Services.{search,list_recent_recipients}``.
The Flask handlers are thin glue — auth check via session
``store_id``, JSON envelope, store-name decoration on cross-umbrella
hits.

These are pure JSON endpoints reached by the SPA via literal path
fetches; no ``url_for("api_customers_search")`` callers exist in
the codebase (verified by grep). Endpoint-name namespacing is
silent — nothing breaks if the endpoint moves from
``api_customers_search`` to ``customers_api.api_customers_search``.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request, session


bp = Blueprint("customers_api", __name__)


@bp.route("/api/customers/search")
def api_customers_search():
    """Autocomplete endpoint for the sender field on the transfer
    form.

    Scope: all stores under the same owner umbrella as the current
    session's store. Standalone stores (no owner links) see only
    their own customers. Unrelated stores can never see each
    other's customers.

    Returns a JSON envelope:
        { "matches":     [ ...exact substring matches... ],
          "suggestions": [ ...fuzzy near-misses, when query is
                            long enough... ] }

    The suggestions list is the dedup-prevention hook: when a
    cashier types "Maria Gonzales" but the record is
    "Maria Gonzalez", a substring search returns nothing — the
    suggestion list catches it via difflib's SequenceMatcher and
    lets the cashier pick the existing row instead of creating a
    duplicate. Suggestions are populated only when the query is
    >= 4 chars and there's room (matches < 5) so the regular case
    stays fast."""
    from app import Store, db, login_required
    from api.Modules.Customers.Services import search as _customers_search

    @login_required
    def _h():
        sid = session.get("store_id")
        if not sid:
            return jsonify({"matches": [], "suggestions": []})
        q_text = request.args.get("q", "").strip()
        matches, suggestions = _customers_search(db.session, sid, q_text)
        # Precompute the home-store name for rows not owned by the
        # current store so the UI can label "from Store A" on
        # cross-store matches.
        other_store_ids = {
            c.store_id for c in (list(matches) + list(suggestions))
            if c.store_id != sid
        }
        home_names = (
            {s.id: s.name for s in
             Store.query.filter(Store.id.in_(other_store_ids)).all()}
            if other_store_ids else {}
        )
        return jsonify({
            "matches": [
                c.to_dict(current_store_id=sid, home_names=home_names)
                for c in matches
            ],
            "suggestions": [
                c.to_dict(current_store_id=sid, home_names=home_names)
                for c in suggestions
            ],
        })

    return _h()


@bp.route("/api/customers/<int:cid>/recent-recipients")
def api_customer_recent_recipients(cid: int):
    """Last N distinct recipients this customer has sent to. Powers
    the "recent recipients" chip row above the recipient_name input
    on the transfer form.

    Scope, query, and result shape live in
    ``api.Modules.Customers.Services.list_recent_recipients``; this
    route is the Flask glue that authorises the request and
    serialises the result."""
    from app import db, login_required
    from api.Modules.Customers.Services import list_recent_recipients

    @login_required
    def _h():
        sid = session.get("store_id")
        if not sid:
            return jsonify([])
        rows = list_recent_recipients(db.session, cid, sid)
        return jsonify([r.to_dict() for r in rows])

    return _h()
