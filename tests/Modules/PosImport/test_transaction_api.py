"""Transaction browsing endpoints (G-6).

The list and detail routes over ``pos_transaction``. Synthetic
fixtures only — never real Gilbarco journal data.

The load-bearing assertions here are about the void: a cancelled
line must be VISIBLE on the detail (that is why the screen exists)
and must never reach a money total (that is why it is dangerous).
"""
from datetime import date, datetime

import pytest

from api.Modules.PosImport.Models import (
    PosTransaction, PosTransactionLine, PosTransactionTender,
)
from tests._app import db, db_session
from tests.conftest import login_admin, make_employee_client

DAY = date(2025, 12, 8)


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _admin(client, test_store_id):
    return _headers(login_admin(client, test_store_id))


def _seed(store_id, *, source_file, transaction_no, grand_cents,
          voided=False, kind="sale", register_id="1",
          cashier_id="3", day=DAY, description="CANDY BAR"):
    """One ticket with a real line, a tender, and optionally a
    voided line whose amount is deliberately large — if it ever
    leaks into a total the assertion will be unmissable."""
    txn = PosTransaction(
        store_id=store_id, business_date=day, source_file=source_file,
        kind=kind, register_id=register_id, cashier_id=cashier_id,
        till_id="0318", transaction_no=transaction_no,
        event_sequence_id="7",
        receipt_at=datetime(day.year, day.month, day.day, 13, 31, 38),
        gross_cents=grand_cents, net_cents=grand_cents, tax_cents=0,
        grand_total_cents=grand_cents, has_voided_line=voided,
    )
    db.session.add(txn)
    db.session.flush()
    db.session.add(PosTransactionLine(
        transaction_id=txn.id, store_id=store_id, business_date=day,
        line_seq=2, status="normal", pos_code="222222222222",
        description=description, quantity=1.0, amount_cents=grand_cents,
        actual_price_cents=grand_cents, merchandise_code="10",
    ))
    if voided:
        db.session.add(PosTransactionLine(
            transaction_id=txn.id, store_id=store_id, business_date=day,
            line_seq=1, status="cancel", pos_code="111111111111",
            description="VOIDED PREMIUM ITEM", quantity=1.0,
            amount_cents=500_00, actual_price_cents=500_00,
            merchandise_code="10",
        ))
    db.session.add(PosTransactionTender(
        transaction_id=txn.id, store_id=store_id, business_date=day,
        code="cash", sub_code="generic", amount_cents=grand_cents,
        is_change=False,
    ))
    db.session.flush()
    return txn.id


@pytest.fixture()
def seeded(client, test_store_id):
    with db_session():
        plain = _seed(
            test_store_id, source_file="PJR-1.xml",
            transaction_no="8945", grand_cents=300,
        )
        with_void = _seed(
            test_store_id, source_file="PJR-2.xml",
            transaction_no="8946", grand_cents=1200, voided=True,
            description="COFFEE LARGE",
        )
        db.session.commit()
    return {"plain": plain, "with_void": with_void}


# ── List ────────────────────────────────────────────────────


