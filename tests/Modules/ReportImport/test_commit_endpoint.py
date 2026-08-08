"""HTTP tests for POST /api/v2/report-import/intermex/commit.

Monkeypatches the parser (unit-tested elsewhere) so we don't ship a
binary PDF fixture; the commit Service is unit-tested in
test_commit_service.py. These cover the endpoint wiring: auth, store
scoping, the locked-day guard, date validation, and the audit row.
"""
import base64
from datetime import date, datetime

from tests._app import db, db_session


def _login_admin_token(client_, store_id):
    resp = client_.post(
        "/api/v2/auth/login",
        json={"username": "admin@test.com", "password": "testpass123!",
              "store_id": store_id},
    )
    return resp.get_json()["access_token"]


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _fake_report(giros):
    from api.Modules.ReportImport.Services import (
        IntermexDailyReport, IntermexTxnRow,
    )
    rows = [
        IntermexTxnRow(
            section="giros", confirm_number=str(i),
            send_amount=s, fee=f, federal_tax=t,
            total_collected=round(s + f + t, 2), cashier="C",
            cancelled=False, replacement=False, reconciles=True,
        )
        for i, (s, f, t) in enumerate(giros, start=1)
    ]
    return IntermexDailyReport(
        agency="TEST", report_date=date(2026, 5, 1),
        giros=rows, money_orders=[], bill_payments=[],
    )


def _patch_parse(monkeypatch, report):
    monkeypatch.setattr(
        "api.Modules.ReportImport.Controllers.parse_intermex_pdf",
        lambda data: report,
    )


def _body(store_id, day_iso):
    return {
        "content_base64": _b64(b"%PDF-1.4 fake"),
        "filename": "r.pdf",
        "store_id": store_id,
        "report_date": day_iso,
    }


def test_commit_requires_auth(client):
    resp = client.post(
        "/api/v2/report-import/intermex/commit",
        json=_body(1, date.today().isoformat()),
    )
    assert resp.status_code == 401


def test_commit_happy_path_updates_breakdown_and_audits(
    client, test_store_id, monkeypatch,
):
    from api.Modules.Audit.Models import OperatorAuditLog
    from api.Modules.DailyBook.Services import read_mt_breakdown
    day = date(2026, 6, 1)
    _patch_parse(monkeypatch, _fake_report([(100.0, 5.0, 1.0),
                                            (200.0, 8.0, 2.0)]))
    token = _login_admin_token(client, test_store_id)
    resp = client.post(
        "/api/v2/report-import/intermex/commit",
        json=_body(test_store_id, day.isoformat()),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    b = resp.get_json()
    assert b["company"] == "Intermex"
    assert b["giros_committed"] == 2
    assert b["amount"] == 300.0
    assert b["committed_total"] == 316.0

    with db_session():
        breakdown = read_mt_breakdown(db.session, test_store_id, day)
        intermex = next(r for r in breakdown.rows if r.company == "Intermex")
        assert intermex.saved_amount == 300.0
        audit = (
            db.session.query(OperatorAuditLog)
              .filter_by(store_id=test_store_id, action="import_intermex_mt")
              .all()
        )
        assert len(audit) == 1
        assert "intermex import" in audit[0].summary.lower()


def test_commit_rejects_cross_store(client, test_store_id, monkeypatch):
    _patch_parse(monkeypatch, _fake_report([(100.0, 5.0, 1.0)]))
    token = _login_admin_token(client, test_store_id)
    resp = client.post(
        "/api/v2/report-import/intermex/commit",
        json=_body(test_store_id + 9999, date(2026, 6, 2).isoformat()),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_commit_rejects_bad_date(client, test_store_id, monkeypatch):
    _patch_parse(monkeypatch, _fake_report([(100.0, 5.0, 1.0)]))
    token = _login_admin_token(client, test_store_id)
    resp = client.post(
        "/api/v2/report-import/intermex/commit",
        json=_body(test_store_id, "not-a-date"),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_commit_rejects_locked_day(client, test_store_id, monkeypatch):
    from api.Modules.DailyBook.Models import DailyReport
    day = date(2026, 6, 3)
    with db_session():
        db.session.add(DailyReport(
            store_id=test_store_id, report_date=day,
            locked_at=datetime.utcnow(),
        ))
        db.session.commit()
    _patch_parse(monkeypatch, _fake_report([(100.0, 5.0, 1.0)]))
    token = _login_admin_token(client, test_store_id)
    resp = client.post(
        "/api/v2/report-import/intermex/commit",
        json=_body(test_store_id, day.isoformat()),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert "lock" in resp.get_data(as_text=True).lower()


def test_commit_rejects_non_reconciling_report(
    client, test_store_id, monkeypatch,
):
    rep = _fake_report([(100.0, 5.0, 1.0)])
    object.__setattr__(rep.giros[0], "reconciles", False)
    _patch_parse(monkeypatch, rep)
    token = _login_admin_token(client, test_store_id)
    resp = client.post(
        "/api/v2/report-import/intermex/commit",
        json=_body(test_store_id, date(2026, 6, 4).isoformat()),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
