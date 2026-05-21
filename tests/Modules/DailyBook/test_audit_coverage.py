"""Regression guard for CLAUDE.md invariant #7 — every mutating
DailyBook endpoint records an `OperatorAuditLog` row.

Cash-ledger edits + per-company MT breakdown + the field save all
fan into the daily P&L, so silent mutation here would leave admins
asking "who logged this $500 drop?" with no answer.  These tests
fire if a future refactor moves any of the four audit emissions
back off the controllers.
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


def _latest_audit(store_id, action: str):
    from api.Modules.Audit.Models import OperatorAuditLog
    return (
        db.session.query(OperatorAuditLog)
          .filter_by(store_id=store_id, action=action)
          .order_by(OperatorAuditLog.id.desc())
          .first()
    )


def _seed_report(store_id, on_date):
    from api.Modules.DailyBook.Models import DailyReport
    with db_session():
        r = DailyReport(store_id=store_id, report_date=on_date)
        db.session.add(r); db.session.commit()


# ── PUT /daily/{store}/{date} ───────────────────────────────


def test_update_daily_emits_audit_row(client, test_store_id):
    """`PUT /daily/{store}/{date}` records `update_daily_report`
    listing the field keys the operator touched."""
    today_iso = date.today().isoformat()
    token = _login_admin(client, test_store_id)
    resp = client.put(
        f"/api/v2/daily/{test_store_id}/{today_iso}",
        json={"taxable_sales": 100.0, "notes": "audit smoke"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    row = _latest_audit(test_store_id, "update_daily_report")
    assert row is not None
    summary = row.summary or ""
    assert "taxable_sales" in summary
    assert "notes" in summary


def test_update_daily_no_op_skips_audit(client, test_store_id):
    """Empty payload — no fields, no notes — emits no audit row."""
    today_iso = date.today().isoformat()
    token = _login_admin(client, test_store_id)
    from api.Modules.Audit.Models import OperatorAuditLog
    before = (
        db.session.query(OperatorAuditLog)
          .filter_by(store_id=test_store_id, action="update_daily_report")
          .count()
    )
    resp = client.put(
        f"/api/v2/daily/{test_store_id}/{today_iso}",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    after = (
        db.session.query(OperatorAuditLog)
          .filter_by(store_id=test_store_id, action="update_daily_report")
          .count()
    )
    assert after == before


# ── POST + DELETE /daily/{store}/{date}/line-items ──────────


def test_line_item_create_emits_audit_row(client, test_store_id):
    """Logging a cash-ledger entry records a `create_line_item`
    row with the kind + amount in the summary."""
    today = date.today()
    _seed_report(test_store_id, today)
    token = _login_admin(client, test_store_id)
    resp = client.post(
        f"/api/v2/daily/{test_store_id}/{today.isoformat()}/line-items",
        json={
            "kind": "drop",
            "at_time": "10:30",
            "amount": "250.00",
            "note": "audit smoke",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    row = _latest_audit(test_store_id, "create_line_item")
    assert row is not None
    summary = row.summary or ""
    assert "kind=drop" in summary
    assert "250.00" in summary


def test_line_item_delete_emits_audit_row(client, test_store_id):
    """Deleting a cash-ledger entry records a `delete_line_item`
    row — the highest-value audit on the daily-book surface
    (deletions are what answer "where did that drop go?")."""
    today = date.today()
    _seed_report(test_store_id, today)
    token = _login_admin(client, test_store_id)
    create = client.post(
        f"/api/v2/daily/{test_store_id}/{today.isoformat()}/line-items",
        json={
            "kind": "drop",
            "at_time": "11:00",
            "amount": "100.00",
            "note": "to be deleted",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    item_id = create.get_json()["id"]
    resp = client.delete(
        f"/api/v2/daily/{test_store_id}/line-items/{item_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204
    row = _latest_audit(test_store_id, "delete_line_item")
    assert row is not None
    assert "kind=drop" in (row.summary or "")
    assert "100.00" in (row.summary or "")


# ── PUT /daily/{store}/{date}/mt-breakdown ──────────────────


def test_mt_breakdown_replace_emits_audit_row(client, test_store_id):
    today = date.today()
    _seed_report(test_store_id, today)
    token = _login_admin(client, test_store_id)
    resp = client.put(
        f"/api/v2/daily/{test_store_id}/{today.isoformat()}/mt-breakdown",
        json={
            "rows": [
                {"company": "intermex", "amount": 500.0, "fees": 5.0,
                 "federal_tax": 0.0, "commission": 2.0},
                {"company": "maxi",     "amount": 300.0, "fees": 3.0,
                 "federal_tax": 0.0, "commission": 1.5},
            ],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    row = _latest_audit(test_store_id, "replace_mt_breakdown")
    assert row is not None
    summary = row.summary or ""
    # Companies appear alphabetically.
    assert "intermex" in summary
    assert "maxi" in summary
