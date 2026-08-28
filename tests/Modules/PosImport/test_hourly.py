"""Hourly sales (G-3): parser hour extraction, live staging
increments, commit-time rebuild, and the dashboard block.

The invariants under test:
  * ``event_hour`` comes from <EventDateTime> when present, falls
    back to the JournalHeader's <BeginTime>, and is None when the
    file carries no timestamp (day totals unaffected either way),
  * each staged sale/refund increments its store-level hour bucket
    live; duplicate uploads never double-count,
  * committing a day REBUILDS its buckets from the staged
    originals (self-healing, idempotent),
  * the admin dashboard's sales block carries the two most recent
    hourly days as the chart payload.
"""
from tests.Modules.PosImport.test_agent import (
    _admin, _agent_upload, _headers, _issue_key,
)
from tests.Modules.PosImport.test_ingest import _map_codes, _mk_department
from tests.Modules.PosImport.test_naxml import _sale
from tests._app import db, db_session


def _buckets(store_id, day_iso):
    from datetime import date as _date

    from api.Modules.DayClose.Models import HourlySale
    with db_session():
        rows = (
            db.session.query(HourlySale)
            .filter_by(
                store_id=store_id,
                report_date=_date.fromisoformat(day_iso),
            )
            .all()
        )
        return {int(r.hour): int(r.amount_cents) for r in rows}


def test_parser_event_hour_sources():
    from api.Modules.PosImport.Services.naxml import parse_pjr

    # <EventDateTime> wins.
    ev = parse_pjr(_sale(event_dt="2024-10-14T13:45:12"))
    assert ev.event_hour == 13

    # Falls back to the JournalHeader's <BeginTime>.
    doc = _sale().replace(
        "<BeginDate>2024-10-13</BeginDate>",
        "<BeginDate>2024-10-13</BeginDate><BeginTime>07:02:11</BeginTime>",
    )
    assert parse_pjr(doc).event_hour == 7

    # No timestamp anywhere → None (chart mutes, totals intact).
    assert parse_pjr(_sale()).event_hour is None


def test_staging_increments_and_commit_rebuilds(client, test_store_id):
    h = _admin(client, test_store_id)
    key = _issue_key(client, h)["key"]
    dept = _mk_department(client, h, "Misc H1")
    _map_codes(client, h, {"17": dept["id"]})

    # Two sales in hour 13, one in hour 20 — buckets sum live.
    _agent_upload(client, key, "H1-001.xml", _sale(
        business_date="2025-01-10", event_dt="2025-01-10T13:05:00",
    ))
    _agent_upload(client, key, "H1-002.xml", _sale(
        business_date="2025-01-10", event_dt="2025-01-10T13:40:00",
    ))
    _agent_upload(client, key, "H1-003.xml", _sale(
        business_date="2025-01-10", event_dt="2025-01-10T20:01:00",
    ))
    # Duplicate filename → no double count.
    _agent_upload(client, key, "H1-001.xml", _sale(
        business_date="2025-01-10", event_dt="2025-01-10T13:05:00",
    ))
    # net_cents is pre-tax sales (2.99/event) — same basis as
    # the booked gross_sales.
    assert _buckets(test_store_id, "2025-01-10") == {
        13: 598, 20: 299,
    }

    # Day rolls (G-1 auto-commit fires) → rebuild produces the
    # same buckets — idempotent with the live increments.
    _agent_upload(client, key, "H1-D2-001.xml", _sale(
        business_date="2025-01-11", event_dt="2025-01-11T06:00:00",
    ))
    assert _buckets(test_store_id, "2025-01-10") == {
        13: 598, 20: 299,
    }

    # Manual re-commit also rebuilds, not doubles.
    resp = client.post(
        "/api/v2/posimport/staged/commit", headers=h,
        json={"day": "2025-01-10"},
    )
    assert resp.status_code == 200, resp.text
    assert _buckets(test_store_id, "2025-01-10") == {
        13: 598, 20: 299,
    }


def test_dashboard_hourly_block(client, test_store_id):
    from datetime import date, timedelta

    from api.Modules.DayClose.Models import HourlySale
    from api.Modules.Tenancy.Models import Store
    from tests.conftest import login_admin

    with db_session():
        db.session.get(Store, test_store_id).business_type = "cstore"
        today = date.today()
        for day, hour, cents in [
            (today, 9, 500_00),
            (today, 17, 900_00),
            (today - timedelta(days=1), 9, 400_00),
        ]:
            db.session.add(HourlySale(
                store_id=test_store_id, report_date=day, hour=hour,
                amount_cents=cents,
            ))
        db.session.commit()

    token = login_admin(client, test_store_id)
    sales = client.get(
        "/api/v2/dashboard/summary",
        headers=_headers(token),
    ).json()["sales"]
    hourly = sales["hourly"]
    assert hourly is not None
    assert hourly["current_date"] == date.today().isoformat()
    assert hourly["current"][9] == 500.0
    assert hourly["current"][17] == 900.0
    assert hourly["current_total"] == 1400.0
    assert hourly["previous"][9] == 400.0
    assert hourly["previous_total"] == 400.0
