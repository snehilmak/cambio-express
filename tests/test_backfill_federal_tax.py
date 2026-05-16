"""Tests for ``scripts/backfill_federal_tax.py``.

Covers:
* Dry-run (default) doesn't mutate.
* ``--commit`` writes the recomputed values.
* Rows already at the correct value are skipped (idempotent).
* Service-type / country exemptions are honored (so domestic +
  Bill Payment rows keep federal_tax=0).
"""
from __future__ import annotations

from datetime import date as _date

from scripts.backfill_federal_tax import main
from tests._app import db, db_session


def _seed_store(slug: str, *, federal_tax_rate: float = 0.01):
    from api.Modules.Tenancy.Models import Store
    s = Store(
        name=slug, slug=slug,
        email=f"{slug}@x.com", plan="basic",
        federal_tax_rate=federal_tax_rate,
    )
    db.session.add(s); db.session.commit()
    return s.id


def _seed_transfer(
    store_id: int, *,
    send_amount: float, federal_tax: float,
    service_type: str = "Money Transfer", country: str = "Mexico",
    employee_id: int = 1,
):
    from api.Modules.Transfers.Models import Transfer
    t = Transfer(
        store_id=store_id,
        send_date=_date.today(),
        company="Intermex",
        service_type=service_type,
        sender_name="Backfill Test Sender",
        sender_phone="5550000000",
        sender_phone_country="+1",
        sender_address="",
        send_amount=send_amount,
        fee=10.0,
        federal_tax=federal_tax,
        country=country,
        recipient_name="Backfill Test Recipient",
        recipient_phone="",
        confirm_number="",
        status="Sent",
        employee_id=employee_id,
    )
    db.session.add(t); db.session.commit()
    return t.id


def _seed_employee(store_id: int):
    """Transfer.employee_id has a FK constraint — use a real
    Employee row instead of a literal 1."""
    from api.Modules.Tenancy.Models import StoreEmployee
    emp = StoreEmployee(store_id=store_id, name="Backfill Tester", is_active=True)
    db.session.add(emp); db.session.commit()
    return emp.id


# ── Dry-run by default ──────────────────────────────────────


def test_dry_run_does_not_mutate(capsys):
    """Without ``--commit``, the script must NOT write. Existing
    ``federal_tax=0`` row stays at 0 even though the recompute
    would change it to ``send_amount * rate``."""
    from api.Modules.Transfers.Models import Transfer
    with db_session():
        store_id = _seed_store("backfill-dry-run")
        emp_id = _seed_employee(store_id)
        tid = _seed_transfer(
            store_id, send_amount=500.0, federal_tax=0.0,
            service_type="Money Transfer", country="Mexico",
            employee_id=emp_id,
        )

    rc = main([])  # no --commit
    assert rc == 0

    with db_session():
        t = db.session.get(Transfer, tid)
        assert t.federal_tax == 0.0  # unchanged in dry-run


# ── --commit writes ─────────────────────────────────────────


def test_commit_writes_recomputed_federal_tax():
    """With ``--commit``, a row with federal_tax=0 that SHOULD
    have federal_tax=send_amount*rate gets updated."""
    from api.Modules.Transfers.Models import Transfer
    with db_session():
        store_id = _seed_store(
            "backfill-commit", federal_tax_rate=0.01,
        )
        emp_id = _seed_employee(store_id)
        tid = _seed_transfer(
            store_id, send_amount=500.0, federal_tax=0.0,
            service_type="Money Transfer", country="Mexico",
            employee_id=emp_id,
        )

    rc = main(["--commit"])
    assert rc == 0

    with db_session():
        t = db.session.get(Transfer, tid)
        # 500 * 0.01 = 5.00, rounded to cents.
        assert t.federal_tax == 5.00


# ── Service-type exemptions ─────────────────────────────────


def test_bill_payment_stays_zero(capsys):
    """Bill Payment / Top Up / Recharge are tax-exempt per
    CLAUDE.md invariant #9. The backfill must NOT add tax to
    those rows even on --commit."""
    from api.Modules.Transfers.Models import Transfer
    with db_session():
        store_id = _seed_store("backfill-exempt")
        emp_id = _seed_employee(store_id)
        tid = _seed_transfer(
            store_id, send_amount=200.0, federal_tax=0.0,
            service_type="Bill Payment", country="Mexico",
            employee_id=emp_id,
        )

    rc = main(["--commit"])
    assert rc == 0

    with db_session():
        t = db.session.get(Transfer, tid)
        assert t.federal_tax == 0.0


# ── Domestic recipient stays zero ───────────────────────────


def test_domestic_country_stays_zero():
    """Money Transfer with country=United States is domestic →
    federal_tax = 0. Backfill mustn't tax domestic transfers."""
    from api.Modules.Transfers.Models import Transfer
    with db_session():
        store_id = _seed_store("backfill-domestic")
        emp_id = _seed_employee(store_id)
        tid = _seed_transfer(
            store_id, send_amount=200.0, federal_tax=0.0,
            service_type="Money Transfer", country="United States",
            employee_id=emp_id,
        )

    rc = main(["--commit"])
    assert rc == 0

    with db_session():
        t = db.session.get(Transfer, tid)
        assert t.federal_tax == 0.0


# ── Idempotency ─────────────────────────────────────────────


def test_already_correct_row_is_noop():
    """A row whose federal_tax is already the right value gets
    skipped — running the backfill twice doesn't double-count
    or drift the totals."""
    from api.Modules.Transfers.Models import Transfer
    with db_session():
        store_id = _seed_store("backfill-idempotent")
        emp_id = _seed_employee(store_id)
        tid = _seed_transfer(
            store_id, send_amount=500.0, federal_tax=5.00,  # already correct
            service_type="Money Transfer", country="Mexico",
            employee_id=emp_id,
        )

    rc = main(["--commit"])
    assert rc == 0
    rc = main(["--commit"])  # second pass — still no-op
    assert rc == 0

    with db_session():
        t = db.session.get(Transfer, tid)
        assert t.federal_tax == 5.00
