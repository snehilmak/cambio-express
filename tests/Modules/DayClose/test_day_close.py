"""DayClose module (P1-7): departments, register closes, day summary.

The invariants under test:
  * department names unique per store (case-insensitive),
  * POST /day/{date}/closes upserts on the (register, shift) key —
    corrections replace, department lines replace-all,
  * over_short = cash_counted − cash_total, None until counted,
  * tender_variance = (cash + card + other) − (gross + tax),
  * day summary aggregates across closes + rolls up departments,
  * uncounted_drawers flags closes with no drawer count,
  * cashiers (employees) can submit closes but not manage the
    department catalog or delete closes,
  * module flag bundles: day_close ON for cstore, OFF for msb_hybrid.
"""
from tests._app import db, db_session
from tests.conftest import login_admin, make_employee_client


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _admin(client, test_store_id):
    return _headers(login_admin(client, test_store_id))


def _mk_department(client, h, name="Grocery", sort_order=0):
    resp = client.post("/api/v2/dayclose/departments", headers=h, json={
        "name": name, "sort_order": sort_order,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["department"]


def _close_payload(**overrides):
    body = {
        "register_label": "Register 1",
        "gross_sales": 1000.0,
        "sales_tax": 80.0,
        "cash_total": 400.0,
        "card_total": 650.0,
        "other_total": 30.0,
    }
    body.update(overrides)
    return body


# ── Departments ────────────────────────────────────────────


def test_department_crud_roundtrip(client, test_store_id):
    h = _admin(client, test_store_id)
    dept = _mk_department(client, h, "Tobacco", sort_order=2)
    assert dept["name"] == "Tobacco"

    resp = client.put(
        f"/api/v2/dayclose/departments/{dept['id']}", headers=h,
        json={"name": "Tobacco & Vape", "is_active": False},
    )
    assert resp.status_code == 200
    assert resp.json()["department"]["name"] == "Tobacco & Vape"
    # Inactive departments drop out of the default list.
    assert client.get(
        "/api/v2/dayclose/departments", headers=h,
    ).json()["departments"] == []
    assert len(client.get(
        "/api/v2/dayclose/departments?include_inactive=1", headers=h,
    ).json()["departments"]) == 1


def test_duplicate_department_name_conflicts(client, test_store_id):
    h = _admin(client, test_store_id)
    _mk_department(client, h, "Beer")
    resp = client.post("/api/v2/dayclose/departments", headers=h, json={
        "name": "beer",
    })
    assert resp.status_code == 409


# ── Register closes ────────────────────────────────────────


def test_close_math_and_day_rollup(client, test_store_id):
    """Two registers: gross/tax/tenders aggregate; department sales
    roll up across closes; over_short and tender_variance compute
    from the entered figures."""
    h = _admin(client, test_store_id)
    groc = _mk_department(client, h, "Grocery", sort_order=0)
    beer = _mk_department(client, h, "Beer", sort_order=1)

    day = client.post(
        "/api/v2/dayclose/day/2026-08-20/closes", headers=h,
        json=_close_payload(
            register_label="Register 1",
            cash_counted=395.0,   # $5 short vs cash_total 400
            department_sales=[
                {"department_id": groc["id"], "amount": 700.0},
                {"department_id": beer["id"], "amount": 300.0},
            ],
        ),
    ).json()
    assert day["gross_sales"] == 1000.0
    assert day["closes"][0]["over_short"] == -5.0
    # (400 + 650 + 30) − (1000 + 80) = 0
    assert day["closes"][0]["tender_variance"] == 0.0
    assert day["uncounted_drawers"] == 0

    day = client.post(
        "/api/v2/dayclose/day/2026-08-20/closes", headers=h,
        json=_close_payload(
            register_label="Register 2",
            gross_sales=500.0, sales_tax=40.0,
            cash_total=240.0, card_total=310.0, other_total=0.0,
            department_sales=[
                {"department_id": beer["id"], "amount": 500.0},
            ],
        ),
    ).json()
    assert day["gross_sales"] == 1500.0
    assert day["sales_tax"] == 120.0
    assert day["cash_total"] == 640.0
    # Register 2's drawer not counted → flagged; day over_short only
    # sums the counted drawers.
    assert day["uncounted_drawers"] == 1
    assert day["over_short"] == -5.0
    # (240 + 310 + 0) − (500 + 40) = +10 on register 2.
    assert day["tender_variance"] == 10.0
    # Department rollup: Grocery 700, Beer 300 + 500.
    totals = {
        t["department_name"]: t["amount"]
        for t in day["department_totals"]
    }
    assert totals == {"Grocery": 700.0, "Beer": 800.0}


def test_upsert_replaces_same_register_shift(client, test_store_id):
    h = _admin(client, test_store_id)
    groc = _mk_department(client, h, "Grocery")
    beer = _mk_department(client, h, "Beer")

    client.post(
        "/api/v2/dayclose/day/2026-08-20/closes", headers=h,
        json=_close_payload(department_sales=[
            {"department_id": groc["id"], "amount": 1000.0},
        ]),
    )
    # Re-key the same register + (blank) shift → replaces, and the
    # department lines replace-all (Grocery line disappears).
    day = client.post(
        "/api/v2/dayclose/day/2026-08-20/closes", headers=h,
        json=_close_payload(
            gross_sales=900.0,
            department_sales=[
                {"department_id": beer["id"], "amount": 900.0},
            ],
        ),
    ).json()
    assert len(day["closes"]) == 1
    assert day["gross_sales"] == 900.0
    assert [t["department_name"] for t in day["department_totals"]] == ["Beer"]

    # A different shift label on the same register is a NEW close.
    day = client.post(
        "/api/v2/dayclose/day/2026-08-20/closes", headers=h,
        json=_close_payload(shift_label="Evening", gross_sales=100.0),
    ).json()
    assert len(day["closes"]) == 2


def test_close_validation_guards(client, test_store_id):
    h = _admin(client, test_store_id)
    # Unknown department → 404.
    resp = client.post(
        "/api/v2/dayclose/day/2026-08-20/closes", headers=h,
        json=_close_payload(department_sales=[
            {"department_id": 99999, "amount": 10.0},
        ]),
    )
    assert resp.status_code == 404
    # Duplicate department lines → 422.
    dept = _mk_department(client, h, "Deli")
    resp = client.post(
        "/api/v2/dayclose/day/2026-08-20/closes", headers=h,
        json=_close_payload(department_sales=[
            {"department_id": dept["id"], "amount": 10.0},
            {"department_id": dept["id"], "amount": 20.0},
        ]),
    )
    assert resp.status_code == 422


def test_delete_close(client, test_store_id):
    h = _admin(client, test_store_id)
    day = client.post(
        "/api/v2/dayclose/day/2026-08-21/closes", headers=h,
        json=_close_payload(),
    ).json()
    close_id = day["closes"][0]["id"]
    day = client.delete(
        f"/api/v2/dayclose/closes/{close_id}", headers=h,
    ).json()
    assert day["closes"] == []
    assert client.delete(
        f"/api/v2/dayclose/closes/{close_id}", headers=h,
    ).status_code == 404


# ── Permissions ────────────────────────────────────────────


def test_employee_can_close_but_not_manage(client, test_store_id):
    admin_h = _admin(client, test_store_id)
    _mk_department(client, admin_h, "Grocery")

    emp_client, emp_jwt = make_employee_client(test_store_id)
    emp_h = _headers(emp_jwt)
    # Submitting a close: allowed (day_close.create).
    resp = client.post(
        "/api/v2/dayclose/day/2026-08-20/closes", headers=emp_h,
        json=_close_payload(register_label="Register 9"),
    )
    assert resp.status_code == 200, resp.text
    close_id = resp.json()["closes"][0]["id"]
    # Department catalog + deletion: denied (day_close.update).
    assert client.post(
        "/api/v2/dayclose/departments", headers=emp_h,
        json={"name": "Nope"},
    ).status_code == 403
    assert client.delete(
        f"/api/v2/dayclose/closes/{close_id}", headers=emp_h,
    ).status_code == 403


# ── Module flag bundle ─────────────────────────────────────


def test_day_close_flag_follows_business_type(client, test_store_id):
    from api.Modules.Billing.Services.feature_flags import (
        store_feature_enabled,
    )
    from api.Modules.Tenancy.Models import Store
    with db_session():
        store = db.session.get(Store, test_store_id)
        store.business_type = "cstore"
        db.session.commit()
        assert store_feature_enabled(
            db.session, store, "module_day_close",
        ) is True
        store.business_type = "msb_hybrid"
        db.session.commit()
        assert store_feature_enabled(
            db.session, store, "module_day_close",
        ) is False


def test_session_status_carries_day_close_flag(client, test_store_id):
    from api.Modules.Tenancy.Models import Store
    with db_session():
        db.session.get(Store, test_store_id).business_type = "cstore"
        db.session.commit()
    token = login_admin(client, test_store_id)
    body = client.get(
        "/api/v2/auth/session-status", headers=_headers(token),
    ).json()
    assert "module_day_close" in body["features"]
