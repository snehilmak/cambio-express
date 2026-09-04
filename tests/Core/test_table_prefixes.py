"""The table-naming convention (S-1), enforced.

Every application table is ``<area>_<thing>`` so a developer can
read which part of the product owns it. This file is what keeps that
true after the rename PR: a new model with the wrong prefix, a new
module missing from the map, a stale schema doc, or a migration that
disagrees with the models all fail here.
"""
import importlib.util
import re
from pathlib import Path

import pytest
from sqlalchemy import inspect

from api.Core.Database.session import Base
from api.Core.Schema import (
    AREAS, LIBRARY_TABLES, MODULE_PREFIX, load_all_models, module_of,
    render_schema_doc, table_inventory,
)
from tests._app import db

_REPO = Path(__file__).resolve().parents[2]
_MIGRATION = (
    _REPO / "alembic" / "versions" / "c4a9e7d21f08_area_prefix_every_table.py"
)


def _mapped_tables() -> dict[str, type]:
    # Some modules register their models lazily; without this the
    # inventory is whatever happened to be imported so far.
    load_all_models()
    return {
        str(m.local_table.name): m.class_
        for m in Base.registry.mappers
        if m.local_table is not None
    }


# ── Models follow the map ───────────────────────────────────


def test_every_prefix_is_a_known_area():
    for module, prefix in MODULE_PREFIX.items():
        assert prefix in AREAS, f"{module} maps to undeclared area {prefix!r}"


def test_every_model_module_is_in_the_map():
    missing = sorted({
        module_of(cls) for cls in _mapped_tables().values()
        if module_of(cls) not in MODULE_PREFIX
    })
    assert not missing, (
        f"modules with models but no prefix in api/Core/Schema.py: {missing}"
    )


def test_every_table_starts_with_its_module_prefix():
    wrong = []
    for table, cls in _mapped_tables().items():
        prefix = MODULE_PREFIX[module_of(cls)]
        if not table.startswith(prefix):
            wrong.append(f"{table} ({module_of(cls)} → {prefix})")
    assert not wrong, "tables not carrying their area prefix:\n  " + "\n  ".join(sorted(wrong))


def test_no_table_uses_a_prefix_from_another_area():
    """``retail_`` on a model that lives in DailyBook would pass the
    startswith check for its own module only if DailyBook mapped to
    retail_ — so this is the cross-check: the prefix a table wears
    must be the one its module owns, not merely some valid prefix."""
    for table, cls in _mapped_tables().items():
        worn = next((p for p in AREAS if table.startswith(p)), None)
        assert worn == MODULE_PREFIX[module_of(cls)], (
            f"{table} wears {worn!r} but {module_of(cls)} owns "
            f"{MODULE_PREFIX[module_of(cls)]!r}"
        )


# ── The migration and the models agree ──────────────────────


def _load_migration():
    spec = importlib.util.spec_from_file_location("c4a9e7d21f08", _MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_imports_no_application_code():
    source = _MIGRATION.read_text()
    assert not re.search(r"^\s*(from|import)\s+api\b", source, re.M), (
        "the rename migration must spell its table list literally"
    )


def test_migration_targets_are_exactly_the_model_tables():
    mig = _load_migration()
    renamed_to = {new for _, new in mig.RENAMES}
    renamed_from = {old for old, _ in mig.RENAMES}
    model_tables = set(_mapped_tables())
    # Tables the migration leaves alone must already carry a prefix.
    untouched = model_tables - renamed_to
    for t in untouched:
        assert any(t.startswith(p) for p in AREAS), (
            f"{t} is neither renamed by the migration nor already prefixed"
        )
    # …and nothing is renamed INTO a name no model uses.
    assert renamed_to <= model_tables, sorted(renamed_to - model_tables)
    # No old name survives as a model table.
    assert not (renamed_from & model_tables), sorted(renamed_from & model_tables)


# ── The live database matches ───────────────────────────────


def test_the_test_database_has_only_prefixed_tables():
    """conftest builds the DB through ``alembic upgrade head`` — so if
    this passes, the migration ran and produced the model names."""
    insp = inspect(db.engine)
    present = set(insp.get_table_names()) - LIBRARY_TABLES
    assert present == set(_mapped_tables()), (
        f"db-only: {sorted(present - set(_mapped_tables()))}; "
        f"model-only: {sorted(set(_mapped_tables()) - present)}"
    )


def test_foreign_keys_point_at_renamed_tables():
    """SQLite rewrites REFERENCES clauses on rename only from 3.26 with
    legacy_alter_table off; Postgres tracks by oid. Either way, every
    FK must resolve to a table that exists under its new name."""
    insp = inspect(db.engine)
    tables = set(insp.get_table_names())
    dangling = []
    for t in tables - LIBRARY_TABLES:
        for fk in insp.get_foreign_keys(t):
            if fk["referred_table"] not in tables:
                dangling.append(f"{t} → {fk['referred_table']}")
    assert not dangling, dangling


def test_index_names_follow_the_renamed_tables():
    """``index=True`` columns derive ``ix_<table>_<col>``; the migration
    renames the stored index to match so autogenerate stays quiet."""
    insp = inspect(db.engine)
    mig = _load_migration()
    stale = []
    for old, new in mig.RENAMES:
        for ix in insp.get_indexes(new):
            name = ix.get("name") or ""
            if name.startswith(f"ix_{old}_"):
                stale.append(f"{new}: {name} still named after {old}")
    assert not stale, stale


# ── The doc is generated, and current ───────────────────────


def test_schema_doc_is_current():
    rendered = render_schema_doc(table_inventory())
    committed = (_REPO / "docs" / "SCHEMA.md").read_text()
    assert committed == rendered, (
        "docs/SCHEMA.md is stale — run `python -m scripts.dump_schema_doc`"
    )
