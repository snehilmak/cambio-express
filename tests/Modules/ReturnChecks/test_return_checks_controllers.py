"""HTTP integration tests for the ReturnChecks Controllers."""
from datetime import date
from tests._app import db, db_session


def _login(client, store_id):
    resp = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


def _seed_rc(store_id, *, customer_name="Bouncer Co",
              amount=500.0, bounced_on_=None, status="pending"):
    from api.Modules.ReturnChecks.Models import ReturnCheck
    from tests._app import db
    r = ReturnCheck(
        store_id=store_id,
        bounced_on=bounced_on_ or date.today(),
        customer_name=customer_name,
        check_number="123",
        payer_bank="Bank A",
        amount=amount,
        status=status,
    )
    db.session.add(r); db.session.commit()
    return r.id


# ── GET /return-checks ──────────────────────────────────────


def test_list_returns_envelope(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/return-checks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert "rows" in resp.get_json()


def test_list_filters_by_status(client, test_store_id):
    with db_session():
        _seed_rc(test_store_id, customer_name="Pending Co", status="pending")
        rc_loss = _seed_rc(test_store_id, customer_name="Loss Co", status="loss")
        _ = rc_loss
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/return-checks?status=pending",
        headers={"Authorization": f"Bearer {token}"},
    )
    rows = resp.get_json()["rows"]
    statuses = {r["status"] for r in rows}
    assert statuses == {"pending"}


# ── POST /return-checks ─────────────────────────────────────


