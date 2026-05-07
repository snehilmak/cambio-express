"""Unit tests for SA MRR/ARR + churn-cohort services (PR 98)."""
from datetime import date, datetime

from app import Store


def _add_store(db, *, slug, plan="basic", billing_cycle="monthly",
               created_at=None, canceled_at=None):
    s = Store(name=slug, slug=slug, plan=plan,
              billing_cycle=billing_cycle,
              email=f"{slug}@example.com",
              created_at=created_at or datetime.utcnow(),
              canceled_at=canceled_at)
    db.add(s); db.flush()
    return s


# ── PLAN_MRR constant ────────────────────────────────────


def test_plan_mrr_table_has_expected_keys():
    """PLAN_MRR maps (plan, cycle) → monthly equivalent."""
    from api.Modules.Superadmin.Services import PLAN_MRR
    assert PLAN_MRR[("basic", "monthly")] == 49.0
    assert PLAN_MRR[("pro",   "monthly")] == 99.0
    # Yearly prices normalised to monthly.
    assert abs(PLAN_MRR[("basic", "yearly")] - 490.0 / 12.0) < 1e-9
    assert abs(PLAN_MRR[("pro",   "yearly")] - 990.0 / 12.0) < 1e-9


# ── mrr_arr ───────────────────────────────────────────────


