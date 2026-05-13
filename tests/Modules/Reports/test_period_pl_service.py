"""Unit tests for Reports.Services.period_pl (PR 87)."""
from datetime import date

from api.Modules.DailyBook.Models import DailyReport
from api.Modules.Tenancy.Models import Store
from api.Modules.Transfers.Models import Transfer


def _add_store(db, *, slug="ppl-store"):
    s = Store(name=slug, slug=slug, plan="basic",
              email=f"{slug}@example.com")
    db.add(s); db.flush()
    return s


def _add_transfer(db, store_id, *, send_date, send_amount=100.0,
                   fee=2.0, federal_tax=1.0, status="Sent"):
    t = Transfer(
        store_id=store_id,
        send_date=send_date,
        company="Intermex",
        sender_name="x",
        send_amount=send_amount,
        fee=fee,
        federal_tax=federal_tax,
        status=status,
    )
    db.add(t); db.flush()
    return t


def _add_daily_report(db, store_id, *, report_date, **kwargs):
    r = DailyReport(
        store_id=store_id,
        report_date=report_date,
        **kwargs,
    )
    db.add(r); db.flush()
    return r


# ── shape ────────────────────────────────────────────────


def test_returns_rows_and_totals_tuple():
    """Service returns (rows, totals); rows is a list of dicts;
    totals is a dict with income / expenses / net / days."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import period_pl
    with flask_app.app_context():
        s = _add_store(db.session, slug="ppl-shape")
        rows, totals = period_pl(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert isinstance(rows, list)
        assert isinstance(totals, dict)
        assert set(totals) == {"income", "expenses", "net", "days"}


def test_rows_carry_label_section_amount():
    """Each row has label / section / amount keys."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import period_pl
    with flask_app.app_context():
        s = _add_store(db.session, slug="ppl-keys")
        rows, _ = period_pl(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        for r in rows:
            assert set(r) == {"label", "section", "amount"}
            assert r["section"] in {"Income", "Expenses"}


def test_includes_money_transfer_fees_income_row():
    """Every result includes a "Money Transfer Fees" income row,
    even when the period has zero fees."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import period_pl
    with flask_app.app_context():
        Transfer.query.delete()
        DailyReport.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="ppl-mtf")
        rows, _ = period_pl(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        labels = [r["label"] for r in rows]
        assert "Money Transfer Fees" in labels
        # And it lives in the Income section.
        mtf = next(r for r in rows if r["label"] == "Money Transfer Fees")
        assert mtf["section"] == "Income"
        assert mtf["amount"] == 0.0


# ── ordering ─────────────────────────────────────────────


def test_section_order_income_then_expenses():
    """Rows are ordered: all income rows, then all expense rows.
    The template depends on this contiguous grouping for headings."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import period_pl
    with flask_app.app_context():
        s = _add_store(db.session, slug="ppl-order")
        rows, _ = period_pl(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        sections = [r["section"] for r in rows]
        # Find where Income ends.
        first_expense = sections.index("Expenses")
        # No "Income" should appear after the first "Expenses" row.
        assert "Income" not in sections[first_expense:]


# ── aggregation correctness ──────────────────────────────


def test_aggregates_daily_report_income_columns():
    """Income lines sum the matching DailyReport column across the
    period."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import period_pl
    with flask_app.app_context():
        Transfer.query.delete()
        DailyReport.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="ppl-income")
        _add_daily_report(
            db.session, s.id, report_date=date(2026, 5, 5),
            taxable_sales=100.0, non_taxable=20.0,
        )
        _add_daily_report(
            db.session, s.id, report_date=date(2026, 5, 10),
            taxable_sales=50.0,
        )
        rows, totals = period_pl(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        by_label = {r["label"]: r for r in rows}
        assert by_label["Taxable Sales"]["amount"] == 150.0
        assert by_label["Non-Taxable Sales"]["amount"] == 20.0
        # income total = 150 + 20 + 0 (mtf) = 170
        assert totals["income"] == 170.0
        assert totals["expenses"] == 0.0
        assert totals["net"] == 170.0


def test_aggregates_daily_report_expense_columns():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import period_pl
    with flask_app.app_context():
        Transfer.query.delete()
        DailyReport.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="ppl-expense")
        _add_daily_report(
            db.session, s.id, report_date=date(2026, 5, 5),
            cash_purchases=30.0, payroll_expense=200.0,
        )
        rows, totals = period_pl(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        by_label = {r["label"]: r for r in rows}
        assert by_label["Cash Purchases"]["amount"] == 30.0
        assert by_label["Cash Payroll"]["amount"] == 200.0
        assert totals["expenses"] == 230.0


def test_money_transfer_fees_pulled_from_transfer_table():
    """MTF income row sums Transfer.fee for active transfers in the
    period — it does NOT live on DailyReport."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import period_pl
    with flask_app.app_context():
        Transfer.query.delete()
        DailyReport.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="ppl-mtf-sum")
        _add_transfer(
            db.session, s.id, send_date=date(2026, 5, 10),
            fee=5.0,
        )
        _add_transfer(
            db.session, s.id, send_date=date(2026, 5, 15),
            fee=7.0,
        )
        rows, totals = period_pl(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        by_label = {r["label"]: r for r in rows}
        assert by_label["Money Transfer Fees"]["amount"] == 12.0
        # income = 0 (no DailyReport) + 12 (fees) = 12
        assert totals["income"] == 12.0


def test_net_is_income_minus_expenses():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import period_pl
    with flask_app.app_context():
        Transfer.query.delete()
        DailyReport.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="ppl-net")
        _add_daily_report(
            db.session, s.id, report_date=date(2026, 5, 5),
            taxable_sales=500.0, cash_purchases=200.0,
        )
        _add_transfer(
            db.session, s.id, send_date=date(2026, 5, 10),
            fee=50.0,
        )
        _, totals = period_pl(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        # income = 500 + 50 = 550; expenses = 200; net = 350
        assert totals["income"] == 550.0
        assert totals["expenses"] == 200.0
        assert totals["net"] == 350.0


def test_days_counts_daily_report_rows_in_window():
    """`totals["days"]` is the number of DailyReport rows in the
    window — NOT the date span (so a missing day doesn't inflate
    the denominator if the template ever divides by it)."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import period_pl
    with flask_app.app_context():
        DailyReport.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="ppl-days")
        for d in (5, 6, 10):
            _add_daily_report(
                db.session, s.id, report_date=date(2026, 5, d),
            )
        _, totals = period_pl(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["days"] == 3


# ── store scoping ────────────────────────────────────────


def test_only_includes_stores_in_list():
    """Daily reports + transfers from a sibling store NOT in
    `store_ids` are excluded."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import period_pl
    with flask_app.app_context():
        Transfer.query.delete()
        DailyReport.query.delete()
        db.session.commit()
        s1 = _add_store(db.session, slug="ppl-scope-1")
        s2 = _add_store(db.session, slug="ppl-scope-2")
        _add_daily_report(
            db.session, s1.id, report_date=date(2026, 5, 5),
            taxable_sales=100.0,
        )
        _add_daily_report(
            db.session, s2.id, report_date=date(2026, 5, 5),
            taxable_sales=999.0,
        )
        _, totals = period_pl(
            db.session, [s1.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["income"] == 100.0


def test_only_includes_rows_in_window():
    """Rows outside [d_from, d_to] are excluded."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import period_pl
    with flask_app.app_context():
        Transfer.query.delete()
        DailyReport.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="ppl-window")
        _add_daily_report(
            db.session, s.id, report_date=date(2026, 4, 30),
            taxable_sales=999.0,  # before window
        )
        _add_daily_report(
            db.session, s.id, report_date=date(2026, 6, 1),
            taxable_sales=999.0,  # after window
        )
        _add_daily_report(
            db.session, s.id, report_date=date(2026, 5, 15),
            taxable_sales=100.0,
        )
        _, totals = period_pl(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["income"] == 100.0


# ── legacy wrapper ───────────────────────────────────────


