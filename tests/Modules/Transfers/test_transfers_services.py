"""Unit tests for Transfers.Services — list_transfers + Pydantic schemas.

Service-layer tests run directly against the SQLAlchemy session;
HTTP-level integration tests for the future Controllers come in PR 12.
"""
from datetime import date, timedelta


def _seed_transfer(store_id, *, send_date=None, send_amount=100.0,
                    fee=2.0, federal_tax=1.0, company="Intermex",
                    service_type="Money Transfer", country="MX",
                    recipient_name="R", confirm_number=None,
                    status="Sent"):
    from api.Modules.Transfers.Models import Transfer
    from tests._app import db
    t = Transfer(
        store_id=store_id,
        send_date=send_date or date.today(),
        company=company,
        service_type=service_type,
        sender_name="S",
        recipient_name=recipient_name,
        country=country,
        confirm_number=confirm_number or f"X{send_amount}-{recipient_name}",
        send_amount=send_amount,
        fee=fee,
        federal_tax=federal_tax,
        status=status,
    )
    db.session.add(t); db.session.commit()
    return t.id


# ── list_transfers ──────────────────────────────────────────


def test_list_transfers_returns_page_object_with_meta(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.Transfers.Repositories import TransferFilters
    from api.Modules.Transfers.Services import list_transfers
    with flask_app.app_context():
        for i in range(3):
            _seed_transfer(test_store_id, send_amount=100.0)
        page = list_transfers(
            db.session, [test_store_id], TransferFilters(),
        )
    assert page.total == 3
    assert page.page == 1
    assert page.per_page == 50
    assert page.total_pages == 1
    assert len(page.rows) == 3


def test_list_transfers_page_amount_sums_send_fee_tax(test_store_id):
    """`page_amount` = Σ (send_amount + fee + federal_tax) for visible
    rows. Mirrors the legacy `/transfers` route's header total."""
    from tests._app import app as flask_app, db
    from api.Modules.Transfers.Repositories import TransferFilters
    from api.Modules.Transfers.Services import list_transfers
    with flask_app.app_context():
        _seed_transfer(test_store_id, send_amount=100.0,
                        fee=2.0, federal_tax=1.0)
        _seed_transfer(test_store_id, send_amount=200.0,
                        fee=3.0, federal_tax=2.0)
        page = list_transfers(
            db.session, [test_store_id], TransferFilters(),
        )
    # 100+2+1 + 200+3+2 = 308
    assert page.page_amount == 308.0


def test_list_transfers_page_amount_only_counts_visible_rows(test_store_id):
    """When pagination splits the result, page_amount reflects only
    the rows on this page — that's the header the user sees."""
    from tests._app import app as flask_app, db
    from api.Modules.Transfers.Repositories import TransferFilters
    from api.Modules.Transfers.Services import list_transfers
    with flask_app.app_context():
        # 5 transfers: 100, 200, 300, 400, 500 (with 2 fee + 1 tax each).
        for i in range(5):
            _seed_transfer(
                test_store_id, send_amount=100.0 * (i + 1),
                fee=2.0, federal_tax=1.0,
            )
        # Default sort: send_date desc, then created_at desc — all
        # share the same date today, so created_at descending puts the
        # most-recently-inserted (500) on page 1.
        page = list_transfers(
            db.session, [test_store_id], TransferFilters(),
            page=1, per_page=2,
        )
    assert page.total == 5
    assert page.total_pages == 3
    assert len(page.rows) == 2
    # Page 1 has the two rows with the highest send_amount.
    page_sends = sorted(r.send_amount for r in page.rows)
    assert page_sends == [400.0, 500.0]
    # page_amount sums those two only.
    assert page.page_amount == (400 + 2 + 1) + (500 + 2 + 1)


def test_list_transfers_filters_passthrough(test_store_id):
    """Service must pass the filters dataclass to the repository."""
    from tests._app import app as flask_app, db
    from api.Modules.Transfers.Repositories import TransferFilters
    from api.Modules.Transfers.Services import list_transfers
    with flask_app.app_context():
        _seed_transfer(test_store_id, company="Intermex")
        _seed_transfer(test_store_id, company="Maxi")
        page = list_transfers(
            db.session, [test_store_id],
            TransferFilters(company="Maxi"),
        )
    assert page.total == 1
    assert page.rows[0].company == "Maxi"


def test_list_transfers_empty_set_safe(test_store_id):
    """Empty-store case: no rows, total 0, total_pages 1, page_amount 0."""
    from tests._app import app as flask_app, db
    from api.Modules.Transfers.Repositories import TransferFilters
    from api.Modules.Transfers.Services import list_transfers
    with flask_app.app_context():
        page = list_transfers(
            db.session, [test_store_id], TransferFilters(),
        )
    assert page.rows == []
    assert page.total == 0
    assert page.total_pages == 1
    assert page.page_amount == 0.0


def test_list_transfers_handles_null_fee_and_tax(test_store_id):
    """Legacy rows can have NULL fee/federal_tax — page_amount must
    treat them as zero, not crash on the addition."""
    from api.Modules.Transfers.Models import Transfer
    from tests._app import app as flask_app, db
    from api.Modules.Transfers.Repositories import TransferFilters
    from api.Modules.Transfers.Services import list_transfers
    with flask_app.app_context():
        _seed_transfer(test_store_id, send_amount=100.0)
        # Manually NULL out fee + tax to simulate a legacy row.
        t = db.session.query(Transfer).filter_by(
            store_id=test_store_id).first()
        t.fee = None
        t.federal_tax = None
        db.session.commit()
        page = list_transfers(
            db.session, [test_store_id], TransferFilters(),
        )
    assert page.page_amount == 100.0


# ── Pydantic schema sanity ──────────────────────────────────


# ── delete_transfer ─────────────────────────────────────────


def test_delete_transfer_removes_row(test_store_id):
    from api.Modules.Transfers.Models import Transfer
    from tests._app import app as flask_app, db
    from api.Modules.Transfers.Services import delete_transfer
    with flask_app.app_context():
        tid = _seed_transfer(test_store_id, send_amount=100.0)
        deleted = delete_transfer(db.session, tid, test_store_id)
        db.session.commit()
        assert deleted.send_amount == 100.0
        assert db.session.get(Transfer, tid) is None


def test_delete_transfer_cascades_audit_rows(test_store_id):
    """TransferAudit rows referencing the transfer must be removed
    before the transfer itself (the FK doesn't ON DELETE CASCADE)."""
    from api.Modules.Audit.Models import TransferAudit
    from tests._app import app as flask_app, db
    from api.Modules.Transfers.Services import delete_transfer
    with flask_app.app_context():
        tid = _seed_transfer(test_store_id, send_amount=100.0)
        # Seed a TransferAudit row pointing at this transfer
        a = TransferAudit(
            store_id=test_store_id, transfer_id=tid,
            user_id=None, employee_id=None, employee_name="",
            action="edit", summary="something",
        )
        db.session.add(a); db.session.commit()
        delete_transfer(db.session, tid, test_store_id)
        db.session.commit()
        # No audit rows for this transfer remain
        remaining = (
            db.session.query(TransferAudit)
              .filter_by(transfer_id=tid).count()
        )
        assert remaining == 0


def test_delete_transfer_raises_when_cross_store(test_store_id):
    from api.Modules.Tenancy.Models import Store
    from tests._app import app as flask_app, db
    from api.Modules.Transfers.Services import (
        TransferNotFoundError, delete_transfer,
    )
    import pytest
    with flask_app.app_context():
        s2 = Store(name="Other", slug="other-tx-del-svc",
                    email="o@x.com", plan="trial")
        db.session.add(s2); db.session.commit()
        tid = _seed_transfer(s2.id, send_amount=99.0)
        with pytest.raises(TransferNotFoundError):
            delete_transfer(db.session, tid, test_store_id)


def test_delete_transfer_raises_for_unknown_id(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.Transfers.Services import (
        TransferNotFoundError, delete_transfer,
    )
    import pytest
    with flask_app.app_context():
        with pytest.raises(TransferNotFoundError):
            delete_transfer(db.session, 99999, test_store_id)


# ── Pydantic schema sanity ──────────────────────────────────


def test_transfer_row_validates_service_output(test_store_id):
    """A row produced via the service should be paintable into the
    TransferRow Pydantic model. If the wire shape ever drifts from
    the model, this test fails before the controller does."""
    from tests._app import app as flask_app, db
    from api.Modules.Transfers.Repositories import TransferFilters
    from api.Modules.Transfers.Services import list_transfers
    from api.Modules.Transfers.Requests import (
        TransferRow, TransferListResponse,
    )
    with flask_app.app_context():
        _seed_transfer(test_store_id, send_amount=100.0,
                        fee=2.0, federal_tax=1.0,
                        company="Intermex", recipient_name="Maria")
        page = list_transfers(
            db.session, [test_store_id], TransferFilters(),
        )
        row = page.rows[0]
        validated = TransferRow(
            id=row.id,
            send_date=row.send_date.isoformat(),
            company=row.company,
            service_type=row.service_type or "Money Transfer",
            sender_name=row.sender_name,
            recipient_name=row.recipient_name or "",
            country=row.country or "",
            confirm_number=row.confirm_number or "",
            send_amount=row.send_amount,
            fee=row.fee or 0.0,
            federal_tax=row.federal_tax or 0.0,
            total_collected=row.total_collected,
            status=row.status,
            batch_id=row.batch_id or "",
            employee_name=row.employee_name or "",
        )
        resp = TransferListResponse(
            rows=[validated],
            total=page.total, page=page.page, per_page=page.per_page,
            total_pages=page.total_pages, page_amount=page.page_amount,
        )
    assert resp.rows[0].company == "Intermex"
    assert resp.total == 1
    assert resp.page_amount == 103.0
