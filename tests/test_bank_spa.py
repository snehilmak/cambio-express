"""Bank SPA migration contract tests.

The /bank accounts landing and /bank/rules CRUD page both 301 to
React. The SPA reads /api/v2/bank/{accounts,transactions,rules}
and writes via /api/v2/bank/rules + the legacy Flask form-POST
endpoints (refresh, sync, nickname, disconnect, FC connect) which
each 302 back to /bank → 301 → /app/bank.

Two Jinja templates retired (bank.html, bank_rules.html).
"""


def _admin_session_login(client, store_id, plan="pro"):
    from app import User, Store, db
    with client.application.app_context():
        u = User.query.filter_by(store_id=store_id, role="admin").first()
        uid = u.id
        s = db.session.get(Store, store_id)
        s.plan = plan
        s.billing_cycle = "monthly"
        db.session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "admin"
        sess["store_id"] = store_id


def test_bank_redirects_to_spa(client, test_store_id):
    _admin_session_login(client, test_store_id)
    resp = client.get("/bank", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/bank"


def test_bank_rules_redirects_to_spa(client, test_store_id):
    _admin_session_login(client, test_store_id)
    resp = client.get("/bank/rules", follow_redirects=False)
    assert resp.status_code == 301
    assert resp.headers["Location"] == "/app/bank/rules"


def test_bank_redirect_preserves_paywall_for_basic_plan(client, test_store_id):
    """A Basic-plan store still hits the @pro_required gate — the
    301 to /app/bank only fires after the paywall check passes."""
    _admin_session_login(client, test_store_id, plan="basic")
    resp = client.get("/bank", follow_redirects=False)
    assert resp.status_code == 302
    assert "/subscribe" in resp.headers["Location"]
