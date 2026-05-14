"""Unit tests for Superadmin.Services reports (PR 97).

Covers the first three platform-health aggregators:
  - active_stores_by_plan
  - signup_funnel
  - login_activity
"""
from datetime import date, datetime, timedelta

from api.Modules.Tenancy.Models import Store, User
from tests._app import db


_USER_COUNTER = 0


def _add_store(db, *, slug, plan="trial",
               created_at=None):
    s = Store(name=slug, slug=slug, plan=plan,
              email=f"{slug}@example.com",
              created_at=created_at or datetime.utcnow())
    db.add(s); db.flush()
    return s


def _add_user(db, store_id=None, *, role="admin",
              last_login_at=None, full_name="X"):
    global _USER_COUNTER
    _USER_COUNTER += 1
    u = User(
        store_id=store_id,
        username=f"sa-test-{_USER_COUNTER}",
        full_name=full_name,
        password_hash="hash",
        role=role,
        last_login_at=last_login_at,
    )
    db.add(u); db.flush()
    return u


# ── active_stores_by_plan ────────────────────────────────


def test_active_stores_by_plan_groups_by_plan():
    """Counts existing stores by current plan at end-of-period."""
    from tests._app import app as flask_app, db
    from api.Modules.Superadmin.Services import active_stores_by_plan
    with flask_app.app_context():
        db.session.query(Store).delete()
        db.session.commit()
        _add_store(db.session, slug="sa-pl-trial-1", plan="trial",
                   created_at=datetime(2026, 5, 1))
        _add_store(db.session, slug="sa-pl-trial-2", plan="trial",
                   created_at=datetime(2026, 5, 2))
        _add_store(db.session, slug="sa-pl-basic-1", plan="basic",
                   created_at=datetime(2026, 5, 3))
        rows, totals = active_stores_by_plan(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        by_plan = {r["plan"]: r for r in rows}
        assert by_plan["Trial"]["count"] == 2
        assert by_plan["Basic"]["count"] == 1
        assert totals["count"] == 3
        assert totals["plans"] == 2


def test_active_stores_by_plan_excludes_stores_created_after_d_to():
    """Stores created AFTER d_to don't count — point-in-time at
    end-of-period."""
    from tests._app import app as flask_app, db
    from api.Modules.Superadmin.Services import active_stores_by_plan
    with flask_app.app_context():
        db.session.query(Store).delete()
        db.session.commit()
        _add_store(db.session, slug="sa-pl-future", plan="trial",
                   created_at=datetime(2026, 7, 1))
        _add_store(db.session, slug="sa-pl-existing", plan="trial",
                   created_at=datetime(2026, 5, 5))
        _, totals = active_stores_by_plan(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["count"] == 1


def test_active_stores_by_plan_unknown_plan_label():
    """Stores with NULL plan render as '(unknown)'."""
    from tests._app import app as flask_app, db
    from api.Modules.Superadmin.Services import active_stores_by_plan
    with flask_app.app_context():
        db.session.query(Store).delete()
        db.session.commit()
        s = _add_store(db.session, slug="sa-pl-null", plan="trial",
                       created_at=datetime(2026, 5, 5))
        s.plan = ""  # blank → '(unknown)' display
        db.session.commit()
        rows, _ = active_stores_by_plan(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert rows[0]["plan"] == "(Unknown)"


# ── signup_funnel ────────────────────────────────────────


def test_signup_funnel_only_counts_stores_created_in_window():
    from tests._app import app as flask_app, db
    from api.Modules.Superadmin.Services import signup_funnel
    with flask_app.app_context():
        db.session.query(Store).delete()
        db.session.commit()
        # Outside window (before).
        _add_store(db.session, slug="sa-sf-old", plan="trial",
                   created_at=datetime(2026, 4, 30))
        # Inside.
        _add_store(db.session, slug="sa-sf-in-1", plan="trial",
                   created_at=datetime(2026, 5, 5))
        _add_store(db.session, slug="sa-sf-in-2", plan="basic",
                   created_at=datetime(2026, 5, 10))
        # Outside (after).
        _add_store(db.session, slug="sa-sf-future", plan="trial",
                   created_at=datetime(2026, 6, 1))
        _, totals = signup_funnel(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["count"] == 2


def test_signup_funnel_groups_by_plan():
    from tests._app import app as flask_app, db
    from api.Modules.Superadmin.Services import signup_funnel
    with flask_app.app_context():
        db.session.query(Store).delete()
        db.session.commit()
        _add_store(db.session, slug="sa-sf-trial-1", plan="trial",
                   created_at=datetime(2026, 5, 5))
        _add_store(db.session, slug="sa-sf-trial-2", plan="trial",
                   created_at=datetime(2026, 5, 10))
        _add_store(db.session, slug="sa-sf-pro", plan="pro",
                   created_at=datetime(2026, 5, 15))
        rows, _ = signup_funnel(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        by_plan = {r["plan"]: r for r in rows}
        assert by_plan["Trial"]["count"] == 2
        assert by_plan["Pro"]["count"] == 1


# ── login_activity ───────────────────────────────────────


def test_login_activity_groups_by_role():
    from tests._app import app as flask_app, db
    from api.Modules.Superadmin.Services import login_activity
    with flask_app.app_context():
        # Snapshot existing logins so seed users don't pollute.
        baseline_email = db.session.query(User).filter_by(role="superadmin").first()
        if baseline_email:
            baseline_email.last_login_at = None
        db.session.commit()
        s = _add_store(db.session, slug="sa-li-store", plan="basic",
                       created_at=datetime(2026, 4, 1))
        _add_user(db.session, s.id, role="admin",
                  last_login_at=datetime(2026, 5, 5))
        _add_user(db.session, s.id, role="admin",
                  last_login_at=datetime(2026, 5, 6))
        _add_user(db.session, s.id, role="employee",
                  last_login_at=datetime(2026, 5, 7))
        # Outside window — must not count.
        _add_user(db.session, s.id, role="employee",
                  last_login_at=datetime(2026, 4, 1))
        rows, totals = login_activity(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        by_role = {r["role"]: r["count"] for r in rows}
        assert by_role.get("Admin") == 2
        assert by_role.get("Employee") == 1
        assert totals["count"] == 3


def test_login_activity_filters_by_window():
    """Users whose `last_login_at` is outside [d_from, d_to] don't
    surface even if they have a recent login."""
    from tests._app import app as flask_app, db
    from api.Modules.Superadmin.Services import login_activity
    with flask_app.app_context():
        # Reset baseline.
        for u in db.session.query(User).all():
            u.last_login_at = None
        db.session.commit()
        s = _add_store(db.session, slug="sa-li-window",
                       plan="basic",
                       created_at=datetime(2026, 4, 1))
        _add_user(db.session, s.id, role="admin",
                  last_login_at=datetime(2026, 4, 30))
        _add_user(db.session, s.id, role="admin",
                  last_login_at=datetime(2026, 6, 1))
        _, totals = login_activity(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["count"] == 0


# ── legacy wrappers ──────────────────────────────────────






