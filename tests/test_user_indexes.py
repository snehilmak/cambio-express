"""PR 106 — User cross-store username index.

The generic `/login` POST and `find_user_by_username` (CLI
password-reset / superadmin recovery) filter on `User.username`
alone — without `store_id`. The existing unique constraint on
`(store_id, username)` leads with `store_id`, so those queries
fall back to a full table scan. `ix_user_username` covers them.

`user` is a Postgres reserved word; `_ensure_added_indexes()`
already double-quotes the table name in the DDL, so the registry
entry uses the plain `"user"` string. This test pins that the
boot helper actually creates the index on the live DB so we
catch any regression in the quoting path.
"""
from sqlalchemy import inspect
from tests._app import db_session


def test_user_username_index_declared(client):
    from api.Modules.Tenancy.Models import User
    declared = {
        ix.name: tuple(c.name for c in ix.columns)
        for ix in User.__table__.indexes
    }
    assert "ix_user_username" in declared, (
        "User.__table_args__ must declare an Index() on `username` "
        "so fresh installs pick it up via db.create_all()."
    )
    assert declared["ix_user_username"] == ("username",)


def test_user_username_index_present_in_db(client):
    """End-to-end check that the boot helper's quoting handles the
    `user` reserved word correctly. If the DDL emitted `""user""`
    or `user` (unquoted), this would fail on Postgres at boot —
    on sqlite it would silently work, masking the bug. We assert
    inspector visibility either way."""
    from tests._app import db
    with db_session():
        insp = inspect(db.engine)
        present = {ix["name"] for ix in insp.get_indexes("user")}
    assert "ix_user_username" in present, (
        f"ix_user_username should exist on the user table after "
        f"_ensure_added_indexes(); got {present!r}"
    )


def test_user_unique_constraint_still_present(client):
    """Sanity: the (store_id, username) unique constraint that
    prevents per-store username collisions must survive."""
    from tests._app import db
    with db_session():
        insp = inspect(db.engine)
        uniques = insp.get_unique_constraints("user")
    cols = [tuple(u["column_names"]) for u in uniques]
    assert ("store_id", "username") in cols, (
        f"unique constraint (store_id, username) must survive; "
        f"got {cols!r}"
    )


def test_added_indexes_registry_lists_user(client):
    from api.Modules.Tenancy.Models import User
    from api.Core.Bootstrap import ADDED_INDEXES as _ADDED_INDEXES
    declared = {ix.name for ix in User.__table__.indexes}
    user_entries = [
        name for name, table, _ in _ADDED_INDEXES if table == "user"
    ]
    for name in user_entries:
        assert name in declared, (
            f"_ADDED_INDEXES has {name!r} for the user table, but "
            f"no matching db.Index() in the model. Fresh installs "
            f"won't get it."
        )
