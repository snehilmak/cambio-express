"""Unit tests for Superadmin.Services.dashboard (PR 75)."""
from datetime import datetime, timedelta

from api.Modules.Billing.Models import ReferralCode
from api.Modules.Tenancy.Models import Store
from api.Modules.Transfers.Models import Transfer
from tests._app import db, db_session


# ── compute_mrr ───────────────────────────────────────────


def test_compute_mrr_pure_math():
    """No DB, no side-effects — just price math."""
    from api.Modules.Superadmin.Services import compute_mrr
    bm, by_, pm, py_, total = compute_mrr(2, 1, 3, 1)
    # Basic monthly: 2 * $35 = $70
    assert bm == 70
    # Basic yearly: 1 * $350 / 12 ≈ $29
    assert by_ == round(350 / 12)
    # Pro monthly: 3 * $45 = $135
    assert pm == 135
    # Pro yearly: 1 * $450 / 12 ≈ $38. This was priced at $420 while
    # the pricing page sold Pro-yearly at $450, under-reporting MRR.
    assert py_ == round(450 / 12)
    assert total == bm + by_ + pm + py_


def test_compute_mrr_zero_subscribers_returns_zero():
    from api.Modules.Superadmin.Services import compute_mrr
    bm, by_, pm, py_, total = compute_mrr(0, 0, 0, 0)
    assert (bm, by_, pm, py_, total) == (0, 0, 0, 0, 0)


# ── superadmin_dashboard_context ──────────────────────────


def test_dashboard_context_returns_required_keys():
    """The template expects a known set of keys; missing one
    breaks the dashboard. Snapshot the public contract."""
    from tests._app import db
    from api.Modules.Superadmin.Services import (
        superadmin_dashboard_context,
    )
    with db_session():
        ctx = superadmin_dashboard_context(db.session)
        required = {
            "total_stores", "active_count", "trial_count",
            "paid_count", "estimated_mrr", "inactive_count",
            "new_stores_30d", "new_stores_delta",
            "churn_30d", "churn_delta",
            "basic_monthly", "basic_yearly",
            "pro_monthly", "pro_yearly",
            "basic_monthly_mrr", "basic_yearly_mrr",
            "pro_monthly_mrr", "pro_yearly_mrr",
            "basic_count", "pro_count",
            "signup_labels", "signup_direct", "signup_referral",
            "plan_dist", "volume_by_company",
            "total_volume_30d", "total_transfers_30d",
            "top_referrers", "direct_signups", "referral_signups",
            "activity", "stores",
        }
        assert required.issubset(set(ctx.keys()))


def test_dashboard_context_signup_series_always_90_entries():
    from tests._app import db
    from api.Modules.Superadmin.Services import (
        superadmin_dashboard_context,
    )
    with db_session():
        ctx = superadmin_dashboard_context(db.session)
        assert len(ctx["signup_labels"]) == 90
        assert len(ctx["signup_direct"]) == 90
        assert len(ctx["signup_referral"]) == 90


def test_dashboard_context_plan_distribution_has_four_buckets():
    """Trial / Basic / Pro / Inactive — fixed shape."""
    from tests._app import db
    from api.Modules.Superadmin.Services import (
        superadmin_dashboard_context,
    )
    with db_session():
        ctx = superadmin_dashboard_context(db.session)
        labels = [bucket["label"] for bucket in ctx["plan_dist"]]
        assert labels == ["Trial", "Basic", "Pro", "Inactive"]


def test_dashboard_context_counts_paid_correctly():
    """paid_count = basic_count + pro_count."""
    from tests._app import db
    from api.Modules.Superadmin.Services import (
        superadmin_dashboard_context,
    )
    with db_session():
        db.session.query(Store).delete()
        db.session.commit()
        # 2 basic, 1 pro, 1 trial.
        for slug, plan, cycle in [
            ("dash-basic-1", "basic", "monthly"),
            ("dash-basic-2", "basic", "monthly"),
            ("dash-pro-1",   "pro",   "monthly"),
            ("dash-trial-1", "trial", ""),
        ]:
            db.session.add(Store(
                name=slug, slug=slug, plan=plan,
                billing_cycle=cycle,
                email=f"{slug}@test.com",
            ))
        db.session.commit()
        ctx = superadmin_dashboard_context(db.session)
        assert ctx["basic_count"] == 2
        assert ctx["pro_count"] == 1
        assert ctx["paid_count"] == 3
        assert ctx["trial_count"] == 1


def test_dashboard_context_excludes_canceled_transfers_from_volume():
    from tests._app import db
    from api.Modules.Superadmin.Services import (
        superadmin_dashboard_context,
    )
    with db_session():
        db.session.query(Transfer).delete()
        db.session.query(Store).delete()
        db.session.commit()
        s = Store(name="dash-vol", slug="dash-vol", plan="basic",
                  email="dash-vol@test.com")
        db.session.add(s); db.session.flush()
        recent = datetime.utcnow() - timedelta(days=5)
        # Sent → counts; Canceled / Rejected → excluded.
        for amt, status in [(100.0, "Sent"),
                            (200.0, "Canceled"),
                            (300.0, "Rejected")]:
            t = Transfer(
                store_id=s.id,
                send_date=recent.date(),
                company="Intermex",
                sender_name="x",
                send_amount=amt,
                fee=0.0,
                federal_tax=0.0,
                status=status,
            )
            t.created_at = recent
            db.session.add(t)
        db.session.commit()
        ctx = superadmin_dashboard_context(db.session)
        # Only the $100 Sent counted.
        assert ctx["total_volume_30d"] == 100.0
        assert ctx["total_transfers_30d"] == 1


def test_dashboard_context_top_referrers_only_includes_redeemed():
    """Referral codes with redeemed_count=0 are excluded."""
    from tests._app import db
    from api.Modules.Superadmin.Services import (
        superadmin_dashboard_context,
    )
    with db_session():
        db.session.query(ReferralCode).delete()
        db.session.query(Store).delete()
        db.session.commit()
        s_redeemed = Store(name="redeemed", slug="redeemed",
                            plan="basic",
                            email="redeemed@test.com")
        s_unused = Store(name="unused", slug="unused",
                          plan="basic",
                          email="unused@test.com")
        db.session.add_all([s_redeemed, s_unused])
        db.session.flush()
        db.session.add(ReferralCode(
            code="REDEEM01",
            owner_store_id=s_redeemed.id,
            redeemed_count=3,
            reward_self_cents=10000,
            reward_referee_cents=5000,
        ))
        db.session.add(ReferralCode(
            code="UNUSED01",
            owner_store_id=s_unused.id,
            redeemed_count=0,
            reward_self_cents=10000,
            reward_referee_cents=5000,
        ))
        db.session.commit()
        ctx = superadmin_dashboard_context(db.session)
        codes = [r["code"] for r in ctx["top_referrers"]]
        assert "REDEEM01" in codes
        assert "UNUSED01" not in codes


def test_dashboard_context_activity_capped_at_12():
    from tests._app import db
    from api.Modules.Superadmin.Services import (
        superadmin_dashboard_context,
    )
    with db_session():
        db.session.query(Store).delete()
        db.session.commit()
        # 15 stores, all recent → activity feed should still cap.
        for i in range(15):
            db.session.add(Store(
                name=f"dash-act-{i}", slug=f"dash-act-{i}",
                plan="basic",
                email=f"dash-act-{i}@test.com",
            ))
        db.session.commit()
        ctx = superadmin_dashboard_context(db.session)
        assert len(ctx["activity"]) <= 12


# ── legacy Flask wrappers ─────────────────────────────────




