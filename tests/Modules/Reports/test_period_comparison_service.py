"""Unit tests for Reports.Services.period_comparison (PR 86)."""
from datetime import date, timedelta

from api.Modules.DailyBook.Models import DailyReport
from api.Modules.Tenancy.Models import Store
from api.Modules.Transfers.Models import Transfer


def _add_store(db, *, slug="pc-store"):
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


# ── auto-prior window ─────────────────────────────────────


def test_default_prior_is_immediately_preceding_window():
    """Without compare_from/to, the prior window is the same
    length immediately before d_from."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import period_comparison
    with flask_app.app_context():
        s = _add_store(db.session, slug="pc-default")
        # d_from..d_to is 7 days → prior should be 7 days
        # immediately before.
        rows, totals = period_comparison(
            db.session, [s.id],
            date(2026, 5, 8), date(2026, 5, 14),
        )
        assert "May 01" in totals["prior_label"]
        assert "May 07" in totals["prior_label"]
        assert "May 08" in totals["current_label"]


# ── custom comparison window ─────────────────────────────


def test_custom_compare_window_used_when_both_set():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import period_comparison
    with flask_app.app_context():
        s = _add_store(db.session, slug="pc-custom")
        rows, totals = period_comparison(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
            compare_from=date(2025, 5, 1),
            compare_to=date(2025, 5, 31),
        )
        # Label format: "May 01 – May 31, 2025" — year only on
        # the second date.
        assert "May 31, 2025" in totals["prior_label"]
        assert "May 01" in totals["prior_label"]


def test_custom_compare_normalises_backwards_dates():
    """If user picked compare_from > compare_to, swap them."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import period_comparison
    with flask_app.app_context():
        s = _add_store(db.session, slug="pc-backward")
        _, totals = period_comparison(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
            compare_from=date(2025, 5, 31),  # later date first
            compare_to=date(2025, 5, 1),
        )
        # Should still display May 01 → May 31.
        assert "May 01" in totals["prior_label"]
        assert "May 31, 2025" in totals["prior_label"]


def test_only_one_compare_arg_falls_back_to_auto_prior():
    """Both compare_from AND compare_to must be set — passing
    just one falls back to auto-prior."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import period_comparison
    with flask_app.app_context():
        s = _add_store(db.session, slug="pc-onearg")
        _, totals = period_comparison(
            db.session, [s.id],
            date(2026, 5, 8), date(2026, 5, 14),
            compare_from=date(2025, 1, 1),  # only one set
        )
        # Auto-prior used (May 1-7), not 2025.
        assert "May" in totals["prior_label"]
        assert "2025" not in totals["prior_label"]


# ── fixed metrics list ────────────────────────────────────


def test_returns_seven_metric_rows_in_fixed_order():
    """Always returns exactly 7 rows in this order — the template
    relies on it."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import period_comparison
    with flask_app.app_context():
        s = _add_store(db.session, slug="pc-7rows")
        rows, _ = period_comparison(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert len(rows) == 7
        labels = [r["label"] for r in rows]
        assert labels == [
            "Transfers", "Total Sent", "Fees Earned",
            "Federal Tax", "Total Income", "Total Expenses",
            "Net Income",
        ]


def test_money_flag_set_correctly_per_row():
    """`is_money` is True for currency metrics, False for
    transfer counts (so the template formats correctly)."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import period_comparison
    with flask_app.app_context():
        s = _add_store(db.session, slug="pc-money")
        rows, _ = period_comparison(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        by_label = {r["label"]: r for r in rows}
        assert by_label["Transfers"]["is_money"] is False
        assert by_label["Total Sent"]["is_money"] is True
        assert by_label["Net Income"]["is_money"] is True


# ── aggregation correctness ──────────────────────────────


def test_aggregates_transfer_metrics_in_window():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import period_comparison
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="pc-agg-tx")
        # Current period: 3 transfers totaling $300, $6 fee, $3 tax
        for _ in range(3):
            _add_transfer(
                db.session, s.id,
                send_date=date(2026, 5, 15),
                send_amount=100.0, fee=2.0, federal_tax=1.0,
            )
        rows, _ = period_comparison(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
            compare_from=date(2026, 4, 1),
            compare_to=date(2026, 4, 30),
        )
        by_label = {r["label"]: r for r in rows}
        assert by_label["Transfers"]["current"] == 3
        assert by_label["Total Sent"]["current"] == 300.0
        assert by_label["Fees Earned"]["current"] == 6.0
        assert by_label["Federal Tax"]["current"] == 3.0


def test_pct_change_computation():
    """delta = current - prior; pct = (delta / prior * 100) when
    prior != 0, else 100 if current else 0."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import period_comparison
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="pc-pct")
        # Current: 2 transfers; prior: 1 transfer → +100% delta.
        _add_transfer(
            db.session, s.id, send_date=date(2026, 5, 15),
            send_amount=100.0,
        )
        _add_transfer(
            db.session, s.id, send_date=date(2026, 5, 16),
            send_amount=100.0,
        )
        _add_transfer(
            db.session, s.id, send_date=date(2026, 4, 15),
            send_amount=100.0,
        )
        rows, _ = period_comparison(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
            compare_from=date(2026, 4, 1),
            compare_to=date(2026, 4, 30),
        )
        by_label = {r["label"]: r for r in rows}
        assert by_label["Transfers"]["current"] == 2
        assert by_label["Transfers"]["prior"] == 1
        assert by_label["Transfers"]["delta"] == 1
        assert by_label["Transfers"]["pct"] == 100.0


