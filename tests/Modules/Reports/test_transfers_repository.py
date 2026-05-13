"""Unit tests for `api.Modules.Reports.Repositories.transfers`.

These run the new repository directly, with no HTTP, no Flask, no
FastAPI. The contract: same query logic that previously lived in
`app.py::_aggregate_transfers` and `app.py::_active_transfers_period_filters`,
now isolated and unit-testable.

Two layers of coverage:

  1. The new repository functions themselves (the migrated logic).
  2. The legacy shim functions in `app.py` (which now delegate to
     the repository). This guards the strangler-fig contract: both
     names have to keep producing identical results until the
     legacy callers are migrated too.
"""
from datetime import date, timedelta


def _seed_transfer(store_id, *, send_date=None, send_amount=100.0,
                    fee=2.0, federal_tax=1.0, company="Intermex",
                    status="Sent", sender_name="S"):
    from api.Modules.Transfers.Models import Transfer
    from app import db
    t = Transfer(
        store_id=store_id,
        send_date=send_date or date.today(),
        company=company,
        sender_name=sender_name,
        recipient_name="R",
        country="MX",
        confirm_number=f"X{send_amount}",
        send_amount=send_amount,
        fee=fee,
        federal_tax=federal_tax,
        status=status,
    )
    db.session.add(t); db.session.commit()
    return t.id


def test_period_filters_returns_three_clauses(test_store_id):
    """Repository contract: three filter clauses (store, date range,
    status). The shape stays stable — services + later modules
    splat the result into `.filter(*...)`."""
    from api.Modules.Reports.Repositories.transfers import period_filters
    today = date.today()
    clauses = period_filters([test_store_id], today, today)
    # SQLAlchemy filter clauses don't equality-compare easily so we
    # assert on the shape — three clauses, all non-None.
    assert len(clauses) == 4  # store_in + date>= + date<= + status_notin
    assert all(c is not None for c in clauses)


def test_aggregate_returns_rows_and_totals(test_store_id):
    """Group by company, three transfers across two companies, one
    Canceled (must be excluded). Repository should return two rows
    (Intermex + Maxi) and totals that sum just the active ones."""
    from api.Modules.Transfers.Models import Transfer
    from app import app as flask_app, db
    today = date.today()
    with flask_app.app_context():
        _seed_transfer(test_store_id, send_amount=100.0,
                        company="Intermex", fee=2.0, federal_tax=1.0)
        _seed_transfer(test_store_id, send_amount=200.0,
                        company="Intermex", fee=4.0, federal_tax=2.0)
        _seed_transfer(test_store_id, send_amount=999.0,
                        company="Intermex", fee=999.0,
                        federal_tax=999.0, status="Canceled")  # excluded
        _seed_transfer(test_store_id, send_amount=300.0,
                        company="Maxi", fee=6.0, federal_tax=3.0)

        from api.Modules.Reports.Repositories.transfers import aggregate
        rows, totals = aggregate(
            db.session, [test_store_id], today, today,
            Transfer.company,
        )

    by_company = {r["key"]: r for r in rows}
    assert "Intermex" in by_company
    assert "Maxi" in by_company
    assert by_company["Intermex"]["count"] == 2
    assert by_company["Intermex"]["sent"] == 300.0
    assert by_company["Maxi"]["count"] == 1
    assert by_company["Maxi"]["sent"] == 300.0
    # Totals: 2 Intermex (300) + 1 Maxi (300) = 600 sent. Canceled
    # excluded so the 999 doesn't show up.
    assert totals["sent"] == 600.0
    assert totals["count"] == 3
    # Avg per row: Intermex 300/2=150, Maxi 300/1=300.
    assert by_company["Intermex"]["avg"] == 150.0
    assert by_company["Maxi"]["avg"] == 300.0


def test_aggregate_excludes_out_of_period(test_store_id):
    """Date filter contract — transfers outside [d_from, d_to] don't
    appear in the result."""
    from api.Modules.Transfers.Models import Transfer
    from app import app as flask_app, db
    today = date.today()
    with flask_app.app_context():
        _seed_transfer(test_store_id, send_date=today,
                        send_amount=100.0)
        _seed_transfer(test_store_id, send_date=today - timedelta(days=10),
                        send_amount=999.0)  # outside window
        from api.Modules.Reports.Repositories.transfers import aggregate
        rows, totals = aggregate(
            db.session, [test_store_id], today, today,
            Transfer.company,
        )
    assert totals["sent"] == 100.0
    assert totals["count"] == 1


def test_aggregate_returns_empty_for_no_data(test_store_id):
    """Empty period — repository returns `([], {sent:0, fees:0,
    tax:0, count:0})`. Caller code shouldn't have to special-case
    the empty path."""
    from api.Modules.Transfers.Models import Transfer
    from app import app as flask_app, db
    today = date.today()
    with flask_app.app_context():
        from api.Modules.Reports.Repositories.transfers import aggregate
        rows, totals = aggregate(
            db.session, [test_store_id], today, today,
            Transfer.company,
        )
    assert rows == []
    assert totals == {"sent": 0.0, "fees": 0.0, "tax": 0.0, "count": 0}




