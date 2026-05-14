"""Unit tests for Reports.Services.employee_activity (PR 94)."""
from datetime import date

from api.Modules.Tenancy.Models import Store, User
from api.Modules.Transfers.Models import Transfer
from tests._app import db, db_session


_USER_COUNTER = 0


def _add_store(db, *, slug="ea-store"):
    s = Store(name=slug, slug=slug, plan="basic",
              email=f"{slug}@example.com")
    db.add(s); db.flush()
    return s


def _add_user(db, store_id, *, full_name="Cashier",
              username=None):
    global _USER_COUNTER
    _USER_COUNTER += 1
    u = User(
        store_id=store_id,
        username=username or f"u-{_USER_COUNTER}",
        full_name=full_name,
        password_hash="hash",
        role="employee",
    )
    db.add(u); db.flush()
    return u


def _add_transfer(db, store_id, *, send_date, send_amount=100.0,
                  fee=2.0, federal_tax=1.0, status="Sent",
                  created_by=None):
    t = Transfer(
        store_id=store_id,
        created_by=created_by,
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


# ── shape ────────────────────────────────────────────────


def test_returns_rows_and_totals_tuple():
    from tests._app import db
    from api.Modules.Reports.Services import employee_activity
    with db_session():
        db.session.query(Transfer).delete()
        db.session.commit()
        s = _add_store(db.session, slug="ea-shape")
        rows, totals = employee_activity(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert isinstance(rows, list)
        assert set(totals) == {"count", "sent", "cancels"}


def test_row_shape():
    from tests._app import db
    from api.Modules.Reports.Services import employee_activity
    with db_session():
        db.session.query(Transfer).delete()
        db.session.commit()
        s = _add_store(db.session, slug="ea-row")
        u = _add_user(db.session, s.id)
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 5),
                      created_by=u.id)
        rows, _ = employee_activity(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert len(rows) == 1
        assert set(rows[0]) == {
            "employee", "username", "count", "sent",
            "cancels", "last_activity",
        }


# ── attribution ─────────────────────────────────────────


def test_unattributed_transfers_bucket_to_unattributed_label():
    from tests._app import db
    from api.Modules.Reports.Services import employee_activity
    with db_session():
        db.session.query(Transfer).delete()
        db.session.commit()
        s = _add_store(db.session, slug="ea-unattr")
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 5),
                      created_by=None)
        rows, _ = employee_activity(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert len(rows) == 1
        assert rows[0]["employee"] == "(unattributed)"
        assert rows[0]["username"] == ""


def test_employee_label_prefers_full_name_over_username():
    from tests._app import db
    from api.Modules.Reports.Services import employee_activity
    with db_session():
        db.session.query(Transfer).delete()
        db.session.commit()
        s = _add_store(db.session, slug="ea-label")
        u = _add_user(db.session, s.id,
                      full_name="Alice Smith",
                      username="alice")
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 5),
                      created_by=u.id)
        rows, _ = employee_activity(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert rows[0]["employee"] == "Alice Smith"
        assert rows[0]["username"] == "alice"


def test_employee_label_falls_back_to_username_when_no_full_name():
    from tests._app import db
    from api.Modules.Reports.Services import employee_activity
    with db_session():
        db.session.query(Transfer).delete()
        db.session.commit()
        s = _add_store(db.session, slug="ea-uname")
        u = _add_user(db.session, s.id,
                      full_name="",
                      username="bob")
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 5),
                      created_by=u.id)
        rows, _ = employee_activity(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert rows[0]["employee"] == "bob"


# ── activity vs cancels ─────────────────────────────────


def test_active_count_excludes_canceled_status():
    """Active count + sent only counts non-excluded statuses."""
    from tests._app import db
    from api.Modules.Reports.Services import employee_activity
    with db_session():
        db.session.query(Transfer).delete()
        db.session.commit()
        s = _add_store(db.session, slug="ea-active")
        u = _add_user(db.session, s.id)
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 5),
                      send_amount=100.0,
                      created_by=u.id, status="Sent")
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 6),
                      send_amount=999.0,
                      created_by=u.id, status="Canceled")
        rows, _ = employee_activity(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert len(rows) == 1
        r = rows[0]
        assert r["count"] == 1
        assert r["sent"] == 100.0
        assert r["cancels"] == 1


def test_cancel_only_employees_appear_with_zero_active():
    """An employee who ONLY had cancelled transfers still surfaces
    as a row (cancels > 0, count = 0, last_activity = None)."""
    from tests._app import db
    from api.Modules.Reports.Services import employee_activity
    with db_session():
        db.session.query(Transfer).delete()
        db.session.commit()
        s = _add_store(db.session, slug="ea-cancel-only")
        u = _add_user(db.session, s.id, full_name="C-Only",
                      username="conly")
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 5),
                      created_by=u.id, status="Canceled")
        rows, _ = employee_activity(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        r = rows[0]
        assert r["employee"] == "C-Only"
        assert r["count"] == 0
        assert r["sent"] == 0.0
        assert r["cancels"] == 1
        assert r["last_activity"] is None


# ── ordering ─────────────────────────────────────────────


def test_rows_sorted_by_total_activity_descending():
    """Rows sort by (count + cancels) desc — busiest employees
    surface first, regardless of revenue."""
    from tests._app import db
    from api.Modules.Reports.Services import employee_activity
    with db_session():
        db.session.query(Transfer).delete()
        db.session.commit()
        s = _add_store(db.session, slug="ea-sort")
        u_busy   = _add_user(db.session, s.id,
                             full_name="Busy", username="busy")
        u_quiet  = _add_user(db.session, s.id,
                             full_name="Quiet", username="quiet")
        for _ in range(5):
            _add_transfer(db.session, s.id,
                          send_date=date(2026, 5, 5),
                          created_by=u_busy.id)
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 5),
                      created_by=u_quiet.id)
        rows, _ = employee_activity(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        labels = [r["employee"] for r in rows]
        assert labels == ["Busy", "Quiet"]


# ── totals ─────────────────────────────────────────────


def test_totals_sum_count_sent_cancels():
    from tests._app import db
    from api.Modules.Reports.Services import employee_activity
    with db_session():
        db.session.query(Transfer).delete()
        db.session.commit()
        s = _add_store(db.session, slug="ea-totals")
        u1 = _add_user(db.session, s.id)
        u2 = _add_user(db.session, s.id)
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 5),
                      send_amount=100.0,
                      created_by=u1.id, status="Sent")
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 5),
                      send_amount=200.0,
                      created_by=u2.id, status="Sent")
        _add_transfer(db.session, s.id,
                      send_date=date(2026, 5, 6),
                      created_by=u1.id, status="Canceled")
        _, totals = employee_activity(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["count"]   == 2
        assert totals["sent"]    == 300.0
        assert totals["cancels"] == 1


# ── legacy wrapper ───────────────────────────────────────


