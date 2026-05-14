"""PR 108 — Missing FK indexes on `store_id` for cascade-delete
and JOIN performance.

Postgres does not auto-index FKs. The data-retention purge
(`purge_expired_stores`) issues `DELETE FROM <tbl> WHERE
store_id = ?` on every per-store table; without an index that
cascade is a full table scan per table per purged store.

Tables that get a `store_id` index here are exactly the ones
the audit found lacking a leading-store_id index — tables
where `store_id` was already first-position in a unique
constraint or composite index are skipped (transfer, customer,
etc.).
"""
from sqlalchemy import inspect
from tests._app import db_session


# (model attr, table_name, expected_index_name)
EXPECTED_FK_INDEXES = [
    ("StoreEmployee",     "store_employee",      "ix_store_employee_store_id"),
    ("OperatorAuditLog",  "operator_audit_log",  "ix_operator_audit_log_store_id"),
    ("TransferAudit",     "transfer_audit",      "ix_transfer_audit_store_id"),
    ("DailyDrop",         "daily_drop",          "ix_daily_drop_store_id"),
    ("CheckDeposit",      "check_deposit",       "ix_check_deposit_store_id"),
    ("ReturnCheck",       "return_check",        "ix_return_check_store_id"),
    ("DailyLineItem",     "daily_line_item",     "ix_daily_line_item_store_id"),
    ("StripeBankAccount", "stripe_bank_account", "ix_stripe_bank_account_store_id"),
    ("StoreOwnerLink",    "store_owner_link",    "ix_store_owner_link_store_id"),
]


def test_all_store_id_indexes_declared_on_models(client):
    """Every target model must have an index that leads with
    `store_id`. We don't pin the auto-generated name — just that
    *some* index covers the column with store_id first — because
    SQLAlchemy's auto-naming is what produces the registry name."""
    from tests import _app as appmod
    for model_attr, table_name, _expected in EXPECTED_FK_INDEXES:
        model = getattr(appmod, model_attr)
        leads = {
            tuple(c.name for c in ix.columns)[:1]
            for ix in model.__table__.indexes
        }
        assert ("store_id",) in leads, (
            f"{model_attr} (table {table_name}) needs an index "
            f"leading with store_id; have {leads!r}"
        )


def test_all_store_id_indexes_present_in_db(client):
    """End-to-end: every expected index actually exists in the
    live DB after `_ensure_added_indexes()` runs at boot."""
    from tests._app import db
    with db_session():
        insp = inspect(db.engine)
        for _model_attr, table_name, expected in EXPECTED_FK_INDEXES:
            present = {ix["name"] for ix in insp.get_indexes(table_name)}
            assert expected in present, (
                f"index {expected!r} missing from {table_name!r}; "
                f"present indexes: {present!r}"
            )


def test_added_indexes_registry_covers_all_targets(client):
    """`_ADDED_INDEXES` must list every (table, store_id) entry —
    otherwise existing prod databases will silently skip the
    index even though fresh installs get it."""
    from api.Core.Bootstrap import ADDED_INDEXES as _ADDED_INDEXES
    registry = {(name, table) for name, table, _ in _ADDED_INDEXES}
    for _model_attr, table_name, expected in EXPECTED_FK_INDEXES:
        assert (expected, table_name) in registry, (
            f"_ADDED_INDEXES is missing ({expected!r}, {table_name!r}); "
            f"existing prod DBs won't get the index on the next boot."
        )