def test_pct_handles_zero_prior_with_current():
    """When prior=0 and current>0, pct should be 100 (not crash)."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import period_comparison
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="pc-zero-prior")
        _add_transfer(
            db.session, s.id, send_date=date(2026, 5, 15),
            send_amount=100.0,
        )
        rows, _ = period_comparison(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
            compare_from=date(2026, 4, 1),
            compare_to=date(2026, 4, 30),
        )
        by_label = {r["label"]: r for r in rows}
        # No transfers in April; one in May → +100%
        assert by_label["Transfers"]["prior"] == 0
        assert by_label["Transfers"]["pct"] == 100.0


def test_pct_zero_when_both_zero():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import period_comparison
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="pc-zero-both")
        rows, _ = period_comparison(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
            compare_from=date(2026, 4, 1),
            compare_to=date(2026, 4, 30),
        )
        by_label = {r["label"]: r for r in rows}
        assert by_label["Transfers"]["pct"] == 0.0


def test_includes_daily_report_pl_lines():
    """Income lines pull from DailyReport columns AND transfer
    fees. Expenses from DailyReport only."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import period_comparison
    with flask_app.app_context():
        Transfer.query.delete()
        DailyReport.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="pc-pl")
        _add_daily_report(
            db.session, s.id, report_date=date(2026, 5, 15),
            taxable_sales=200.0, cash_purchases=50.0,
        )
        _add_transfer(
            db.session, s.id, send_date=date(2026, 5, 15),
            fee=10.0,
        )
        rows, _ = period_comparison(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
            compare_from=date(2026, 4, 1),
            compare_to=date(2026, 4, 30),
        )
        by_label = {r["label"]: r for r in rows}
        # income = 200 (taxable_sales) + 10 (fee) = 210
        assert by_label["Total Income"]["current"] == 210.0
        # expenses = 50 (cash_purchases)
        assert by_label["Total Expenses"]["current"] == 50.0
        # net = 210 - 50 = 160
        assert by_label["Net Income"]["current"] == 160.0


# ── PL constants ─────────────────────────────────────────


def test_pl_income_lines_includes_core_columns():
    from api.Modules.Reports.Services import PL_INCOME_LINES
    fields = [f for _, f in PL_INCOME_LINES]
    expected = {
        "taxable_sales", "non_taxable", "bill_payment_charge",
        "phone_recargas", "boost_mobile",
        "check_cashing_fees", "return_check_hold_fees",
        "rebates_commissions",
    }
    assert expected.issubset(set(fields))


def test_pl_expense_lines_includes_core_columns():
    from api.Modules.Reports.Services import PL_EXPENSE_LINES
    fields = [f for _, f in PL_EXPENSE_LINES]
    expected = {
        "cash_purchases", "check_purchases",
        "cash_expense", "check_expense",
        "payroll_expense",
    }
    assert expected.issubset(set(fields))


# ── legacy Flask wrapper ─────────────────────────────────




def test_legacy_pl_constants_re_exported():
    from app import (
        _PL_EXPENSE_LINES as legacy_expense,
        _PL_INCOME_LINES as legacy_income,
    )
    from api.Modules.Reports.Services import (
        PL_EXPENSE_LINES, PL_INCOME_LINES,
    )
    assert legacy_income is PL_INCOME_LINES
    assert legacy_expense is PL_EXPENSE_LINES
