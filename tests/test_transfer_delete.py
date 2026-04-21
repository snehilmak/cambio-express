"""Tests for POST /transfers/<tid>/delete.

Store admins can delete transfers; employees cannot. Deleting a transfer
removes its TransferAudit rows too (FK constraint), so the admin Activity
log for that specific transfer goes away with it — expected, since the
record it described is also gone.
"""
from datetime import date
from app import app as flask_app, db


def _seed_transfer(sender="Jane Doe", send_amount=500.0, fee=5.0):
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
        # Seed one audit row so we can verify cascade behavior.
        db.session.add(TransferAudit(
            store_id=store.id, transfer_id=t.id,
            user_id=user.id, action="created", summary="seeded",
        ))
        db.session.commit()
        return t.id


def _logged_in_employee_client():
    """A client authenticated as a store employee (role='employee'),
    which is the role @admin_required is supposed to reject."""
    from app import User, Store
    c = flask_app.test_client()
    with flask_app.app_context():
        store = Store.query.filter_by(slug="test-store").first()
        emp = User(store_id=store.id, username="emp@test.com",
                   full_name="Employee", role="employee")
        emp.set_password("testpass123!")
        db.session.add(emp)
        db.session.commit()
        uid, sid = emp.id, store.id
    with c.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "employee"
        sess["store_id"] = sid
    return c


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
