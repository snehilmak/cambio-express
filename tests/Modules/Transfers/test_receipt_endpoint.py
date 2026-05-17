"""HTTP integration tests for the printable transfer-receipt
endpoint: ``GET /api/v2/transfers/{id}/receipt``.

Returns ``{store, transfer}`` so the SPA's
``/app/transfers/{id}/receipt`` route can render the printable
page from a single fetch. Tenancy is enforced via the same
``?store_ids=`` umbrella param the rest of the Transfers routes
take.
"""
from datetime import date

from tests._app import db, db_session


def _login_admin(client, store_id):
    resp = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


def _seed_transfer(store_id, **overrides):
    """Drop a minimal valid Transfer row + the StoreEmployee FK
    it requires. Returns the transfer id."""
    from api.Modules.Transfers.Models import Transfer
    from api.Modules.Tenancy.Models import StoreEmployee
    emp = (
        db.session.query(StoreEmployee)
          .filter_by(store_id=store_id).first()
    )
    if emp is None:
        emp = StoreEmployee(
            store_id=store_id, name="Receipt cashier", is_active=True,
        )
        db.session.add(emp); db.session.flush()
    defaults = dict(
        store_id=store_id,
        send_date=date.today(),
        company="Intermex",
        service_type="Money Transfer",
        sender_name="Maria Lopez",
        sender_phone="5550000000",
        sender_phone_country="+1",
        sender_address="123 Main St",
        send_amount=100.0,
        fee=5.0,
        federal_tax=1.0,
        country="Mexico",
        recipient_name="Juan Garcia",
        recipient_phone="5559990000",
        confirm_number="ABC-123",
        status="Sent",
        employee_id=emp.id,
    )
    defaults.update(overrides)
    t = Transfer(**defaults)
    db.session.add(t); db.session.commit()
    return t.id


# ── Auth gating ─────────────────────────────────────────────


def test_receipt_requires_store_ids_param(client, test_store_id):
    with db_session():
        tid = _seed_transfer(test_store_id)
    token = _login_admin(client, test_store_id)
    # No ``?store_ids=`` → Pydantic rejects with 422.
    resp = client.get(
        f"/api/v2/transfers/{tid}/receipt",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ── Happy path ──────────────────────────────────────────────


def test_receipt_returns_transfer_and_store(client, test_store_id):
    with db_session():
        tid = _seed_transfer(test_store_id)
    token = _login_admin(client, test_store_id)
    resp = client.get(
        f"/api/v2/transfers/{tid}/receipt"
        f"?store_ids={test_store_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert set(body.keys()) == {"store", "transfer"}
    assert body["transfer"]["id"] == tid
    assert body["transfer"]["sender_name"] == "Maria Lopez"
    assert body["transfer"]["recipient_name"] == "Juan Garcia"
    assert body["transfer"]["country"] == "Mexico"
    assert body["transfer"]["send_amount"] == 100.0
    assert body["transfer"]["fee"] == 5.0
    assert body["transfer"]["federal_tax"] == 1.0
    # 100 + 5 + 1 — the receipt prints this as the headline.
    assert body["transfer"]["total_collected"] == 106.0
    # Store header carries the seeded store's data.
    assert body["store"]["name"] == "Test Store"


def test_receipt_carries_store_customization_fields(
    client, test_store_id,
):
    """receipt_logo_url / receipt_footer / receipt_tax_id round-
    trip from Store row → API → response."""
    from api.Modules.Tenancy.Models import Store
    with db_session():
        s = db.session.get(Store, test_store_id)
        s.receipt_logo_url = "https://example.com/logo.png"
        s.receipt_footer = "Thank you for your business!"
        s.receipt_tax_id = "EIN 12-3456789"
        db.session.commit()
        tid = _seed_transfer(test_store_id)
    token = _login_admin(client, test_store_id)
    body = client.get(
        f"/api/v2/transfers/{tid}/receipt"
        f"?store_ids={test_store_id}",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["store"]["receipt_logo_url"] == (
        "https://example.com/logo.png"
    )
    assert body["store"]["receipt_footer"] == "Thank you for your business!"
    assert body["store"]["receipt_tax_id"] == "EIN 12-3456789"


def test_receipt_carries_business_legal_fields(client, test_store_id):
    """legal_name / ein / legal_address surface on the receipt
    payload so the SPA print view renders the registered-entity
    block. Empty strings stay empty (the renderer suppresses the
    line)."""
    from api.Modules.Tenancy.Models import Store
    with db_session():
        s = db.session.get(Store, test_store_id)
        s.legal_name    = "Test Remittance LLC"
        s.ein           = "12-3456789"
        s.legal_address = "100 Main St, Houston, TX 77002"
        db.session.commit()
        tid = _seed_transfer(test_store_id)
    token = _login_admin(client, test_store_id)
    body = client.get(
        f"/api/v2/transfers/{tid}/receipt"
        f"?store_ids={test_store_id}",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["store"]["legal_name"] == "Test Remittance LLC"
    assert body["store"]["ein"] == "12-3456789"
    assert body["store"]["legal_address"] == (
        "100 Main St, Houston, TX 77002"
    )


def test_receipt_defaults_empty_strings_when_not_customized(
    client, test_store_id,
):
    """A store that never set the receipt_* fields gets empty
    strings in the response, not nulls. The SPA renders a
    fallback layout when these are empty."""
    with db_session():
        tid = _seed_transfer(test_store_id)
    token = _login_admin(client, test_store_id)
    body = client.get(
        f"/api/v2/transfers/{tid}/receipt"
        f"?store_ids={test_store_id}",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["store"]["receipt_logo_url"] == ""
    assert body["store"]["receipt_footer"] == ""
    assert body["store"]["receipt_tax_id"] == ""
    assert body["store"]["legal_name"] == ""
    assert body["store"]["ein"] == ""
    assert body["store"]["legal_address"] == ""


# ── Tenancy ─────────────────────────────────────────────────


def test_receipt_404_when_transfer_outside_store_ids(
    client, test_store_id,
):
    """The umbrella scope is enforced — a transfer at an unrelated
    store 404s rather than leaking that the id exists."""
    from api.Modules.Tenancy.Models import Store
    with db_session():
        unrelated = Store(
            name="Unrelated Receipt", slug="unrelated-receipt",
            email="unrel@x.com", plan="basic",
        )
        db.session.add(unrelated); db.session.flush()
        tid = _seed_transfer(unrelated.id)
    token = _login_admin(client, test_store_id)
    resp = client.get(
        f"/api/v2/transfers/{tid}/receipt"
        f"?store_ids={test_store_id}",  # NOT including ``unrelated``
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_receipt_404_when_transfer_missing(client, test_store_id):
    token = _login_admin(client, test_store_id)
    resp = client.get(
        f"/api/v2/transfers/9999999/receipt"
        f"?store_ids={test_store_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ── Route ordering ──────────────────────────────────────────


def test_receipt_route_does_not_shadow_transfer_detail(
    client, test_store_id,
):
    """``/receipt`` is a two-segment path; the single-segment
    ``/{transfer_id}`` route must still resolve to the regular
    transfer-detail endpoint, not get intercepted by the receipt
    matcher. Pins the route-ordering choice in the controller."""
    with db_session():
        tid = _seed_transfer(test_store_id)
    token = _login_admin(client, test_store_id)
    resp = client.get(
        f"/api/v2/transfers/{tid}"
        f"?store_ids={test_store_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    # Regular transfer response shape is ``{transfer: {...}}``,
    # NOT ``{store, transfer}``.
    assert "transfer" in body
    assert "store" not in body
