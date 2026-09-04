"""Regenerate docs/SCHEMA.md from the SQLAlchemy models.

    python -m scripts.dump_schema_doc          # write the file
    python -m scripts.dump_schema_doc --check  # exit 1 if stale

The doc is the developer-facing map of every table: area prefix,
owning module, scope, foreign keys, and the INVARIANTS.md to read
first. ``tests/Core/test_table_prefixes.py`` runs the ``--check``
logic so a model change that forgets to regenerate fails CI.
"""
from __future__ import annotations

import sys
from pathlib import Path

from api.Core.Schema import render_schema_doc, table_inventory

DOC = Path(__file__).resolve().parents[1] / "docs" / "SCHEMA.md"


def main(argv: list[str]) -> int:
    rendered = render_schema_doc(table_inventory())
    if "--check" in argv:
        current = DOC.read_text() if DOC.exists() else ""
        if current != rendered:
            print(
                f"{DOC.relative_to(DOC.parents[1])} is stale — run "
                "`python -m scripts.dump_schema_doc`",
                file=sys.stderr,
            )
            return 1
        print("docs/SCHEMA.md is current")
        return 0
    DOC.write_text(rendered)
    print(f"wrote {DOC.relative_to(DOC.parents[1])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
