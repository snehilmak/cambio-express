"""The Store Daily Book migration spells its columns out literally
rather than importing them from the model.

That is deliberate — a migration must be immutable, so renaming a
model field later must not change what a historical revision
creates. The cost of that choice is two lists that could drift, so
this test is the thing that stops them.
"""
import importlib.util
from pathlib import Path

from api.Modules.StoreBook.Models import COUNT_FIELDS, MONEY_FIELDS

_MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "alembic" / "versions" / "f2b8d4e6a1c7_add_store_daily_entry.py"
)


def _load():
    spec = importlib.util.spec_from_file_location(
        "sde_migration", _MIGRATION,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_creates_exactly_the_model_money_columns():
    assert tuple(_load()._MONEY_FIELDS) == tuple(MONEY_FIELDS)


def test_migration_creates_exactly_the_model_count_columns():
    assert tuple(_load()._COUNT_FIELDS) == tuple(COUNT_FIELDS)


def test_migration_does_not_import_application_code():
    """Alembic loads every version file to build the revision graph,
    and init_db() runs that during app boot — a top-level app import
    here drags the model layer into the boot path from inside the
    migration loader."""
    source = _MIGRATION.read_text()
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")):
            assert not stripped.startswith(
                ("import api", "from api"),
            ), f"migration imports application code: {stripped}"
