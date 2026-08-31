"""Store Daily Book HTTP contract (D-2).

  GET   /api/v2/storebook/month
  GET   /api/v2/storebook/{day}
  PATCH /api/v2/storebook/{day}
  POST  /api/v2/storebook/{day}/lock
  POST  /api/v2/storebook/{day}/restore
"""
from tests._app import db, db_session

DAY = "2026-08-02"


def _admin(client, store_id):
    r = client.post("/api/v2/auth/login", json={
        "username": "admin@test.com", "password": "testpass123!",
        "store_id": store_id,
    })
    return r.get_json()["access_token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


# ── Auth ────────────────────────────────────────────────────


def test_requires_authentication(client):
    assert client.get(f"/api/v2/storebook/{DAY}").status_code == 401
    assert client.get(
        "/api/v2/storebook/month?year=2026&month=8",
    ).status_code == 401


def test_cashier_without_day_close_cannot_read(client, test_store_id):
    """The sheet carries the store's money — a login without the
    day_close grant must not see it."""
    from api.Core.Permissions import clear_user_permissions, set_user_permissions
    from api.Modules.Tenancy.Models import User
    with db_session():
        u = User(store_id=test_store_id, username="sb-cashier@x.com",
                 email="sb-cashier@x.com", role="employee",
                 full_name="Cashier", is_active=True)
        u.set_password("cashierpw1!")
        db.session.add(u); db.session.commit()
        uid = u.id
        # No day_close at all.
        set_user_permissions(test_store_id, uid, {"time_clock": {"read": True}})
    try:
        tok = client.post("/api/v2/auth/login", json={
            "username": "sb-cashier@x.com", "password": "cashierpw1!",
            "store_id": test_store_id,
        }).get_json()["access_token"]
        assert client.get(
            f"/api/v2/storebook/{DAY}", headers=_h(tok),
        ).status_code == 403
    finally:
        clear_user_permissions(test_store_id, uid)


# ── Reading a day ───────────────────────────────────────────


def test_day_is_created_on_first_open(client, test_store_id):
    """An operator shouldn't have to 'start' a day before typing."""
    tok = _admin(client, test_store_id)
    r = client.get(f"/api/v2/storebook/{DAY}", headers=_h(tok))
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["entry_date"] == DAY
    assert body["is_locked"] is False
    assert body["totals"]["over_short_cents"] == 0
    # Layout ships with the data so the page can't hold a stale copy.
    assert [c["column"] for c in body["layout"]] == [
        "sales", "tenders", "deposit",
    ]


def test_bad_date_is_rejected(client, test_store_id):
    tok = _admin(client, test_store_id)
    r = client.get("/api/v2/storebook/not-a-date", headers=_h(tok))
    assert r.status_code == 422


# ── Editing + the balance ───────────────────────────────────


def test_patch_updates_values_and_recomputes_over_short(client, test_store_id):
    tok = _admin(client, test_store_id)
    r = client.patch(
        f"/api/v2/storebook/{DAY}",
        json={"values": {
            "gross_sales": 2_064_771,
            "cards": 1_208_534, "closing_cash": 780_900,
            "lotto_paid_out": 54_800, "paid_out_purchases": 23_000,
        }},
        headers=_h(tok),
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    t = r.get_json()["totals"]
    assert t["sales_cents"] == 2_064_771
    assert t["tenders_cents"] == 2_067_234
    assert t["over_short_cents"] == 2_463


def test_patch_accepts_counts_and_notes(client, test_store_id):
    tok = _admin(client, test_store_id)
    r = client.patch(
        f"/api/v2/storebook/{DAY}",
        json={
            "values": {"money_order": 83_800},
            "counts": {"money_order_count": 7, "fuel_gallons": 463.51},
            "notes": "Pump 3 down after 6pm.",
        },
        headers=_h(tok),
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["counts"]["money_order_count"] == 7
    assert body["counts"]["fuel_gallons"] == 463.51
    assert body["notes"] == "Pump 3 down after 6pm."


def test_unknown_field_is_422_not_a_silent_drop(client, test_store_id):
    tok = _admin(client, test_store_id)
    r = client.patch(
        f"/api/v2/storebook/{DAY}",
        json={"values": {"grosss_sales": 100}}, headers=_h(tok),
    )
    assert r.status_code == 422


def test_patch_writes_an_audit_row(client, test_store_id):
    """Operator mutations are audited — CLAUDE.md invariant #7."""
    from api.Modules.Audit.Models import OperatorAuditLog
    tok = _admin(client, test_store_id)
    client.patch(
        f"/api/v2/storebook/{DAY}",
        json={"values": {"gross_sales": 1_000}}, headers=_h(tok),
    )
    with db_session():
        rows = (
            db.session.query(OperatorAuditLog)
            .filter_by(store_id=test_store_id, target_type="store_daily_entry")
            .all()
        )
        assert any(r.action == "update" for r in rows)


# ── Lock ────────────────────────────────────────────────────


def test_lock_then_edit_is_409(client, test_store_id):
    """409 (not 422) so the SPA can say 'unlock first' rather than
    showing a field-validation error."""
    tok = _admin(client, test_store_id)
    lock = client.post(
        f"/api/v2/storebook/{DAY}/lock",
        json={"locked": True}, headers=_h(tok),
    )
    assert lock.status_code == 200
    assert lock.get_json()["is_locked"] is True

    blocked = client.patch(
        f"/api/v2/storebook/{DAY}",
        json={"values": {"gross_sales": 1}}, headers=_h(tok),
    )
    assert blocked.status_code == 409

    unlock = client.post(
        f"/api/v2/storebook/{DAY}/lock",
        json={"locked": False}, headers=_h(tok),
    )
    assert unlock.get_json()["is_locked"] is False
    assert client.patch(
        f"/api/v2/storebook/{DAY}",
        json={"values": {"gross_sales": 1}}, headers=_h(tok),
    ).status_code == 200


# ── Restore an imported value ───────────────────────────────


def test_restore_returns_the_register_number(client, test_store_id):
    from datetime import date as _date
    from api.Modules.StoreBook.Services import (
        apply_import, get_or_create_entry,
    )
    tok = _admin(client, test_store_id)
    with db_session():
        e = get_or_create_entry(
            db.session, test_store_id, _date(2026, 8, 2),
        )
        apply_import(
            db.session, e, {"lottery_sales": 24_900}, source="gilbarco",
        )
        db.session.commit()

    # Operator overrides it...
    over = client.patch(
        f"/api/v2/storebook/{DAY}",
        json={"values": {"lottery_sales": 41_700}}, headers=_h(tok),
    ).get_json()
    assert over["values"]["lottery_sales"] == 41_700
    assert over["originals"]["lottery_sales"] == 24_900

    # ...then takes the register's number back.
    back = client.post(
        f"/api/v2/storebook/{DAY}/restore",
        json={"field_key": "lottery_sales"}, headers=_h(tok),
    )
    assert back.status_code == 200
    assert back.get_json()["values"]["lottery_sales"] == 24_900


def test_restore_without_an_import_is_422(client, test_store_id):
    tok = _admin(client, test_store_id)
    r = client.post(
        f"/api/v2/storebook/{DAY}/restore",
        json={"field_key": "gross_sales"}, headers=_h(tok),
    )
    assert r.status_code == 422


# ── Month ───────────────────────────────────────────────────


def test_month_lists_days_with_totals(client, test_store_id):
    tok = _admin(client, test_store_id)
    client.patch(
        "/api/v2/storebook/2026-08-02",
        json={"values": {"gross_sales": 196_300, "fuel_amount": 50_000},
              "counts": {"fuel_gallons": 100.5}},
        headers=_h(tok),
    )
    r = client.get(
        "/api/v2/storebook/month?year=2026&month=8", headers=_h(tok),
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["year"] == 2026 and body["month"] == 8
    day = next(x for x in body["rows"] if x["entry_date"] == "2026-08-02")
    assert day["sales_cents"] == 246_300
    assert body["total_fuel_gallons"] == 100.5
    assert body["total_fuel_cents"] == 50_000


def test_month_rejects_a_bad_month(client, test_store_id):
    tok = _admin(client, test_store_id)
    assert client.get(
        "/api/v2/storebook/month?year=2026&month=13", headers=_h(tok),
    ).status_code == 422
