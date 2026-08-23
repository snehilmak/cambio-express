"""Module-driven dashboard (P1-10): sections follow enabled modules.

The invariants under test:
  * the summary carries ``modules`` so the SPA renders exactly the
    sections the store's business type enables,
  * a cstore-type store gets day_close + lottery sections and NO
    money-services data (transfer queries are skipped entirely),
  * an msb_hybrid store keeps the transfer-shaped payload and gets
    no day_close/lottery sections,
  * the day-close snapshot prefers today and falls back to the
    most recent booked business day,
  * employee summaries carry the same module sections.
"""
from tests._app import db, db_session
from tests.conftest import login_admin, make_employee_client


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _set_type(test_store_id, business_type):
    from api.Modules.Tenancy.Models import Store
    with db_session():
        db.session.get(Store, test_store_id).business_type = business_type
        db.session.commit()


def _summary(client, token):
    resp = client.get(
        "/api/v2/dashboard/summary", headers=_headers(token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_cstore_gets_retail_sections_not_money_services(
    client, test_store_id,
):
    _set_type(test_store_id, "cstore")
    token = login_admin(client, test_store_id)
    data = _summary(client, token)
    assert "module_day_close" in data["modules"]
    assert "module_lottery" in data["modules"]
    assert "module_money_services" not in data["modules"]
    # Money-services payload empty without their module.
    assert data["company_stats"] == []
    assert data["recent_transfers"] == []
    assert data["recent_batches"] == []
    # No day-close data booked yet → section stays None.
    assert data["day_close"] is None
    assert data["lottery"] is None


def test_msb_hybrid_keeps_transfer_shape(client, test_store_id):
    _set_type(test_store_id, "msb_hybrid")
    token = login_admin(client, test_store_id)
    data = _summary(client, token)
    assert "module_money_services" in data["modules"]
    assert data["day_close"] is None
    assert data["lottery"] is None
    assert "total_transfers" in data["kpis"]


def test_day_close_snapshot_prefers_latest_booked_day(
    client, test_store_id,
):
    _set_type(test_store_id, "cstore")
    token = login_admin(client, test_store_id)
    h = _headers(token)
    # Book a close on a past business day (no closes today).
    resp = client.post(
        "/api/v2/dayclose/day/2026-08-20/closes", headers=h,
        json={
            "register_label": "Register 1",
            "gross_sales": 1200.0, "sales_tax": 96.0,
            "cash_total": 500.0, "card_total": 796.0, "other_total": 0.0,
        },
    )
    assert resp.status_code == 200, resp.text

    data = _summary(client, token)
    snap = data["day_close"]
    assert snap is not None
    assert snap["date"] == "2026-08-20"
    assert snap["gross_sales"] == 1200.0
    assert snap["closes"] == 1
    assert snap["uncounted_drawers"] == 1


def test_employee_summary_carries_module_sections(client, test_store_id):
    _set_type(test_store_id, "cstore")
    emp_client, emp_jwt = make_employee_client(test_store_id)
    data = _summary(client, emp_jwt)
    assert "module_day_close" in data["modules"]
    # No transfers section content without money services.
    assert data["today_transfers"] == []
    assert data["totals"]["count"] == 0
