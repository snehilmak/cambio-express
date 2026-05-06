"""Unit tests for Reports.Services.sales — sales_by_company,
sales_by_service, by_destination_country, top_recipients.

These call the service functions directly with a real DB session
(no HTTP, no Flask). Same coverage axis as the legacy data fns
they replace; this gives us the equivalence guarantee the
strangler fig depends on.
"""
from datetime import date


def _seed_transfer(store_id, *, send_amount=100.0, fee=2.0,
                    federal_tax=1.0, company="Intermex",
                    service_type="Money Transfer", country="MX",
                    recipient_name="R", status="Sent"):
    from app import Transfer, db
    t = Transfer(
        store_id=store_id,
        send_date=date.today(),
        company=company,
        service_type=service_type,
        sender_name="S",
        recipient_name=recipient_name,
        country=country,
        confirm_number=f"X{send_amount}",
        send_amount=send_amount,
        fee=fee,
        federal_tax=federal_tax,
        status=status,
    )
    db.session.add(t); db.session.commit()
    return t.id


def _today():
    return date.today()


def test_sales_by_company_renames_key_and_sorts_by_sent_desc(test_store_id):
    from app import app as flask_app, db
    today = _today()
    with flask_app.app_context():
        _seed_transfer(test_store_id, send_amount=100.0, company="Intermex")
        _seed_transfer(test_store_id, send_amount=500.0, company="Maxi")
        _seed_transfer(test_store_id, send_amount=200.0, company="Maxi")

        from api.Modules.Reports.Services import sales_by_company
        rows, totals = sales_by_company(db.session, [test_store_id], today, today)

    # Sort: Maxi (700) before Intermex (100).
    assert [r["company"] for r in rows] == ["Maxi", "Intermex"]
    assert rows[0]["sent"] == 700.0
    assert rows[0]["count"] == 2
    assert totals["sent"] == 800.0


def test_sales_by_company_handles_empty_company(test_store_id):
    """Legacy rows with no company tag get the `"(no company)"`
    bucket instead of disappearing — the totals must match."""
    from app import app as flask_app, db
    today = _today()
    with flask_app.app_context():
        _seed_transfer(test_store_id, send_amount=100.0, company="")
        from api.Modules.Reports.Services import sales_by_company
        rows, totals = sales_by_company(db.session, [test_store_id], today, today)
    assert rows[0]["company"] == "(no company)"
    assert totals["sent"] == 100.0


def test_sales_by_service_groups_by_service_type(test_store_id):
    from app import app as flask_app, db
    today = _today()
    with flask_app.app_context():
        _seed_transfer(test_store_id, send_amount=300.0,
                        service_type="Money Transfer")
        _seed_transfer(test_store_id, send_amount=50.0,
                        service_type="Bill Payment")

        from api.Modules.Reports.Services import sales_by_service
        rows, _ = sales_by_service(db.session, [test_store_id], today, today)
    types = {r["service_type"] for r in rows}
    assert types == {"Money Transfer", "Bill Payment"}


def test_by_destination_country_renames_key(test_store_id):
    from app import app as flask_app, db
    today = _today()
    with flask_app.app_context():
        _seed_transfer(test_store_id, send_amount=100.0, country="MX")
        _seed_transfer(test_store_id, send_amount=200.0, country="GT")

        from api.Modules.Reports.Services import by_destination_country
        rows, _ = by_destination_country(db.session, [test_store_id], today, today)
    countries = {r["country"] for r in rows}
    assert countries == {"MX", "GT"}


def test_top_recipients_respects_limit(test_store_id):
    """Service returns only `limit` rows by sent desc; totals reflect
    EVERY group so percentages stay accurate."""
    from app import app as flask_app, db
    today = _today()
    with flask_app.app_context():
        for i in range(5):
            _seed_transfer(test_store_id, send_amount=100.0 * (i + 1),
                            recipient_name=f"R{i}")
        from api.Modules.Reports.Services import top_recipients
        rows, totals = top_recipients(
            db.session, [test_store_id], today, today, limit=2,
        )
    assert len(rows) == 2
    # Top 2 by sent: R4 (500), R3 (400).
    assert rows[0]["recipient"] == "R4"
    assert rows[0]["sent"] == 500.0
    assert rows[1]["recipient"] == "R3"
    # Totals reflect all 5: 100+200+300+400+500 = 1500.
    assert totals["sent"] == 1500.0


# ── Legacy-shim equivalence ─────────────────────────────────


def test_legacy_shims_delegate_to_services(test_store_id):
    """The legacy `_sales_by_*_data` fns in app.py are now 2-line
    delegators. End-to-end equivalence: same inputs produce identical
    output through both surfaces, until the legacy callers migrate
    too (PR 5)."""
    from app import app as flask_app, db
    today = _today()
    with flask_app.app_context():
        _seed_transfer(test_store_id, send_amount=100.0, company="Intermex",
                        service_type="Money Transfer", country="MX",
                        recipient_name="Maria")
        _seed_transfer(test_store_id, send_amount=200.0, company="Maxi",
                        service_type="Top Up", country="GT",
                        recipient_name="Carlos")

        from app import (
            _sales_by_company_data, _sales_by_service_data,
            _by_destination_country_data, _top_recipients_data,
        )
        from api.Modules.Reports.Services import (
            sales_by_company, sales_by_service,
            by_destination_country, top_recipients,
        )

        for legacy_fn, service_fn in [
            (_sales_by_company_data, sales_by_company),
            (_sales_by_service_data, sales_by_service),
            (_by_destination_country_data, by_destination_country),
        ]:
            l_rows, l_totals = legacy_fn([test_store_id], today, today)
            s_rows, s_totals = service_fn(db.session, [test_store_id], today, today)
            assert l_rows == s_rows, f"{service_fn.__name__} drift"
            assert l_totals == s_totals

        # top_recipients takes a `limit` kwarg.
        l_rows, l_totals = _top_recipients_data([test_store_id], today, today, limit=10)
        s_rows, s_totals = top_recipients(
            db.session, [test_store_id], today, today, limit=10,
        )
        assert l_rows == s_rows
        assert l_totals == s_totals


# ── Pydantic schema sanity ──────────────────────────────────


def test_pydantic_response_schemas_validate_service_output(test_store_id):
    """Wire test: the service rows must validate as instances of
    the matching Pydantic model. If the service shape ever drifts
    from the schema, this test fails before we hit the controller
    in PR 4."""
    from app import app as flask_app, db
    today = _today()
    with flask_app.app_context():
        _seed_transfer(test_store_id, send_amount=100.0)
        from api.Modules.Reports.Services import sales_by_company
        from api.Modules.Reports.Requests import (
            CompanyRow, AggregatedTotals, SalesByCompanyResponse,
        )
        rows, totals = sales_by_company(db.session, [test_store_id], today, today)
        validated_rows = [CompanyRow(**r) for r in rows]
        validated_totals = AggregatedTotals(**totals)
        # Compose the full response — exercises the model_config
        # `extra="forbid"` setting too.
        resp = SalesByCompanyResponse(
            rows=validated_rows, totals=validated_totals,
        )
        assert len(resp.rows) == 1
        assert resp.rows[0].company == "Intermex"
        assert resp.totals.sent == 100.0
