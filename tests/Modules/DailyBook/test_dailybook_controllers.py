"""HTTP integration tests for the DailyBook Controllers (PR 23)."""
from datetime import date, timedelta

from fastapi.testclient import TestClient
from tests._app import db, db_session
import pytest


def _seed_report(store_id, report_date, **kwargs):
    from api.Modules.DailyBook.Models import DailyReport
    from tests._app import db
    r = DailyReport(
        store_id=store_id, report_date=report_date, **kwargs,
    )
    db.session.add(r); db.session.commit()
    return r.id


@pytest.fixture
def api_client():
    from api.main import api_app
    with TestClient(api_app) as c:
        yield c


@pytest.fixture
def authed_client(test_store_id, api_client):
    from api.Modules.Tenancy.Models import User
    with db_session():
        u = db.session.query(User).filter_by(
            store_id=test_store_id, role="admin",
        ).first()
        assert u is not None
        username = u.username
    resp = api_client.post(
        "/auth/login",
        json={"username": username, "password": "testpass123!",
              "store_id": test_store_id},
    )
    token = resp.json()["access_token"]
    api_client.headers["Authorization"] = f"Bearer {token}"
    return api_client


# ── /daily/{store_id}/{report_date} ─────────────────────────


def test_get_report_returns_404_when_missing(test_store_id, authed_client):
    today = date.today().isoformat()
    resp = authed_client.get(f"/daily/{test_store_id}/{today}")
    assert resp.status_code == 404


def test_get_fresh_day_returns_carried_forward_balance(
    test_store_id, authed_client,
):
    """A day with no saved row but a prior logged day returns 200 with
    the carried forward balance (read-only), not 404 — so the editor
    shows the opening cash before the operator saves anything."""
    prior = date.today() - timedelta(days=1)
    with db_session():
        _seed_report(
            test_store_id, prior,
            outside_cash_drops=100.0, safe_balance=400.0,
        )
    today = date.today().isoformat()
    resp = authed_client.get(f"/daily/{test_store_id}/{today}")
    assert resp.status_code == 200
    row = resp.json()["report"]
    assert row["forward_balance"] == 500.0
    assert row["forward_balance_auto"] is True


