"""Unit tests for Transfers.Repositories — list_with_filters,
get_by_id_in_stores, TransferFilters.from_query.

Mirrors the legacy `/transfers` route's filter + sort + pagination
behavior. No HTTP, no Flask request context — just the repository
helpers against a live SQLAlchemy session.
"""
from datetime import date, timedelta
from tests._app import db, db_session


def _seed_transfer(store_id, *, send_date=None, send_amount=100.0,
                    fee=2.0, federal_tax=1.0, company="Intermex",
                    service_type="Money Transfer", country="MX",
                    sender_name="S", recipient_name="R",
                    confirm_number=None, status="Sent",
                    batch_id=""):
    from api.Modules.Transfers.Models import Transfer
    from tests._app import db
    t = Transfer(
        store_id=store_id,
        send_date=send_date or date.today(),
        company=company,
        service_type=service_type,
        sender_name=sender_name,
        recipient_name=recipient_name,
        country=country,
        confirm_number=confirm_number or f"X{send_amount}-{recipient_name}",
        send_amount=send_amount,
        fee=fee,
        federal_tax=federal_tax,
        status=status,
        batch_id=batch_id,
    )
    db.session.add(t); db.session.commit()
    return t.id


# ── TransferFilters.from_query ──────────────────────────────


def test_filters_parses_dates():
    from api.Modules.Transfers.Repositories import TransferFilters
    f = TransferFilters.from_query({
        "date_from": "2026-01-01",
        "date_to": "2026-12-31",
    })
    assert f.date_from == date(2026, 1, 1)
    assert f.date_to == date(2026, 12, 31)


def test_filters_drops_malformed_dates():
    """The legacy route silently skips malformed dates rather than
    500ing — we mirror that."""
    from api.Modules.Transfers.Repositories import TransferFilters
    f = TransferFilters.from_query({
        "date_from": "not-a-date",
        "date_to": "",
    })
    assert f.date_from is None
    assert f.date_to is None


def test_filters_strips_whitespace_on_text_fields():
    from api.Modules.Transfers.Repositories import TransferFilters
    f = TransferFilters.from_query({"sender": "  alice  "})
    assert f.sender == "alice"


def test_filters_normalizes_sort_dir():
    """Unknown `dir` values fall back to `desc` so a malformed URL
    can't pick a random direction."""
    from api.Modules.Transfers.Repositories import TransferFilters
    f = TransferFilters.from_query({"sort": "send_date", "dir": "garbage"})
    assert f.sort_dir == "desc"
    f = TransferFilters.from_query({"sort": "send_date", "dir": "ASC"})
    assert f.sort_dir == "asc"


# ── list_with_filters ───────────────────────────────────────


def test_list_returns_rows_and_total(test_store_id):
    from tests._app import db
    from api.Modules.Transfers.Repositories import (
        TransferFilters, list_with_filters,
    )
    with db_session():
        for i in range(3):
            _seed_transfer(test_store_id, send_amount=100.0 * (i + 1))
        rows, total = list_with_filters(
            db.session, [test_store_id], TransferFilters(),
        )
    assert total == 3
    assert len(rows) == 3


def test_list_filters_by_company(test_store_id):
    from tests._app import db
    from api.Modules.Transfers.Repositories import (
        TransferFilters, list_with_filters,
    )
    with db_session():
        _seed_transfer(test_store_id, company="Intermex")
        _seed_transfer(test_store_id, company="Maxi")
        rows, total = list_with_filters(
            db.session, [test_store_id],
            TransferFilters(company="Intermex"),
        )
    assert total == 1
    assert rows[0].company == "Intermex"


def test_list_filters_by_status(test_store_id):
    from tests._app import db
    from api.Modules.Transfers.Repositories import (
        TransferFilters, list_with_filters,
    )
    with db_session():
        _seed_transfer(test_store_id, status="Sent")
        _seed_transfer(test_store_id, status="Cancelled",
                        confirm_number="X-CN")
        rows, _ = list_with_filters(
            db.session, [test_store_id],
            TransferFilters(status="Cancelled"),
        )
    assert len(rows) == 1
    assert rows[0].status == "Cancelled"


def test_list_filters_by_date_range(test_store_id):
    from tests._app import db
    from api.Modules.Transfers.Repositories import (
        TransferFilters, list_with_filters,
    )
    today = date.today()
    yesterday = today - timedelta(days=1)
    last_week = today - timedelta(days=7)
    with db_session():
        _seed_transfer(test_store_id, send_date=last_week,
                        confirm_number="X-LW")
        _seed_transfer(test_store_id, send_date=yesterday,
                        confirm_number="X-Y")
        _seed_transfer(test_store_id, send_date=today,
                        confirm_number="X-T")
        rows, total = list_with_filters(
            db.session, [test_store_id],
            TransferFilters(date_from=yesterday, date_to=today),
        )
    assert total == 2
    confirms = {r.confirm_number for r in rows}
    assert confirms == {"X-Y", "X-T"}


def test_list_global_search_q_matches_multiple_columns(test_store_id):
    """The `q=` global search hits sender, recipient, confirm,
    country, batch — anything string-y."""
    from tests._app import db
    from api.Modules.Transfers.Repositories import (
        TransferFilters, list_with_filters,
    )
    with db_session():
        _seed_transfer(test_store_id, sender_name="Alice",
                        confirm_number="X-Alice-Send")
        _seed_transfer(test_store_id, recipient_name="Alice",
                        confirm_number="X-Alice-Recv")
        _seed_transfer(test_store_id, batch_id="ALICE-2026",
                        confirm_number="X-Alice-Batch")
        _seed_transfer(test_store_id, sender_name="Bob",
                        confirm_number="X-Bob")
        rows, total = list_with_filters(
            db.session, [test_store_id], TransferFilters(q="alice"),
        )
    confirms = {r.confirm_number for r in rows}
    # Three rows match: sender, recipient, and batch_id all contain "alice".
    assert total == 3
    assert confirms == {"X-Alice-Send", "X-Alice-Recv", "X-Alice-Batch"}


