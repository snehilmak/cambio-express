"""HTTP tests for POST /api/v2/report-import/intermex/parse.

The happy path monkeypatches the parser (already unit-tested against a
synthetic fixture in test_intermex_parser.py) so we don't have to ship
a binary PDF fixture. The error paths use real (bad) input.
"""
import base64
from datetime import date

import pytest


def _login_admin_token(client_, store_id):
    resp = client_.post(
        "/api/v2/auth/login",
        json={"username": "admin@test.com", "password": "testpass123!",
              "store_id": store_id},
    )
    return resp.get_json()["access_token"]


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def test_parse_requires_auth(client):
    resp = client.post(
        "/api/v2/report-import/intermex/parse",
        json={"content_base64": _b64(b"x")},
    )
    assert resp.status_code == 401


def test_parse_rejects_bad_base64(client, test_store_id):
    token = _login_admin_token(client, test_store_id)
    resp = client.post(
        "/api/v2/report-import/intermex/parse",
        json={"content_base64": "!!!not base64!!!"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_parse_rejects_non_pdf(client, test_store_id):
    token = _login_admin_token(client, test_store_id)
    resp = client.post(
        "/api/v2/report-import/intermex/parse",
        json={"content_base64": _b64(b"this is plainly not a pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_parse_happy_path(client, test_store_id, monkeypatch):
    from api.Modules.ReportImport.Services import (
        IntermexDailyReport, IntermexTxnRow, SectionTotals,
    )

    fake = IntermexDailyReport(
        agency="1604 TEST (TX-3600)",
        report_date=date(2026, 5, 1),
        giros=[IntermexTxnRow(
            section="giros", confirm_number="8950",
            send_amount=288.12, fee=10.0, federal_tax=2.88,
            total_collected=301.0, cashier="CASAGRA",
            cancelled=False, replacement=False, reconciles=True,
        )],
        money_orders=[],
        bill_payments=[],
        giros_totals=SectionTotals(
            count=1, processed=1, voided=0,
            amount=288.12, fees=10.0, balance=301.0,
        ),
    )
    monkeypatch.setattr(
        "api.Modules.ReportImport.Controllers.parse_intermex_pdf",
        lambda data: fake,
    )

    token = _login_admin_token(client, test_store_id)
    resp = client.post(
        "/api/v2/report-import/intermex/parse",
        json={"content_base64": _b64(b"%PDF-1.4 fake"), "filename": "r.pdf"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["agency"] == "1604 TEST (TX-3600)"
    assert body["report_date"] == "2026-05-01"
    assert body["all_reconcile"] is True
    assert len(body["giros"]) == 1
    g = body["giros"][0]
    assert g["confirm_number"] == "8950"
    assert (g["send_amount"], g["fee"], g["federal_tax"], g["total_collected"]) == (
        288.12, 10.0, 2.88, 301.0,
    )
    assert body["giros_totals"]["balance"] == 301.0