def test_mrr_arr_groups_by_plan_and_cycle():
    from app import app as flask_app, db
    from api.Modules.Superadmin.Services import mrr_arr
    with flask_app.app_context():
        Store.query.delete()
        db.session.commit()
        _add_store(db.session, slug="ma-b1", plan="basic",
                   billing_cycle="monthly",
                   created_at=datetime(2026, 4, 1))
        _add_store(db.session, slug="ma-b2", plan="basic",
                   billing_cycle="monthly",
                   created_at=datetime(2026, 4, 1))
        _add_store(db.session, slug="ma-b3", plan="basic",
                   billing_cycle="yearly",
                   created_at=datetime(2026, 4, 1))
        _add_store(db.session, slug="ma-p1", plan="pro",
                   billing_cycle="monthly",
                   created_at=datetime(2026, 4, 1))
        rows, totals = mrr_arr(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        # 2 basic monthly + 1 basic yearly + 1 pro monthly = 4 stores
        # MRR = 2*49 + 1*(490/12) + 1*99 = 98 + 40.833 + 99 = 237.833
        assert totals["stores"] == 4
        assert abs(totals["mrr"] - (2*49.0 + 490.0/12 + 99.0)) < 0.01
        # ARR = 12 * MRR
        assert abs(totals["arr"] - totals["mrr"] * 12.0) < 0.01


def test_mrr_arr_excludes_trial_and_inactive():
    """Only basic/pro stores count — trial and inactive are ignored."""
    from app import app as flask_app, db
    from api.Modules.Superadmin.Services import mrr_arr
    with flask_app.app_context():
        Store.query.delete()
        db.session.commit()
        _add_store(db.session, slug="ma-trial", plan="trial",
                   created_at=datetime(2026, 4, 1))
        _add_store(db.session, slug="ma-inactive", plan="inactive",
                   created_at=datetime(2026, 4, 1))
        _add_store(db.session, slug="ma-paid", plan="basic",
                   billing_cycle="monthly",
                   created_at=datetime(2026, 4, 1))
        _, totals = mrr_arr(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["stores"] == 1
        assert totals["mrr"] == 49.0


def test_mrr_arr_excludes_stores_created_after_d_to():
    from app import app as flask_app, db
    from api.Modules.Superadmin.Services import mrr_arr
    with flask_app.app_context():
        Store.query.delete()
        db.session.commit()
        _add_store(db.session, slug="ma-future", plan="basic",
                   billing_cycle="monthly",
                   created_at=datetime(2026, 7, 1))
        _add_store(db.session, slug="ma-past", plan="basic",
                   billing_cycle="monthly",
                   created_at=datetime(2026, 4, 1))
        _, totals = mrr_arr(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["stores"] == 1


# ── churn_cohort ─────────────────────────────────────────


def test_churn_cohort_buckets_by_signup_month():
    """Cancelled stores group by their `created_at` YYYY-MM."""
    from app import app as flask_app, db
    from api.Modules.Superadmin.Services import churn_cohort
    with flask_app.app_context():
        Store.query.delete()
        db.session.commit()
        _add_store(db.session, slug="cc-a-1", plan="inactive",
                   created_at=datetime(2026, 1, 5),
                   canceled_at=datetime(2026, 5, 10))
        _add_store(db.session, slug="cc-a-2", plan="inactive",
                   created_at=datetime(2026, 1, 20),
                   canceled_at=datetime(2026, 5, 12))
        _add_store(db.session, slug="cc-b", plan="inactive",
                   created_at=datetime(2026, 2, 5),
                   canceled_at=datetime(2026, 5, 15))
        rows, totals = churn_cohort(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        by_cohort = {r["cohort"]: r for r in rows}
        assert by_cohort["2026-01"]["cancelled"] == 2
        assert by_cohort["2026-02"]["cancelled"] == 1
        assert totals["cancelled"] == 3


def test_churn_cohort_includes_active_survivors():
    """Stores from the same signup month that are STILL active
    (basic/pro, no canceled_at) feed the `active` count."""
    from app import app as flask_app, db
    from api.Modules.Superadmin.Services import churn_cohort
    with flask_app.app_context():
        Store.query.delete()
        db.session.commit()
        # Cancelled in May, signed up in Jan.
        _add_store(db.session, slug="cc-cancelled", plan="inactive",
                   created_at=datetime(2026, 1, 5),
                   canceled_at=datetime(2026, 5, 10))
        # Survivor: same Jan cohort, still active basic.
        _add_store(db.session, slug="cc-active", plan="basic",
                   created_at=datetime(2026, 1, 8),
                   canceled_at=None)
        rows, _ = churn_cohort(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        by_cohort = {r["cohort"]: r for r in rows}
        assert by_cohort["2026-01"]["cancelled"] == 1
        assert by_cohort["2026-01"]["active"]    == 1


def test_churn_cohort_pct_calculation():
    """churn_pct = cancelled / (cancelled + active) * 100."""
    from app import app as flask_app, db
    from api.Modules.Superadmin.Services import churn_cohort
    with flask_app.app_context():
        Store.query.delete()
        db.session.commit()
        # 1 cancelled + 3 active in same Jan cohort → 25% churn.
        _add_store(db.session, slug="cc-pct-cancel", plan="inactive",
                   created_at=datetime(2026, 1, 5),
                   canceled_at=datetime(2026, 5, 10))
        for i in range(3):
            _add_store(db.session, slug=f"cc-pct-active-{i}",
                       plan="basic",
                       created_at=datetime(2026, 1, 6 + i))
        rows, _ = churn_cohort(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert rows[0]["churn_pct"] == 25.0


def test_churn_cohort_empty_when_no_cancellations():
    from app import app as flask_app, db
    from api.Modules.Superadmin.Services import churn_cohort
    with flask_app.app_context():
        Store.query.delete()
        db.session.commit()
        _add_store(db.session, slug="cc-active-only", plan="basic",
                   created_at=datetime(2026, 1, 5))
        rows, totals = churn_cohort(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert rows == []
        assert totals["cancelled"] == 0
        assert totals["active"] == 0


# ── legacy wrappers ──────────────────────────────────────


def test_legacy_mrr_arr_wrapper_delegates():
    from app import app as flask_app, db
    from app import _sa_mrr_arr_data
    from api.Modules.Superadmin.Services import mrr_arr
    with flask_app.app_context():
        Store.query.delete()
        db.session.commit()
        _add_store(db.session, slug="ma-legacy", plan="basic",
                   billing_cycle="monthly",
                   created_at=datetime(2026, 4, 1))
        legacy_rows, legacy_totals = _sa_mrr_arr_data(
            date(2026, 5, 1), date(2026, 5, 31),
        )
        svc_rows, svc_totals = mrr_arr(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert legacy_rows == svc_rows
        assert legacy_totals == svc_totals


def test_legacy_churn_cohort_wrapper_delegates():
    from app import app as flask_app, db
    from app import _sa_churn_cohort_data
    from api.Modules.Superadmin.Services import churn_cohort
    with flask_app.app_context():
        Store.query.delete()
        db.session.commit()
        _add_store(db.session, slug="cc-legacy",
                   plan="inactive",
                   created_at=datetime(2026, 1, 5),
                   canceled_at=datetime(2026, 5, 10))
        legacy_rows, legacy_totals = _sa_churn_cohort_data(
            date(2026, 5, 1), date(2026, 5, 31),
        )
        svc_rows, svc_totals = churn_cohort(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert legacy_rows == svc_rows
        assert legacy_totals == svc_totals
