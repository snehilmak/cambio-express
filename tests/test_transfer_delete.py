"""Tests for POST /transfers/<tid>/delete.

Store admins can delete transfers; employees cannot. Deleting a transfer
removes its TransferAudit rows too (FK constraint), so the admin Activity
log for that specific transfer goes away with it — expected, since the
record it described is also gone.
"""
from datetime import date
from app import app as flask_app, db
from .conftest import make_employee_client


def _seed_transfer(sender="Jane Doe", send_amount=500.0, fee=5.0):
    """Local variant that also seeds one TransferAudit row — lets the
    delete test verify the audit-cascade side effect. The shared
    conftest seed_transfer only writes the transfer row."""
    from app import Store, User, Transfer, TransferAudit
    with flask_app.app_context():
        store = Store.query.filter_by(slug="test-store").first()
        user = User.query.filter_by(username="admin@test.com").first()
        t = Transfer(
            store_id=store.id, created_by=user.id,
            send_date=date.today(), company="Intermex",
            sender_name=sender, send_amount=send_amount, fee=fee,
            federal_tax=round(send_amount * 0.01, 2),
            commission=0.0, status="Sent",
        )
        db.session.add(t)
        db.session.flush()
        db.session.add(TransferAudit(
            store_id=store.id, transfer_id=t.id,
            user_id=user.id, action="created", summary="seeded",
        ))
        db.session.commit()
        return t.id


def _logged_in_employee_client():
    """Back-compat wrapper — existing tests want the employee to be at
    the test-store; the shared helper takes the store_id explicitly."""
    from app import Store
    with flask_app.app_context():
        sid = Store.query.filter_by(slug="test-store").first().id
    return make_employee_client(sid)


# ── Admin can delete ────────────────────────────────────────────

def test_admin_can_delete_transfer(logged_in_client):
    from app import Transfer
    tid = _seed_transfer()
    resp = logged_in_client.post(
        f"/transfers/{tid}/delete", follow_redirects=False)
    # Redirect to /transfers list after successful delete.
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/transfers")
    # Row is actually gone.
    with flask_app.app_context():
        assert db.session.get(Transfer, tid) is None


def test_delete_cascades_transfer_audit_rows(logged_in_client):
    from app import TransferAudit
    tid = _seed_transfer()
    with flask_app.app_context():
        assert TransferAudit.query.filter_by(transfer_id=tid).count() == 1
    logged_in_client.post(f"/transfers/{tid}/delete", follow_redirects=False)
    with flask_app.app_context():
        assert TransferAudit.query.filter_by(transfer_id=tid).count() == 0


# ── Employee is blocked ─────────────────────────────────────────

def test_employee_cannot_delete_transfer():
    """@admin_required must block role='employee'. Backend check is the
    real gate; the template just hides the button."""
    from app import Transfer
    tid = _seed_transfer()
    c = _logged_in_employee_client()
    resp = c.post(f"/transfers/{tid}/delete", follow_redirects=False)
    # admin_required redirects to /dashboard with a flash on reject.
    assert resp.status_code == 302
    assert "/dashboard" in resp.headers["Location"]
    # Transfer is still there.
    with flask_app.app_context():
        assert db.session.get(Transfer, tid) is not None


# ── Cross-store isolation ──────────────────────────────────────

def test_admin_cannot_delete_other_stores_transfer(logged_in_client):
    """Delete route scopes by session store_id — an admin signed into
    store A can't reach store B's transfers even if they guess the id."""
    from app import Store, User, Transfer
    with flask_app.app_context():
        other = Store(name="Other", slug="other", email="o@t.com", plan="trial")
        db.session.add(other)
        db.session.flush()
        owner = User(store_id=other.id, username="owner@o.com",
                     full_name="O", role="admin")
        owner.set_password("x")
        db.session.add(owner)
        db.session.flush()
        stranger = Transfer(
            store_id=other.id, created_by=owner.id,
            send_date=date.today(), company="Intermex",
            sender_name="Stranger", send_amount=100.0, fee=2.0,
            federal_tax=1.0, commission=0.0, status="Sent",
        )
        db.session.add(stranger)
        db.session.commit()
        sid = stranger.id
    # logged_in_client is signed into test-store, not "other".
    resp = logged_in_client.post(f"/transfers/{sid}/delete")
    assert resp.status_code == 404
    with flask_app.app_context():
        assert db.session.get(Transfer, sid) is not None


# ── Button rendering ───────────────────────────────────────────

def test_delete_button_shown_to_admin(logged_in_client):
    tid = _seed_transfer()
    resp = logged_in_client.get(f"/transfers/{tid}/edit")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Danger Zone" in html
    assert f"/transfers/{tid}/delete" in html


def test_delete_button_hidden_from_employee():
    """Template guards on user.role == 'admin'. We verify the server never
    emits the Danger Zone card for an employee session."""
    tid = _seed_transfer()
    c = _logged_in_employee_client()
    resp = c.get(f"/transfers/{tid}/edit")
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Danger Zone" not in html
    assert f"/transfers/{tid}/delete" not in html
