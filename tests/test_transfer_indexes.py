"""Verifies that PR 104 indexes are declared on the Transfer model
*and* land on the live database via the boot helper.

The two checks are intentionally separate:

  1. Model declaration — `Transfer.__table_args__` must list every
     index in `_ADDED_INDEXES`. This catches a regression where
     someone removes the declaration but leaves the boot helper
     entry — fresh installs would skip the index.

  2. DB-level presence — `_ensure_added_indexes()` ran on boot and
     `CREATE INDEX IF NOT EXISTS` actually landed. We query the
     dialect-specific catalog (sqlite_master on sqlite, pg_indexes
     on Postgres) so the test works in both environments.
"""
from sqlalchemy import inspect


# Single source of truth for what the test enforces. Keep this in
# sync with `_ADDED_INDEXES` in app.py.
EXPECTED_TRANSFER_INDEXES = {
    "ix_transfer_store_send_date":  ("store_id", "send_date"),
    "ix_transfer_customer_id":      ("customer_id",),
    "ix_transfer_created_by":       ("created_by",),
    "ix_transfer_status":           ("status",),
    "ix_transfer_confirm_number":   ("confirm_number",),
}


def test_transfer_indexes_declared_on_model(client):
    """The model's `__table_args__` must declare every index, so a
    fresh `db.create_all()` install picks them up without relying
    on the boot-time migration helper."""
    from api.Modules.Transfers.Models import Transfer
    declared = {
        ix.name: tuple(c.name for c in ix.columns)
        for ix in Transfer.__table__.indexes
    }
    for name, cols in EXPECTED_TRANSFER_INDEXES.items():
        assert name in declared, (
            f"Transfer is missing model-level Index({name!r}); "
            f"`db.create_all()` won't pick it up on a fresh DB."
        )
        assert declared[name] == cols, (
            f"{name} declared as {declared[name]!r} but expected "
            f"{cols!r} — column order matters for composite indexes."
        )


def test_transfer_indexes_present_in_db(client):
    """After boot, every expected index actually exists in the
    running database. Catches a bug where the model declares an
    index but `_ensure_added_indexes()` failed silently on prod."""
    from tests._app import db
    with client.application.app_context():
        insp = inspect(db.engine)
        present = {ix["name"] for ix in insp.get_indexes("transfer")}
    for name in EXPECTED_TRANSFER_INDEXES:
        assert name in present, (
            f"index {name!r} should exist on the transfer table; "
            f"got {present!r}"
        )


def test_added_indexes_registry_matches_model(client):
    """Cross-check: every entry in `_ADDED_INDEXES` for the
    transfer table must also be declared on the model. This catches
    drift where someone adds an entry to the registry but forgets
    the model decl (fresh installs would silently skip it)."""
    from api.Modules.Transfers.Models import Transfer
    from api.Core.Bootstrap import ADDED_INDEXES as _ADDED_INDEXES
    declared_names = {ix.name for ix in Transfer.__table__.indexes}
    for name, table, _cols in _ADDED_INDEXES:
        if table != "transfer":
            continue
        assert name in declared_names, (
            f"_ADDED_INDEXES has {name!r} for the transfer table, "
            f"but no matching db.Index() in the model. Fresh "
            f"installs (db.create_all on a clean DB) won't get it."
        )


def test_ensure_added_indexes_is_idempotent(client):
    """Calling the boot helper twice in a row should be a no-op the
    second time — `CREATE INDEX IF NOT EXISTS` is idempotent. This
    catches a regression where someone forgets the IF NOT EXISTS
    and prod boots start failing with `relation already exists`."""
    import logging
    from api.Core.Bootstrap import ensure_added_indexes
    from tests._app import db, app as flask_app
    log = logging.getLogger("dinerobook")
    with flask_app.app_context():
        ensure_added_indexes(db.engine, log)  # first call already happened on boot
        ensure_added_indexes(db.engine, log)  # second call must not raise


def test_period_filter_uses_index_on_postgres(client):
    """Sanity smoke for the hot path: the (store_id, send_date)
    composite is what the period filter needs. We can't run EXPLAIN
    inside the sqlite test fixture and reliably read a query plan,
    so we just assert the index exists with the right column order
    — that's the prerequisite. Real EXPLAIN diffing happens in the
    PR description before/after."""
    from tests._app import db
    with client.application.app_context():
        insp = inspect(db.engine)
        idxs = {ix["name"]: ix for ix in insp.get_indexes("transfer")}
    composite = idxs.get("ix_transfer_store_send_date")
    assert composite is not None
    assert composite["column_names"] == ["store_id", "send_date"]