def test_list_orders_by_send_date_desc_by_default(test_store_id):
    from tests._app import db
    from api.Modules.Transfers.Repositories import (
        TransferFilters, list_with_filters,
    )
    today = date.today()
    yesterday = today - timedelta(days=1)
    with db_session():
        _seed_transfer(test_store_id, send_date=yesterday,
                        confirm_number="X-Y")
        _seed_transfer(test_store_id, send_date=today,
                        confirm_number="X-T")
        rows, _ = list_with_filters(
            db.session, [test_store_id], TransferFilters(),
        )
    assert rows[0].confirm_number == "X-T"
    assert rows[1].confirm_number == "X-Y"


def test_list_respects_explicit_sort(test_store_id):
    from tests._app import db
    from api.Modules.Transfers.Repositories import (
        TransferFilters, list_with_filters,
    )
    with db_session():
        _seed_transfer(test_store_id, send_amount=500.0,
                        confirm_number="X-500")
        _seed_transfer(test_store_id, send_amount=100.0,
                        confirm_number="X-100")
        rows, _ = list_with_filters(
            db.session, [test_store_id],
            TransferFilters(sort_slug="amount", sort_dir="asc"),
        )
    assert rows[0].send_amount == 100.0
    assert rows[1].send_amount == 500.0


def test_list_falls_back_when_sort_slug_invalid(test_store_id):
    """Bad slug → default ordering (send_date desc), not a random column."""
    from tests._app import db
    from api.Modules.Transfers.Repositories import (
        TransferFilters, list_with_filters,
    )
    today = date.today()
    yesterday = today - timedelta(days=1)
    with db_session():
        _seed_transfer(test_store_id, send_date=yesterday,
                        confirm_number="X-Y")
        _seed_transfer(test_store_id, send_date=today,
                        confirm_number="X-T")
        rows, _ = list_with_filters(
            db.session, [test_store_id],
            TransferFilters(sort_slug="garbage"),
        )
    # Default ordering: today first.
    assert rows[0].confirm_number == "X-T"


def test_list_paginates(test_store_id):
    from tests._app import db
    from api.Modules.Transfers.Repositories import (
        TransferFilters, list_with_filters,
    )
    with db_session():
        for i in range(5):
            _seed_transfer(test_store_id, send_amount=100.0 * (i + 1))
        rows, total = list_with_filters(
            db.session, [test_store_id], TransferFilters(),
            page=1, per_page=2,
        )
    assert total == 5
    assert len(rows) == 2


def test_list_clamps_out_of_range_page(test_store_id):
    """Asking for page 99 of a 5-row list returns the last page,
    not an empty list — matches the legacy route's behavior."""
    from tests._app import db
    from api.Modules.Transfers.Repositories import (
        TransferFilters, list_with_filters,
    )
    with db_session():
        for i in range(5):
            _seed_transfer(test_store_id, send_amount=100.0 * (i + 1))
        rows, _ = list_with_filters(
            db.session, [test_store_id], TransferFilters(),
            page=99, per_page=2,
        )
    # Page 3 has 1 row (5 total, 2 per page → pages: 2, 2, 1).
    assert len(rows) == 1


def test_list_isolates_other_stores(test_store_id):
    from tests._app import db
    from api.Modules.Transfers.Repositories import (
        TransferFilters, list_with_filters,
    )
    from api.Modules.Tenancy.Models import Store
    with db_session():
        s2 = Store(name="Other", slug="other-tx",
                    email="o@x.com", plan="trial")
        db.session.add(s2); db.session.commit()
        sid2 = s2.id
        _seed_transfer(test_store_id, confirm_number="X-Mine")
        _seed_transfer(sid2, confirm_number="X-Theirs")
        rows, total = list_with_filters(
            db.session, [test_store_id], TransferFilters(),
        )
    assert total == 1
    assert rows[0].confirm_number == "X-Mine"


def test_list_returns_empty_for_empty_store(test_store_id):
    from tests._app import db
    from api.Modules.Transfers.Repositories import (
        TransferFilters, list_with_filters,
    )
    with db_session():
        rows, total = list_with_filters(
            db.session, [test_store_id], TransferFilters(),
        )
    assert rows == []
    assert total == 0


# ── get_by_id_in_stores ─────────────────────────────────────


def test_get_by_id_returns_row_in_scope(test_store_id):
    from tests._app import db
    from api.Modules.Transfers.Repositories import get_by_id_in_stores
    with db_session():
        tid = _seed_transfer(test_store_id, send_amount=100.0)
        t = get_by_id_in_stores(db.session, tid, [test_store_id])
    assert t is not None
    assert t.id == tid


def test_get_by_id_returns_none_outside_scope(test_store_id):
    """Cross-tenant lookup must return None (callers translate to 404)."""
    from api.Modules.Tenancy.Models import Store
    from tests._app import db
    from api.Modules.Transfers.Repositories import get_by_id_in_stores
    with db_session():
        s2 = Store(name="Other", slug="other-scope",
                    email="o2@x.com", plan="trial")
        db.session.add(s2); db.session.commit()
        sid2 = s2.id
        tid = _seed_transfer(sid2, send_amount=100.0)
        t = get_by_id_in_stores(db.session, tid, [test_store_id])
    assert t is None
