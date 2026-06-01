"""Tiny CSV-construction helper for the parts of the codebase
that produce CSV strings/responses but don't fit the
``Reports/Controllers/csv_export.py`` registry (which is bound to
the date-range report pattern).

Currently used by:
  - ``Admin/Services/tax_pack.py`` — multi-CSV tax-prep ZIP
  - Other ad-hoc CSV builders that needed only the StringIO ↔
    csv.writer ↔ headers+rows mechanics

If a caller needs the report-registry pattern (period filter +
auto-attachment response), use
``Reports/Controllers/csv_export.py`` instead.
"""
from __future__ import annotations

import csv
import io
from typing import Iterable, Sequence


def build_csv(
    headers: Sequence[str],
    rows: Iterable[Sequence[object]],
) -> str:
    """Render ``headers`` + ``rows`` as a CSV string. Empty rows
    iterable produces a header-only CSV. Each row's values are
    passed through csv.writer's default formatting (which calls
    ``str()`` on each value)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(list(headers))
    for row in rows:
        w.writerow(list(row))
    return buf.getvalue()