def test_list_returns_tickets_with_range_totals(
    client, test_store_id, seeded,
):
    h = _admin(client, test_store_id)
    resp = client.get(
        "/api/v2/posimport/transactions"
        f"?start={DAY.isoformat()}&end={DAY.isoformat()}",
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    # $3.00 + $12.00 — and emphatically NOT the $500 voided line.
    assert body["total_grand"] == pytest.approx(15.00)
    assert body["voided_count"] == 1
    by_no = {r["transaction_no"]: r for r in body["rows"]}
    assert by_no["8945"]["has_voided_line"] is False
    assert by_no["8946"]["has_voided_line"] is True
    # The voided ticket has two lines; the count includes the void
    # because the operator is being told the ticket has one.
    assert by_no["8946"]["item_count"] == 2


def test_totals_cover_the_filtered_set_not_the_page(
    client, test_store_id, seeded,
):
    """A footer that only summed the visible page would disagree
    with the count printed beside it."""
    h = _admin(client, test_store_id)
    resp = client.get(
        "/api/v2/posimport/transactions"
        f"?start={DAY.isoformat()}&end={DAY.isoformat()}&per_page=1",
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["rows"]) == 1
    assert body["total"] == 2
    assert body["total_pages"] == 2
    assert body["total_grand"] == pytest.approx(15.00)


def test_voided_only_filter(client, test_store_id, seeded):
    h = _admin(client, test_store_id)
    resp = client.get(
        "/api/v2/posimport/transactions"
        f"?start={DAY.isoformat()}&end={DAY.isoformat()}&voided_only=true",
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert body["rows"][0]["transaction_no"] == "8946"


def test_search_matches_ticket_number_and_item_description(
    client, test_store_id, seeded,
):
    h = _admin(client, test_store_id)
    base = (
        "/api/v2/posimport/transactions"
        f"?start={DAY.isoformat()}&end={DAY.isoformat()}"
    )
    by_ticket = client.get(f"{base}&q=8945", headers=h).json()
    assert [r["transaction_no"] for r in by_ticket["rows"]] == ["8945"]

    # An item description only present on the second ticket.
    by_item = client.get(f"{base}&q=coffee", headers=h).json()
    assert [r["transaction_no"] for r in by_item["rows"]] == ["8946"]


def test_range_is_validated(client, test_store_id):
    h = _admin(client, test_store_id)
    backwards = client.get(
        "/api/v2/posimport/transactions?start=2025-12-08&end=2025-12-01",
        headers=h,
    )
    assert backwards.status_code == 422
    too_wide = client.get(
        "/api/v2/posimport/transactions?start=2024-01-01&end=2025-12-08",
        headers=h,
    )
    assert too_wide.status_code == 422
    malformed = client.get(
        "/api/v2/posimport/transactions?start=12/08/2025&end=2025-12-08",
        headers=h,
    )
    assert malformed.status_code == 422


# ── Detail ──────────────────────────────────────────────────


def test_detail_shows_the_void_but_excludes_it_from_money(
    client, test_store_id, seeded,
):
    """The point of the screen, and the trap in it, in one test."""
    h = _admin(client, test_store_id)
    resp = client.get(
        f"/api/v2/posimport/transactions/{seeded['with_void']}", headers=h,
    )
    assert resp.status_code == 200, resp.text
    txn = resp.json()["transaction"]

    statuses = {line["status"] for line in txn["lines"]}
    assert statuses == {"normal", "cancel"}, "the void must stay visible"
    voided = next(l for l in txn["lines"] if l["status"] == "cancel")
    assert voided["description"] == "VOIDED PREMIUM ITEM"
    assert voided["amount"] == pytest.approx(500.00)

    # …and the ticket's own money is untouched by it.
    assert txn["grand_total"] == pytest.approx(12.00)
    assert txn["has_voided_line"] is True
    assert [t["code"] for t in txn["tenders"]] == ["cash"]
    # Lines come back in register order.
    assert [l["line_seq"] for l in txn["lines"]] == [1, 2]


def test_detail_404s_for_another_stores_transaction(
    client, test_store_id, seeded,
):
    """Store scoping is the security property here — a ticket id is
    a small integer, so guessing one is trivial."""
    from api.Modules.Tenancy.Models import Store

    with db_session():
        other = Store(
            name="Other", slug="other-txn-store",
            email="other-txn@x.com", plan="basic",
        )
        db.session.add(other)
        db.session.commit()
        foreign = _seed(
            other.id, source_file="PJR-X.xml",
            transaction_no="9999", grand_cents=100,
        )
        db.session.commit()

    h = _admin(client, test_store_id)
    resp = client.get(
        f"/api/v2/posimport/transactions/{foreign}", headers=h,
    )
    assert resp.status_code == 404

    # The same scoping holds on the list.
    listed = client.get(
        "/api/v2/posimport/transactions"
        f"?start={DAY.isoformat()}&end={DAY.isoformat()}",
        headers=h,
    ).json()
    assert "9999" not in {r["transaction_no"] for r in listed["rows"]}


def test_detail_404s_for_an_unknown_id(client, test_store_id):
    h = _admin(client, test_store_id)
    assert client.get(
        "/api/v2/posimport/transactions/999999", headers=h,
    ).status_code == 404


# ── Permissions ─────────────────────────────────────────────


def test_cashier_can_read_tickets(client, test_store_id, seeded):
    """Deliberate: looking up "what was on ticket 4417?" is a
    reporting act, so it takes day_close.READ. Requiring the admin
    rights that BOOKING a day needs would put a routine customer
    question behind a manager."""
    emp_client, token = make_employee_client(test_store_id)
    resp = emp_client.get(
        "/api/v2/posimport/transactions"
        f"?start={DAY.isoformat()}&end={DAY.isoformat()}",
        headers=_headers(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 2

    detail = emp_client.get(
        f"/api/v2/posimport/transactions/{seeded['plain']}",
        headers=_headers(token),
    )
    assert detail.status_code == 200, detail.text


def test_anonymous_is_rejected(client, test_store_id, seeded):
    resp = client.get(
        "/api/v2/posimport/transactions"
        f"?start={DAY.isoformat()}&end={DAY.isoformat()}",
    )
    assert resp.status_code in (401, 403)