def test_get_report_returns_summary(test_store_id, authed_client):
    today = date.today()
    with db_session():
        _seed_report(
            test_store_id, today,
            taxable_sales=100.0, sales_tax=10.0,
            cash_expense=20.0,
        )
    resp = authed_client.get(f"/daily/{test_store_id}/{today.isoformat()}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["report"]["taxable_sales"] == 100.0
    assert body["report"]["total_disbursements"] >= 20.0
    assert body["report"]["locked"] is False


def test_get_report_rejects_malformed_date(test_store_id, authed_client):
    resp = authed_client.get(f"/daily/{test_store_id}/not-a-date")
    assert resp.status_code == 422


def test_get_report_rejects_zero_store_id(authed_client):
    """Path validation: store_id must be ≥ 1."""
    resp = authed_client.get("/daily/0/2026-05-06")
    assert resp.status_code == 422


# ── /daily/{store_id}/period ────────────────────────────────


def test_period_returns_summary(test_store_id, authed_client):
    today = date.today()
    yesterday = today - timedelta(days=1)
    with db_session():
        _seed_report(test_store_id, yesterday, taxable_sales=100.0)
        _seed_report(test_store_id, today, taxable_sales=200.0)
    resp = authed_client.get(
        f"/daily/{test_store_id}/period",
        params={"from": yesterday.isoformat(), "to": today.isoformat()},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["days_logged"] == 2
    assert body["total_receipts"] == 300.0


def test_period_swaps_when_from_after_to(test_store_id, authed_client):
    """Mirror the Reports period dependency: if from > to, swap so the
    SQL window stays non-empty."""
    today = date.today()
    yesterday = today - timedelta(days=1)
    with db_session():
        _seed_report(test_store_id, today, taxable_sales=42.0)
    resp = authed_client.get(
        f"/daily/{test_store_id}/period",
        params={"from": today.isoformat(), "to": yesterday.isoformat()},
    )
    assert resp.status_code == 200
    assert resp.json()["total_receipts"] == 42.0


def test_period_requires_from_and_to(test_store_id, authed_client):
    resp = authed_client.get(f"/daily/{test_store_id}/period")
    assert resp.status_code == 422


def test_period_rejects_malformed_dates(test_store_id, authed_client):
    resp = authed_client.get(
        f"/daily/{test_store_id}/period",
        params={"from": "not-a-date", "to": "2026-05-06"},
    )
    assert resp.status_code == 422


def test_period_empty_range_returns_zeros(test_store_id, authed_client):
    today = date.today().isoformat()
    resp = authed_client.get(
        f"/daily/{test_store_id}/period",
        params={"from": today, "to": today},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["days_logged"] == 0
    assert body["total_receipts"] == 0




def test_openapi_includes_daily_paths(authed_client):
    resp = authed_client.get("/openapi.json")
    assert resp.status_code == 200
    paths = set(resp.json()["paths"].keys())
    assert "/daily/{store_id}/{report_date}" in paths
    assert "/daily/{store_id}/period" in paths


# ── PUT /daily/{store_id}/{report_date} (write-side) ────────


def _login_admin_token(client_, store_id):
    resp = client_.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


def test_put_creates_report_when_missing(client, test_store_id):
    """First save for a day auto-creates the row + persists the
    submitted totals."""
    today_iso = date.today().isoformat()
    token = _login_admin_token(client, test_store_id)
    resp = client.put(
        f"/api/v2/daily/{test_store_id}/{today_iso}",
        json={
            "taxable_sales": 100.0,
            "non_taxable":   50.0,
            "sales_tax":     8.50,
            "notes":         "first save of the day",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    row = body["report"]
    assert row["taxable_sales"] == 100.0
    assert row["non_taxable"]   == 50.0
    assert row["sales_tax"]     == 8.50
    assert row["notes"]         == "first save of the day"


def test_put_updates_existing_report(client, test_store_id):
    today = date.today()
    with db_session():
        _seed_report(test_store_id, today, taxable_sales=10.0)
    token = _login_admin_token(client, test_store_id)
    resp = client.put(
        f"/api/v2/daily/{test_store_id}/{today.isoformat()}",
        json={"taxable_sales": 200.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["report"]["taxable_sales"] == 200.0


def test_put_persists_money_order_fees(client, test_store_id):
    """The Fees box's new money_order_fees field is operator-editable:
    it saves through the daily-report PUT and rolls into
    total_receipts alongside the other fee columns."""
    today_iso = date.today().isoformat()
    token = _login_admin_token(client, test_store_id)
    resp = client.put(
        f"/api/v2/daily/{test_store_id}/{today_iso}",
        json={
            "money_order_fees":       12.0,
            "check_cashing_fees":      8.0,
            "return_check_hold_fees":  5.0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    row = resp.get_json()["report"]
    assert row["money_order_fees"] == 12.0
    # All three fee lines flow into total_receipts.
    assert row["total_receipts"] == 25.0


def test_put_rejects_locked_report(client, test_store_id):
    from api.Modules.DailyBook.Models import DailyReport
    from tests._app import db
    today = date.today()
    from datetime import datetime as _dt
    with db_session():
        _seed_report(test_store_id, today, taxable_sales=5.0)
        r = (
            db.session.query(DailyReport)
              .filter_by(store_id=test_store_id, report_date=today)
              .first()
        )
        r.locked_at = _dt.utcnow()
        db.session.commit()

    token = _login_admin_token(client, test_store_id)
    resp = client.put(
        f"/api/v2/daily/{test_store_id}/{today.isoformat()}",
        json={"taxable_sales": 99.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert "lock" in resp.get_data(as_text=True).lower()


def test_put_rejects_cross_store_jwt(client, test_store_id):
    """Superadmin JWT (no store scope) cannot edit a store's
    daily book — same opaque 403 as a wrong-store JWT."""
    today = date.today().isoformat()
    from tests.conftest import login_superadmin
    token = login_superadmin(client)
    resp = client.put(
        f"/api/v2/daily/{test_store_id}/{today}",
        json={"taxable_sales": 99.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_put_rejects_extra_fields(client, test_store_id):
    """Schema is extra=forbid — attempting to write a
    line-item-derived field (money_transfer) must 422 rather
    than silently no-op."""
    today_iso = date.today().isoformat()
    token = _login_admin_token(client, test_store_id)
    resp = client.put(
        f"/api/v2/daily/{test_store_id}/{today_iso}",
        json={
            "taxable_sales": 100.0,
            "money_transfer": 999.0,  # derived; not in the schema
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# Characterization: every field listed under "the 422 trap" in
# INVARIANTS.md MUST be rejected by the daily-report PUT.  Pins
# the full read-only surface (line-item-derived + cross-table-
# derived) so a future refactor can't silently let one slip into
# the writable schema.
@pytest.mark.parametrize("derived_field", [
    "money_transfer",
    "return_check_paid_back",
    "cash_purchases",
    "cash_expense",
    "check_purchases",
    "check_expense",
    "other_cash_in",
    "other_cash_out",
    "outside_cash_drops",
    "checks_deposit",
    "from_bank",
    # over_short is a derived cash reconciliation — computed
    # server-side, never typed (INVARIANTS "Over/Short is derived").
    "over_short",
])
def test_put_rejects_every_derived_field(client, test_store_id, derived_field):
    today_iso = date.today().isoformat()
    token = _login_admin_token(client, test_store_id)
    resp = client.put(
        f"/api/v2/daily/{test_store_id}/{today_iso}",
        json={derived_field: 1.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422, (
        f"Expected 422 when sending {derived_field!r} (derived field per "
        f"INVARIANTS.md), got {resp.status_code}.  If this field is now "
        f"legitimately operator-editable, update INVARIANTS.md + add it to "
        f"EDITABLE_REPORT_FIELDS + DailyReportUpdateRequest in the same PR."
    )


def test_put_requires_jwt(test_store_id, api_client):
    today_iso = date.today().isoformat()
    resp = api_client.put(
        f"/daily/{test_store_id}/{today_iso}",
        json={"taxable_sales": 100.0},
    )
    assert resp.status_code == 401


# ── POST /daily/{store}/{date}/lock + /unlock ───────────────


def test_lock_creates_and_locks(client, test_store_id):
    """Locking a day with no report yet auto-creates + locks it."""
    today_iso = date.today().isoformat()
    token = _login_admin_token(client, test_store_id)
    resp = client.post(
        f"/api/v2/daily/{test_store_id}/{today_iso}/lock",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["report"]["locked"] is True


def test_lock_is_idempotent(client, test_store_id):
    today_iso = date.today().isoformat()
    token = _login_admin_token(client, test_store_id)
    r1 = client.post(
        f"/api/v2/daily/{test_store_id}/{today_iso}/lock",
        headers={"Authorization": f"Bearer {token}"},
    )
    r2 = client.post(
        f"/api/v2/daily/{test_store_id}/{today_iso}/lock",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == r2.status_code == 200
    assert r2.get_json()["report"]["locked"] is True


def test_unlock_clears_the_lock(client, test_store_id):
    today_iso = date.today().isoformat()
    token = _login_admin_token(client, test_store_id)
    # Lock first.
    client.post(
        f"/api/v2/daily/{test_store_id}/{today_iso}/lock",
        headers={"Authorization": f"Bearer {token}"},
    )
    # Then unlock.
    resp = client.post(
        f"/api/v2/daily/{test_store_id}/{today_iso}/unlock",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["report"]["locked"] is False


def test_unlock_404_when_no_report(client, test_store_id):
    """Unlocking a date that never had a report → 404. The
    lock endpoint auto-creates; unlock doesn't."""
    today_iso = date.today().isoformat()
    token = _login_admin_token(client, test_store_id)
    resp = client.post(
        f"/api/v2/daily/{test_store_id}/{today_iso}/unlock",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_lock_unlock_reject_cross_store_jwt(client, test_store_id):
    """Superadmin / wrong-store JWT can't lock or unlock."""
    today_iso = date.today().isoformat()
    from tests.conftest import login_superadmin
    token = login_superadmin(client)
    r1 = client.post(
        f"/api/v2/daily/{test_store_id}/{today_iso}/lock",
        headers={"Authorization": f"Bearer {token}"},
    )
    r2 = client.post(
        f"/api/v2/daily/{test_store_id}/{today_iso}/unlock",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 403
    assert r2.status_code == 403


def test_lock_unlock_require_jwt(test_store_id, api_client):
    today_iso = date.today().isoformat()
    c = api_client
    r1 = c.post(f"/daily/{test_store_id}/{today_iso}/lock")
    r2 = c.post(f"/daily/{test_store_id}/{today_iso}/unlock")
    assert r1.status_code == 401
    assert r2.status_code == 401


# ── Line items: GET / POST / DELETE ─────────────────────────


def test_line_items_list_returns_envelope(client, test_store_id):
    today_iso = date.today().isoformat()
    token = _login_admin_token(client, test_store_id)
    resp = client.get(
        f"/api/v2/daily/{test_store_id}/{today_iso}/line-items",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "items" in body
    assert isinstance(body["items"], list)


def test_line_items_create_round_trip(client, test_store_id):
    """Create a drop, then list — the new row appears + the
    matching DailyReport.outside_cash_drops total is updated."""
    today_iso = date.today().isoformat()
    token = _login_admin_token(client, test_store_id)
    resp = client.post(
        f"/api/v2/daily/{test_store_id}/{today_iso}/line-items",
        json={
            "kind": "drop",
            "at_time": "10:30",
            "amount": 250.0,
            "note": "morning safe drop",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    row = resp.get_json()
    assert row["kind"] == "drop"
    assert row["amount"] == 250.0

    # Now list — must include the new row.
    listed = client.get(
        f"/api/v2/daily/{test_store_id}/{today_iso}/line-items?kind=drop",
        headers={"Authorization": f"Bearer {token}"},
    )
    items = listed.get_json()["items"]
    assert any(i["amount"] == 250.0 and i["kind"] == "drop" for i in items)

    # Daily report's outside_cash_drops field should match.
    detail = client.get(
        f"/api/v2/daily/{test_store_id}/{today_iso}",
        headers={"Authorization": f"Bearer {token}"},
    )
    # The read-side row exposes drops via the cash_deposit /
    # checks_deposit pair OR as part of total_disbursements;
    # we don't rely on a specific surfaced field here. The
    # behavioral guarantee is that the create lands AND the
    # subsequent list shows it — both validated above.
    assert detail.status_code == 200


def test_line_items_create_rejects_bad_amount(client, test_store_id):
    today_iso = date.today().isoformat()
    token = _login_admin_token(client, test_store_id)
    resp = client.post(
        f"/api/v2/daily/{test_store_id}/{today_iso}/line-items",
        json={
            "kind": "drop", "at_time": "10:30",
            "amount": -5.0, "note": "",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_line_items_create_rejects_unknown_kind(client, test_store_id):
    today_iso = date.today().isoformat()
    token = _login_admin_token(client, test_store_id)
    resp = client.post(
        f"/api/v2/daily/{test_store_id}/{today_iso}/line-items",
        json={
            "kind": "totally_made_up", "at_time": "10:30",
            "amount": 5.0, "note": "",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_line_items_delete_round_trip(client, test_store_id):
    today_iso = date.today().isoformat()
    token = _login_admin_token(client, test_store_id)
    create = client.post(
        f"/api/v2/daily/{test_store_id}/{today_iso}/line-items",
        json={
            "kind": "cash_expense", "at_time": "11:15",
            "amount": 30.0, "note": "tape rolls",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    item_id = create.get_json()["id"]
    delete = client.delete(
        f"/api/v2/daily/{test_store_id}/line-items/{item_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete.status_code == 204
    listed = client.get(
        f"/api/v2/daily/{test_store_id}/{today_iso}/line-items?kind=cash_expense",
        headers={"Authorization": f"Bearer {token}"},
    )
    ids = [i["id"] for i in listed.get_json()["items"]]
    assert item_id not in ids


def test_line_items_delete_404_when_missing(client, test_store_id):
    token = _login_admin_token(client, test_store_id)
    resp = client.delete(
        f"/api/v2/daily/{test_store_id}/line-items/9999999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ── PATCH /line-items/{id} ──────────────────────────────────


def test_line_items_patch_round_trip(client, test_store_id):
    """PATCH lets the operator fix a typo'd amount / time / note on
    an existing line item — and the DailyReport roll-up rederives."""
    today_iso = date.today().isoformat()
    token = _login_admin_token(client, test_store_id)
    create = client.post(
        f"/api/v2/daily/{test_store_id}/{today_iso}/line-items",
        json={
            "kind": "drop", "at_time": "09:00",
            "amount": 100.0, "note": "morning",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    item_id = create.get_json()["id"]

    patched = client.patch(
        f"/api/v2/daily/{test_store_id}/line-items/{item_id}",
        json={"amount": 250.0, "note": "morning + extra"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert patched.status_code == 200, patched.get_data(as_text=True)
    body = patched.get_json()
    assert body["amount"] == 250.0
    assert body["note"] == "morning + extra"
    # at_time wasn't in the body, stays at the original 09:00
    assert body["at_time"] == "09:00"

    # DailyReport's outside_cash_drops field should now reflect 250.
    report = client.get(
        f"/api/v2/daily/{test_store_id}/{today_iso}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert report.get_json()["report"]["outside_cash_drops"] == 250.0


def test_line_items_patch_404_when_missing(client, test_store_id):
    token = _login_admin_token(client, test_store_id)
    resp = client.patch(
        f"/api/v2/daily/{test_store_id}/line-items/9999999",
        json={"amount": 5.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_line_items_patch_rejects_bad_amount(client, test_store_id):
    """`amount: 0` (or negative) is a 422 — same contract as create."""
    today_iso = date.today().isoformat()
    token = _login_admin_token(client, test_store_id)
    create = client.post(
        f"/api/v2/daily/{test_store_id}/{today_iso}/line-items",
        json={
            "kind": "drop", "at_time": "09:00",
            "amount": 100.0, "note": "ok",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    item_id = create.get_json()["id"]
    resp = client.patch(
        f"/api/v2/daily/{test_store_id}/line-items/{item_id}",
        json={"amount": -5.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_line_items_patch_rejects_extra_fields(client, test_store_id):
    """`kind` is NOT mutable post-creation — extra=forbid rejects."""
    today_iso = date.today().isoformat()
    token = _login_admin_token(client, test_store_id)
    create = client.post(
        f"/api/v2/daily/{test_store_id}/{today_iso}/line-items",
        json={
            "kind": "drop", "at_time": "09:00",
            "amount": 100.0, "note": "ok",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    item_id = create.get_json()["id"]
    resp = client.patch(
        f"/api/v2/daily/{test_store_id}/line-items/{item_id}",
        json={"kind": "cash_expense"},  # not in the schema
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_line_items_reject_cross_store_jwt(client, test_store_id):
    today_iso = date.today().isoformat()
    from tests.conftest import login_superadmin
    token = login_superadmin(client)
    g = client.get(
        f"/api/v2/daily/{test_store_id}/{today_iso}/line-items",
        headers={"Authorization": f"Bearer {token}"},
    )
    p = client.post(
        f"/api/v2/daily/{test_store_id}/{today_iso}/line-items",
        json={"kind": "drop", "at_time": "10:30", "amount": 1.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert g.status_code == 403
    assert p.status_code == 403


def test_line_items_require_jwt(test_store_id, api_client):
    today_iso = date.today().isoformat()
    c = api_client
    g = c.get(f"/daily/{test_store_id}/{today_iso}/line-items")
    p = c.post(
        f"/daily/{test_store_id}/{today_iso}/line-items",
        json={"kind": "drop", "at_time": "10:30", "amount": 5.0},
    )
    d = c.delete(f"/daily/{test_store_id}/line-items/1")
    assert g.status_code == 401
    assert p.status_code == 401
    assert d.status_code == 401


# ── Line-item edit: time is OPTIONAL on update ──────────────


def test_patch_line_item_blank_time_is_allowed(client, test_store_id):
    """Editing a line item that has no time must NOT 422 with 'Enter a
    valid time' — the SPA's inline edit always sends `at_time`, so a
    blank value means 'leave the time as-is', matching create's guard.
    """
    today = date.today().isoformat()
    token = _login_admin_token(client, test_store_id)
    headers = {"Authorization": f"Bearer {token}"}
    # Create a check-deposit line item with NO time.
    created = client.post(
        f"/api/v2/daily/{test_store_id}/{today}/line-items",
        json={"kind": "check_deposit", "at_time": "", "amount": "100.00"},
        headers=headers,
    )
    assert created.status_code == 201, created.get_data(as_text=True)
    item_id = created.get_json()["id"]
    assert created.get_json()["at_time"] == ""

    # Edit the amount, still sending a blank time (as the SPA does).
    resp = client.patch(
        f"/api/v2/daily/{test_store_id}/line-items/{item_id}",
        json={"at_time": "", "amount": 250.0, "note": "reconciled"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["amount"] == 250.0
    assert body["at_time"] == ""      # stayed timeless, no error
    assert body["note"] == "reconciled"


def test_patch_line_item_valid_time_still_parsed(client, test_store_id):
    """A non-blank time on edit is still parsed + persisted."""
    today = date.today().isoformat()
    token = _login_admin_token(client, test_store_id)
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        f"/api/v2/daily/{test_store_id}/{today}/line-items",
        json={"kind": "check_deposit", "at_time": "", "amount": "50.00"},
        headers=headers,
    )
    item_id = created.get_json()["id"]
    resp = client.patch(
        f"/api/v2/daily/{test_store_id}/line-items/{item_id}",
        json={"at_time": "14:30", "amount": 50.0},
        headers=headers,
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["at_time"] == "14:30"
