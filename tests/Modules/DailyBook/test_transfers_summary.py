"""Unit tests for DailyBook.Services.transfers_summary —
aggregates Transfer rows by company for the daily book's
Money Transfers auto-fill view."""
from datetime import date


def _add_transfer(store_id, **kwargs):
    from app import Transfer, db
    defaults = {
        "company": "Intermex",
        "service_type": "Money Transfer",
        "sender_name": "Test Sender",
        "send_amount": 100.0,
        "fee": 5.0,
        "federal_tax": 1.0,
        "commission": 2.0,
        "status": "Sent",
    }
    defaults.update(kwargs)
    t = Transfer(store_id=store_id, **defaults)
    db.session.add(t); db.session.commit()
    return t.id


def test_summary_default_companies_when_no_transfers(test_store_id):
    """Empty day still returns one row per configured company so
    the React editor can render the auto-fill table consistently."""
    from app import app as flask_app, db
    from api.Modules.DailyBook.Services import summarize_transfers_for_day
    with flask_app.app_context():
        summary = summarize_transfers_for_day(
            db.session, test_store_id, date.today(),
        )
    assert summary.companies == ["Intermex", "Maxi", "Barri"]
    assert {r.company for r in summary.by_company} == {
        "Intermex", "Maxi", "Barri",
    }
    for r in summary.by_company:
        assert r.count == 0
        assert r.total == 0.0
    assert summary.grand_total == 0.0


def test_summary_aggregates_by_company(test_store_id):
    """One transfer per company → each bucket carries its row's
    amount + fees + federal_tax + commission."""
    from app import app as flask_app, db
    from api.Modules.DailyBook.Services import summarize_transfers_for_day
    today = date.today()
    with flask_app.app_context():
        _add_transfer(test_store_id, company="Intermex", send_date=today,
                      send_amount=100, fee=5, federal_tax=1, commission=2)
        _add_transfer(test_store_id, company="Maxi", send_date=today,
                      send_amount=200, fee=10, federal_tax=2, commission=3)
        summary = summarize_transfers_for_day(
            db.session, test_store_id, today,
        )
    by_name = {r.company: r for r in summary.by_company}
    assert by_name["Intermex"].count == 1
    assert by_name["Intermex"].amount == 100
    assert by_name["Intermex"].total == 108  # 100 + 5 + 1 + 2
    assert by_name["Maxi"].count == 1
    assert by_name["Maxi"].total == 215  # 200 + 10 + 2 + 3
    assert by_name["Barri"].count == 0  # configured but no rows
    assert summary.grand_total == 323  # 108 + 215


def test_summary_excludes_cancelled(test_store_id):
    """Cancelled transfers shouldn't poison the day's roll-up."""
    from app import app as flask_app, db
    from api.Modules.DailyBook.Services import summarize_transfers_for_day
    today = date.today()
    with flask_app.app_context():
        _add_transfer(test_store_id, company="Intermex", send_date=today,
                      send_amount=100, status="Sent")
        _add_transfer(test_store_id, company="Intermex", send_date=today,
                      send_amount=999, status="Cancelled")
        summary = summarize_transfers_for_day(
            db.session, test_store_id, today,
        )
    intermex = next(r for r in summary.by_company if r.company == "Intermex")
    assert intermex.count == 1
    assert intermex.amount == 100


def test_summary_carries_unknown_companies_alphabetically(test_store_id):
    """Historical Transfer rows with a company not in the current
    store config still surface — but after the configured list, in
    alphabetical order. Keeps the grand total honest."""
    from app import app as flask_app, db
    from api.Modules.DailyBook.Services import summarize_transfers_for_day
    today = date.today()
    with flask_app.app_context():
        _add_transfer(test_store_id, company="Zoom", send_date=today,
                      send_amount=50)
        _add_transfer(test_store_id, company="Ria", send_date=today,
                      send_amount=75)
        summary = summarize_transfers_for_day(
            db.session, test_store_id, today,
        )
    names = [r.company for r in summary.by_company]
    # Configured companies first (in their CSV order)
    assert names[:3] == ["Intermex", "Maxi", "Barri"]
    # Unknown companies after, alphabetically
    assert names[3:] == ["Ria", "Zoom"]
    assert summary.grand_total > 0
