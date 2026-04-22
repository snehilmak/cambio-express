"""Tests for superadmin impersonation + the new safe-exit flow.

Before this fix, /superadmin/impersonate REPLACED the session with the
target store's admin and left no trace of the original superadmin. The
only way back was a full logout + re-login, actions during impersonation
showed in the audit log as the store admin (not the superadmin), and
the superadmin could silently forget they were impersonating.

Now:
  - The real superadmin's User.id is stashed in session['impersonator_user_id'].
  - A persistent banner renders on every page while impersonating.
  - POST /superadmin/stop-impersonation restores the session.
  - Audit log records both impersonate_start and impersonate_end.
"""
from datetime import datetime, timedelta
from app import app as flask_app, db


def _logged_in_superadmin():
    """Fresh client authenticated as the seeded superadmin (no 2FA)."""
    from app import User
    c = flask_app.test_client()
    with flask_app.app_context():
        sa = User.query.filter_by(username="superadmin", store_id=None).first()
        uid = sa.id
    with c.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "superadmin"
    return c, uid


# ── Start impersonation stashes the real identity ───────────────

def test_impersonate_stashes_superadmin_id(test_store_id):
    c, sa_id = _logged_in_superadmin()
    resp = c.get(f"/superadmin/impersonate/{test_store_id}", follow_redirects=False)
    assert resp.status_code == 302
    with c.session_transaction() as sess:
        # Active session is now the store's admin…
        assert sess["role"] == "admin"
        assert sess["store_id"] == test_store_id
        # …but the real superadmin id is preserved so we can get back.
        assert sess["impersonator_user_id"] == sa_id
        assert sess["user_id"] != sa_id


def test_impersonate_records_audit_start():
    """impersonate_start row lands in the audit log with the target
    store's id so the trail is traceable."""
    from app import SuperadminAuditLog as AuditLog
    c, _ = _logged_in_superadmin()
    from app import Store
    with flask_app.app_context():
        sid = Store.query.filter_by(slug="test-store").first().id
    c.get(f"/superadmin/impersonate/{sid}")
    with flask_app.app_context():
        rows = AuditLog.query.filter_by(action="impersonate_start").all()
        assert len(rows) == 1
        assert rows[0].target_type == "store"
        # target_id stored as string on SuperadminAuditLog.
        assert str(rows[0].target_id) == str(sid)


# ── Stop impersonation restores the real superadmin session ────

def test_stop_impersonation_restores_superadmin():
    c, sa_id = _logged_in_superadmin()
    from app import Store
    with flask_app.app_context():
        sid = Store.query.filter_by(slug="test-store").first().id
    c.get(f"/superadmin/impersonate/{sid}")
    # Back at superadmin chair.
    resp = c.post("/superadmin/stop-impersonation", follow_redirects=False)
    assert resp.status_code == 302
    with c.session_transaction() as sess:
        assert sess["user_id"] == sa_id
        assert sess["role"] == "superadmin"
        assert sess.get("store_id") is None
        assert "impersonator_user_id" not in sess


def test_stop_impersonation_records_audit_end():
    from app import SuperadminAuditLog as AuditLog, Store
    c, _ = _logged_in_superadmin()
    with flask_app.app_context():
        sid = Store.query.filter_by(slug="test-store").first().id
    c.get(f"/superadmin/impersonate/{sid}")
    c.post("/superadmin/stop-impersonation")
    with flask_app.app_context():
        assert AuditLog.query.filter_by(action="impersonate_end").count() == 1


# ── Security: bad / missing / tampered impersonator_user_id ────

def test_stop_impersonation_without_active_impersonation_redirects():
    """A store admin (never impersonated) calling stop-impersonation
    shouldn't get elevated. Expect a redirect to dashboard with a
    flash, not a 500 and not an escalation."""
    from app import User, Store
    c = flask_app.test_client()
    with flask_app.app_context():
        admin = User.query.filter_by(username="admin@test.com").first()
        uid, sid = admin.id, admin.store_id
    with c.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "admin"
        sess["store_id"] = sid
    resp = c.post("/superadmin/stop-impersonation", follow_redirects=False)
    assert resp.status_code == 302
    # Session is unchanged — role is still admin, no elevation.
    with c.session_transaction() as sess:
        assert sess["role"] == "admin"
        assert "impersonator_user_id" not in sess


def test_stop_impersonation_with_tampered_impersonator_id_clears_session():
    """If an attacker forges session['impersonator_user_id'] to point
    at a non-superadmin (or a deactivated superadmin, or a deleted
    user), stop-impersonation must NOT elevate — it clears the
    session and sends them to /login."""
    from app import User
    c = flask_app.test_client()
    # Put an admin session together + tamper the impersonator id to
    # point at another admin user (not a superadmin).
    with flask_app.app_context():
        target_admin = User.query.filter_by(username="admin@test.com").first()
        tampered_id = target_admin.id
    with c.session_transaction() as sess:
        sess["user_id"] = tampered_id
        sess["role"] = "admin"
        sess["impersonator_user_id"] = tampered_id   # <- not a superadmin
    resp = c.post("/superadmin/stop-impersonation", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
    with c.session_transaction() as sess:
        # session.clear() wipes everything, including the tampered id.
        assert "user_id" not in sess
        assert "impersonator_user_id" not in sess


# ── UX banner renders only while impersonating ─────────────────

def test_banner_shows_while_impersonating():
    from app import Store
    c, _ = _logged_in_superadmin()
    with flask_app.app_context():
        store = Store.query.filter_by(slug="test-store").first()
        sid = store.id
        name = store.name
    c.get(f"/superadmin/impersonate/{sid}")
    resp = c.get("/dashboard")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Impersonating" in html
    assert name in html
    assert "/superadmin/stop-impersonation" in html


def test_banner_hidden_for_normal_admin(logged_in_client):
    resp = logged_in_client.get("/dashboard")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Impersonating" not in html
    assert "/superadmin/stop-impersonation" not in html


def test_banner_hidden_for_plain_superadmin():
    c, _ = _logged_in_superadmin()
    resp = c.get("/dashboard")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Impersonating" not in html