def test_create_round_trip(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/return-checks",
        json={
            "bounced_on":    "2026-04-15",
            "customer_name": "Acme Corp",
            "company_name":  "Acme LLC",
            "check_number":  "12345",
            "payer_bank":    "Wells Fargo",
            "amount":        750.0,
            "return_check_fee": 25.0,
            "notes":         "second bounce",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    rc = resp.get_json()["return_check"]
    assert rc["customer_name"] == "Acme Corp"
    assert rc["company_name"] == "Acme LLC"
    assert rc["amount"] == 750.0
    assert rc["return_check_fee"] == 25.0
    assert rc["status"] == "pending"


def test_create_rejects_zero_amount(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/return-checks",
        json={
            "bounced_on":    "2026-04-15",
            "customer_name": "Bad Amount",
            "amount":        0.0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_create_requires_admin_role(client):
    """Cashier role can't create return checks."""
    from api.Modules.Tenancy.Models import User
    from tests._app import db
    with db_session():
        u = User(
            store_id=None, username="emp_rc_test",
            role="employee", is_active=True,
        )
        u.set_password("emppass1234")
        db.session.add(u); db.session.commit()
    try:
        login = client.post(
            "/api/v2/auth/login",
            json={
                "username": "emp_rc_test",
                "password": "emppass1234",
                "store_id": None,
            },
        )
        token = login.get_json()["access_token"]
        resp = client.post(
            "/api/v2/return-checks",
            json={
                "bounced_on":    "2026-04-15",
                "customer_name": "X",
                "company_name":  "X Co",
                "amount":        100.0,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
    finally:
        with db_session():
            u2 = db.session.query(User).filter_by(
                username="emp_rc_test",
            ).first()
            if u2:
                db.session.delete(u2); db.session.commit()


# ── PUT /return-checks/{id} ─────────────────────────────────


def test_update_round_trip(client, test_store_id):
    with db_session():
        rid = _seed_rc(test_store_id, customer_name="Old Name")
    token = _login(client, test_store_id)
    resp = client.put(
        f"/api/v2/return-checks/{rid}",
        json={
            "bounced_on":    "2026-05-01",
            "customer_name": "New Name",
            "company_name":  "New Co",
            "check_number":  "99",
            "payer_bank":    "Bank B",
            "amount":        300.0,
            "notes":         "renamed",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    rc = resp.get_json()["return_check"]
    assert rc["customer_name"] == "New Name"
    assert rc["amount"] == 300.0


# ── Status transitions ──────────────────────────────────────


def test_mark_loss_round_trip(client, test_store_id):
    with db_session():
        rid = _seed_rc(test_store_id, status="pending")
    token = _login(client, test_store_id)
    resp = client.post(
        f"/api/v2/return-checks/{rid}/mark-loss",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    rc = resp.get_json()["return_check"]
    assert rc["status"] == "loss"
    assert rc["status_changed_on"] != ""


def test_mark_fraud_rejects_non_pending(client, test_store_id):
    with db_session():
        rid = _seed_rc(test_store_id, status="loss")
    token = _login(client, test_store_id)
    resp = client.post(
        f"/api/v2/return-checks/{rid}/mark-fraud",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


def test_reopen_round_trip(client, test_store_id):
    from api.Modules.ReturnChecks.Models import ReturnCheck
    from tests._app import db
    with db_session():
        rid = _seed_rc(test_store_id, status="loss")
        rc = db.session.get(ReturnCheck, rid)
        rc.status_changed_on = date.today()
        db.session.commit()
    token = _login(client, test_store_id)
    resp = client.post(
        f"/api/v2/return-checks/{rid}/reopen",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    rc = resp.get_json()["return_check"]
    assert rc["status"] == "pending"
    assert rc["status_changed_on"] == ""


def test_reopen_rejects_pending(client, test_store_id):
    with db_session():
        rid = _seed_rc(test_store_id, status="pending")
    token = _login(client, test_store_id)
    resp = client.post(
        f"/api/v2/return-checks/{rid}/reopen",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


def test_reopen_rejects_recovered(client, test_store_id):
    """A fully-paid (recovered) check can't be reopened — recovery is
    payment-driven, so the undo path is removing a payment, not
    reopening (which would strand it with no remaining balance)."""
    with db_session():
        rid = _seed_rc(test_store_id, status="recovered")
    token = _login(client, test_store_id)
    resp = client.post(
        f"/api/v2/return-checks/{rid}/reopen",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


# ── GET /return-checks/{id}/payments ────────────────────────


def test_payments_returns_envelope(client, test_store_id):
    with db_session():
        rid = _seed_rc(test_store_id)
    token = _login(client, test_store_id)
    resp = client.get(
        f"/api/v2/return-checks/{rid}/payments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["payments"] == []


def test_payments_404_when_missing(client, test_store_id):
    token = _login(client, test_store_id)
    resp = client.get(
        "/api/v2/return-checks/9999/payments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ── Auth ────────────────────────────────────────────────────


# ── POST /return-checks/{id}/payments ───────────────────────


def test_record_payment_creates_row_and_daily_line_item(
    client, test_store_id,
):
    """Recording a partial pay inserts a ReturnCheckPayment row and
    auto-creates the matching DailyLineItem(kind='return_payback')
    so the daily-book stays in sync without double-entry."""
    from api.Modules.DailyBook.Models import DailyLineItem
    with db_session():
        rid = _seed_rc(test_store_id, amount=500.0)
    token = _login(client, test_store_id)
    resp = client.post(
        f"/api/v2/return-checks/{rid}/payments",
        json={
            "paid_on": "2026-04-15",
            "amount":  200.0,
            "method":  "cash",
            "note":    "first installment",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["payment"]["amount"] == 200.0
    # Recovered total flows into the parent envelope so the SPA
    # can render the new "remaining" value without a refetch.
    assert body["return_check"]["recovered_total"] == 200.0
    assert body["return_check"]["status"] == "pending"  # still partial
    with db_session():
        items = (
            db.session.query(DailyLineItem)
              .filter_by(return_check_id=rid, kind="return_payback")
              .all()
        )
        assert len(items) == 1
        assert items[0].amount == 200.0


def test_record_payment_auto_flips_status_to_recovered(
    client, test_store_id,
):
    """When the running total meets the full amount, the check
    auto-flips pending → recovered with a status_changed_on stamp.
    Mirrors the legacy form behavior."""
    with db_session():
        rid = _seed_rc(test_store_id, amount=300.0)
    token = _login(client, test_store_id)
    resp = client.post(
        f"/api/v2/return-checks/{rid}/payments",
        json={"paid_on": "2026-04-15", "amount": 300.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    rc = resp.get_json()["return_check"]
    assert rc["status"] == "recovered"
    assert rc["status_changed_on"] != ""


def test_record_payment_caps_at_remaining(client, test_store_id):
    """A second installment that would overshoot gets capped at the
    remaining balance — matches the legacy submit-time cap so the
    cashier can't accidentally accrue credit on a returned check."""
    with db_session():
        rid = _seed_rc(test_store_id, amount=100.0)
    token = _login(client, test_store_id)
    client.post(
        f"/api/v2/return-checks/{rid}/payments",
        json={"paid_on": "2026-04-15", "amount": 60.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = client.post(
        f"/api/v2/return-checks/{rid}/payments",
        json={"paid_on": "2026-04-16", "amount": 999.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.get_json()["payment"]["amount"] == 40.0  # capped


def test_return_check_fee_included_in_recoverable(client, test_store_id):
    """The returned-check fee raises the balance the customer owes:
    payments pay down to amount+fee, so paying the face amount alone
    leaves the check pending and a later installment caps at the
    remaining fee — not beyond it."""
    token = _login(client, test_store_id)
    auth = {"Authorization": f"Bearer {token}"}
    # $500 check + $25 fee → $525 owed in total.
    create = client.post(
        "/api/v2/return-checks",
        json={
            "bounced_on":       "2026-04-15",
            "customer_name":    "Fee Co",
            "company_name":     "Fee LLC",
            "amount":           500.0,
            "return_check_fee": 25.0,
        },
        headers=auth,
    )
    assert create.status_code == 201
    rid = create.get_json()["return_check"]["id"]

    # Paying the face amount alone still leaves the $25 fee owed —
    # the check stays pending, not recovered.
    p1 = client.post(
        f"/api/v2/return-checks/{rid}/payments",
        json={"paid_on": "2026-04-16", "amount": 500.0},
        headers=auth,
    )
    assert p1.status_code == 201
    assert p1.get_json()["return_check"]["status"] == "pending"

    # A follow-up that would overshoot caps at the remaining $25 fee.
    p2 = client.post(
        f"/api/v2/return-checks/{rid}/payments",
        json={"paid_on": "2026-04-17", "amount": 999.0},
        headers=auth,
    )
    assert p2.status_code == 201
    assert p2.get_json()["payment"]["amount"] == 25.0  # capped at fee
    rc = p2.get_json()["return_check"]
    assert rc["status"] == "recovered"           # fee paid → done
    assert rc["recovered_total"] == 525.0


def test_record_payment_rejects_on_closed_check(
    client, test_store_id,
):
    """Loss / fraud checks must be reopened before recording a
    payback — otherwise the daily book reflects payments against
    a written-off balance."""
    with db_session():
        rid = _seed_rc(test_store_id, status="loss")
    token = _login(client, test_store_id)
    resp = client.post(
        f"/api/v2/return-checks/{rid}/payments",
        json={"paid_on": "2026-04-15", "amount": 50.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


def test_record_payment_404_when_check_missing(
    client, test_store_id,
):
    token = _login(client, test_store_id)
    resp = client.post(
        "/api/v2/return-checks/9999/payments",
        json={"paid_on": "2026-04-15", "amount": 10.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ── DELETE /return-checks/{id}/payments/{pid} ───────────────


def test_delete_payment_removes_row_and_line_item(
    client, test_store_id,
):
    from api.Modules.DailyBook.Models import DailyLineItem
    with db_session():
        rid = _seed_rc(test_store_id, amount=400.0)
    token = _login(client, test_store_id)
    create = client.post(
        f"/api/v2/return-checks/{rid}/payments",
        json={"paid_on": "2026-04-15", "amount": 100.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    pid = create.get_json()["payment"]["id"]
    resp = client.delete(
        f"/api/v2/return-checks/{rid}/payments/{pid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    rc = resp.get_json()["return_check"]
    assert rc["recovered_total"] == 0.0
    with db_session():
        items = (
            db.session.query(DailyLineItem)
              .filter_by(return_check_id=rid, kind="return_payback")
              .all()
        )
        assert items == []


def test_delete_payment_reverts_recovered_to_pending(
    client, test_store_id,
):
    """If deleting the final installment drops payments below the
    full amount, the auto-recovered status reverts to pending."""
    with db_session():
        rid = _seed_rc(test_store_id, amount=200.0)
    token = _login(client, test_store_id)
    create = client.post(
        f"/api/v2/return-checks/{rid}/payments",
        json={"paid_on": "2026-04-15", "amount": 200.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    pid = create.get_json()["payment"]["id"]
    # Sanity: full payment auto-recovered.
    assert create.get_json()["return_check"]["status"] == "recovered"
    resp = client.delete(
        f"/api/v2/return-checks/{rid}/payments/{pid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    rc = resp.get_json()["return_check"]
    assert rc["status"] == "pending"
    assert rc["status_changed_on"] == ""


def test_delete_payment_404_when_payment_missing(
    client, test_store_id,
):
    with db_session():
        rid = _seed_rc(test_store_id)
    token = _login(client, test_store_id)
    resp = client.delete(
        f"/api/v2/return-checks/{rid}/payments/9999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ── Auth ────────────────────────────────────────────────────


def test_endpoints_require_jwt(client):
    g = client.get("/api/v2/return-checks")
    p = client.post("/api/v2/return-checks", json={
        "bounced_on": "2026-01-01",
        "customer_name": "X",
        "amount": 1.0,
    })
    u = client.put("/api/v2/return-checks/1", json={
        "bounced_on": "2026-01-01",
        "customer_name": "X",
        "amount": 1.0,
    })
    ml = client.post("/api/v2/return-checks/1/mark-loss")
    mf = client.post("/api/v2/return-checks/1/mark-fraud")
    ro = client.post("/api/v2/return-checks/1/reopen")
    pa = client.get("/api/v2/return-checks/1/payments")
    pp = client.post(
        "/api/v2/return-checks/1/payments",
        json={"paid_on": "2026-04-15", "amount": 10.0},
    )
    pd = client.delete("/api/v2/return-checks/1/payments/1")
    for r in (g, p, u, ml, mf, ro, pa, pp, pd):
        assert r.status_code == 401


def test_list_rejects_superadmin(client):
    from tests.conftest import login_superadmin
    token = login_superadmin(client)
    resp = client.get(
        "/api/v2/return-checks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
