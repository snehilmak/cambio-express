"""PR 107 — LoginEvent (at, user_id) covering composite for DAU/MAU.

The DAU/MAU aggregator (`api/Modules/Superadmin/Services/reports.py`)
runs three flavors of the same shape:

  SELECT date(at), count(distinct user_id)
    FROM login_event
   WHERE at BETWEEN ? AND ?
   GROUP BY date(at)

  SELECT count(distinct user_id) FROM login_event
   WHERE at BETWEEN ? AND ?

  SELECT count(distinct user_id) FROM login_event
   WHERE at >= today_start

With the standalone `at` index alone, the planner does a range
scan and then a heap fetch for `user_id` on every matched row.
A `(at, user_id)` composite covers the lookup — no heap fetch.

This test pins the composite without removing the standalone
`at` / `user_id` indexes that already exist on the model.
"""
from sqlalchemy import inspect


def test_login_event_composite_declared(client):
    from api.Modules.Auth.Models import LoginEvent
    declared = {
        ix.name: tuple(c.name for c in ix.columns)
        for ix in LoginEvent.__table__.indexes
    }
    assert "ix_login_event_at_user" in declared, (
        "LoginEvent.__table_args__ must declare the (at, user_id) "
        "composite — fresh installs need it via db.create_all()."
    )
    assert declared["ix_login_event_at_user"] == ("at", "user_id"), (
        f"column order matters — got "
        f"{declared['ix_login_event_at_user']!r}"
    )


def test_login_event_composite_present_in_db(client):
    from tests._app import db
    with client.application.app_context():
        insp = inspect(db.engine)
        present = {ix["name"] for ix in insp.get_indexes("login_event")}
    assert "ix_login_event_at_user" in present, (
        f"ix_login_event_at_user should exist after boot; got "
        f"{present!r}"
    )


def test_existing_single_column_indexes_survive(client):
    """The standalone `at` and `user_id` indexes (from
    `index=True` on the columns) cover other paths — FK joins on
    user_id, "logins for user X" lookups, simple range scans on
    `at`. Don't drop them."""
    from tests._app import db
    with client.application.app_context():
        insp = inspect(db.engine)
        idxs = insp.get_indexes("login_event")
    by_cols = {tuple(ix["column_names"]) for ix in idxs}
    assert ("at",)      in by_cols, f"standalone `at` index missing; have {by_cols!r}"
    assert ("user_id",) in by_cols, f"standalone `user_id` index missing; have {by_cols!r}"


def test_added_indexes_registry_lists_login_event(client):
    from api.Modules.Auth.Models import LoginEvent
    from api.Core.Bootstrap import ADDED_INDEXES as _ADDED_INDEXES
    declared = {ix.name for ix in LoginEvent.__table__.indexes}
    entries = [
        name for name, table, _ in _ADDED_INDEXES if table == "login_event"
    ]
    for name in entries:
        assert name in declared, (
            f"_ADDED_INDEXES has {name!r} for login_event but no "
            f"matching db.Index() on the model"
        )
