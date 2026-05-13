"""PR 105 — Customer umbrella-upsert index.

The umbrella-customer lookup (`find_by_phone_in_stores`) filters
`store_id IN (...) AND phone_country = ? AND phone_number = ?`.
The existing unique constraint indexes `(store_id, phone_country,
phone_number)` — leading with `store_id` forces N seeks for an
N-store umbrella. This test pins the secondary
`(phone_country, phone_number)` index so the planner can do a
single seek and filter on store_id.

Mirrors `tests/test_transfer_indexes.py`: model declaration,
DB-level presence, registry parity.
"""
from sqlalchemy import inspect


def test_customer_phone_index_declared(client):
    from api.Modules.Customers.Models import Customer
    declared = {
        ix.name: tuple(c.name for c in ix.columns)
        for ix in Customer.__table__.indexes
    }
    assert "ix_customer_phone" in declared, (
        "Customer.__table_args__ must declare an Index() on "
        "(phone_country, phone_number) so fresh installs pick it "
        "up via db.create_all()."
    )
    assert declared["ix_customer_phone"] == ("phone_country", "phone_number"), (
        f"column order matters — got {declared['ix_customer_phone']!r}"
    )


def test_customer_phone_index_present_in_db(client):
    from app import db
    with client.application.app_context():
        insp = inspect(db.engine)
        present = {ix["name"] for ix in insp.get_indexes("customer")}
    assert "ix_customer_phone" in present, (
        f"ix_customer_phone should exist on the customer table after "
        f"_ensure_added_indexes(); got {present!r}"
    )


def test_unique_constraint_still_present(client):
    """Sanity check: adding the secondary index didn't drop the
    unique constraint that prevents duplicate (store_id, phone) rows."""
    from app import db
    with client.application.app_context():
        insp = inspect(db.engine)
        uniques = insp.get_unique_constraints("customer")
    names = {u["name"] for u in uniques}
    assert "uq_customer_store_phone" in names, (
        f"unique constraint must survive the new index; got {names!r}"
    )


def test_added_indexes_registry_lists_customer_phone(client):
    """Cross-check: registry entry must match a model-level Index()."""
    from api.Modules.Customers.Models import Customer
    from app import _ADDED_INDEXES
    declared = {ix.name for ix in Customer.__table__.indexes}
    customer_entries = [
        name for name, table, _ in _ADDED_INDEXES if table == "customer"
    ]
    for name in customer_entries:
        assert name in declared, (
            f"_ADDED_INDEXES has {name!r} for customer but no matching "
            f"db.Index() on the model"
        )
