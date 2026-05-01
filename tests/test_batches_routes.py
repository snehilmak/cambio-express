"""Route-level tests for the ACH batches CRUD surface.

`test_ach_invariants.py` covers the money math (federal_tax flow,
total_collected) but never hits a route. These tests guard the four
HTTP entry points: list, new, edit, and per-batch transfer detail.

The model invariants are:
  - ACHBatch.store_id is the auth boundary; cross-store reads 404.
  - (store_id, batch_ref) is unique — second insert with the same
    ref under the same store fails (caller responsibility).
"""
from datetime import date, timedelta

from tests.conftest import make_employee_client


def _seed_batch(app, store_id, *, batch_ref="B-0001", company="Intermex",
                ach_date=None, amount=1000.0):
    from app import ACHBatch, db
    with app.app_context():
        b = ACHBatch(
            store_id=store_id, ach_date=ach_date or date.today(),
            company=company, batch_ref=batch_ref,
            ach_amount=amount, status="Pending",
        )
        db.session.add(b); db.session.commit()
        return b.id


# ── Auth gate ────────────────────────────────────────────────


def test_batches_requires_login(client):
    resp = client.get("/batches", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_batches_employee_blocked(client, test_store_id):
    """Employees aren't admins — admin_required bounces them off."""
    c = make_employee_client(test_store_id)
    resp = c.get("/batches", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" not in resp.headers["Location"]  # bounced to dashboard, not login


# ── List ─────────────────────────────────────────────────────


def test_batches_list_renders(logged_in_client):
    resp = logged_in_client.get("/batches")
    assert resp.status_code == 200
    assert b"ACH" in resp.data or b"Batch" in resp.data


def test_batches_list_scoped_to_store(logged_in_client, test_store_id):
    """A batch under a different store must not leak into this store's list."""
    from app import ACHBatch, Store, db
    app = logged_in_client.application
    with app.app_context():
        other = Store(name="Other", slug="other-shop", plan="trial")
        db.session.add(other); db.session.commit()
        other_id = other.id
    _seed_batch(app, test_store_id, batch_ref="MINE-1")
    _seed_batch(app, other_id,      batch_ref="THEIRS-1")
    resp = logged_in_client.get("/batches")
    body = resp.data.decode()
    assert "MINE-1" in body
    assert "THEIRS-1" not in body


# ── Create (GET form + POST round-trip) ──────────────────────


def test_new_batch_get_renders_form(logged_in_client):
    resp = logged_in_client.get("/batches/new")
    assert resp.status_code == 200
    assert b"ach_date" in resp.data or b"date" in resp.data


def test_new_batch_post_creates_row(logged_in_client, test_store_id):
    from app import ACHBatch
    resp = logged_in_client.post("/batches/new", data={
        "ach_date":   date.today().isoformat(),
        "company":    "Maxi",
        "batch_ref":  "BX-NEW-1",
        "ach_amount": "1234.56",
        "status":     "Pending",
        "transfer_dates": "2026-04-29,2026-04-30",
        "notes":      "test note",
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/batches")
    with logged_in_client.application.app_context():
        b = ACHBatch.query.filter_by(batch_ref="BX-NEW-1").first()
        assert b is not None
        assert b.store_id == test_store_id
        assert b.company == "Maxi"
        assert abs(b.ach_amount - 1234.56) < 0.001
        assert b.status == "Pending"
        assert b.notes == "test note"
        assert b.reconciled is False  # checkbox unchecked


def test_new_batch_reconciled_checkbox(logged_in_client):
    """The reconciled flag is set only when the form sends `on`."""
    from app import ACHBatch
    logged_in_client.post("/batches/new", data={
        "ach_date":   date.today().isoformat(),
        "company":    "Barri",
        "batch_ref":  "BX-CHK-1",
        "ach_amount": "500.00",
        "reconciled": "on",
    }, follow_redirects=False)
    with logged_in_client.application.app_context():
        b = ACHBatch.query.filter_by(batch_ref="BX-CHK-1").first()
        assert b.reconciled is True


# ── Edit (GET form + POST round-trip) ────────────────────────


def test_edit_batch_get_renders_with_existing_values(logged_in_client, test_store_id):
    bid = _seed_batch(logged_in_client.application, test_store_id,
                      batch_ref="EDIT-1", company="Intermex", amount=999.99)
    resp = logged_in_client.get(f"/batches/{bid}/edit")
    assert resp.status_code == 200
    assert b"EDIT-1" in resp.data
    assert b"999.99" in resp.data


def test_edit_batch_post_updates_row(logged_in_client, test_store_id):
    from app import ACHBatch, db
    bid = _seed_batch(logged_in_client.application, test_store_id,
                      batch_ref="EDIT-2", company="Intermex", amount=100.0)
    resp = logged_in_client.post(f"/batches/{bid}/edit", data={
        "ach_date":   "2026-05-01",
        "company":    "Maxi",
        "batch_ref":  "EDIT-2",
        "ach_amount": "777.77",
        "status":     "Cleared",
        "reconciled": "on",
        "notes":      "updated",
    }, follow_redirects=False)
    assert resp.status_code == 302
    with logged_in_client.application.app_context():
        b = db.session.get(ACHBatch, bid)
        assert b.company == "Maxi"
        assert abs(b.ach_amount - 777.77) < 0.001
        assert b.status == "Cleared"
        assert b.reconciled is True
        assert b.notes == "updated"
        assert b.ach_date == date(2026, 5, 1)


def test_edit_batch_cross_store_404(logged_in_client, test_store_id):
    """An admin can't edit another store's batch even by guessing the id."""
    from app import Store, db
    app = logged_in_client.application
    with app.app_context():
        other = Store(name="Other", slug="other-shop-2", plan="trial")
        db.session.add(other); db.session.commit()
        other_id = other.id
    other_bid = _seed_batch(app, other_id, batch_ref="THEIRS-2")
    resp = logged_in_client.get(f"/batches/{other_bid}/edit")
    assert resp.status_code == 404


# ── Per-batch transfer detail ────────────────────────────────


def test_batch_transfers_renders(logged_in_client, test_store_id):
    bid = _seed_batch(logged_in_client.application, test_store_id,
                      batch_ref="DET-1")
    resp = logged_in_client.get(f"/batches/{bid}/transfers")
    assert resp.status_code == 200
    assert b"DET-1" in resp.data


def test_batch_transfers_cross_store_404(logged_in_client, test_store_id):
    from app import Store, db
    app = logged_in_client.application
    with app.app_context():
        other = Store(name="Other", slug="other-shop-3", plan="trial")
        db.session.add(other); db.session.commit()
        other_id = other.id
    other_bid = _seed_batch(app, other_id, batch_ref="THEIRS-3")
    resp = logged_in_client.get(f"/batches/{other_bid}/transfers")
    assert resp.status_code == 404
