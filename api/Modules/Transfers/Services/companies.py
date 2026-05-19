"""Money-transfer company list resolution.

Per CLAUDE.md, the canonical money-transfer companies (Intermex,
Maxi, Barri) are the historical default. Stores can customise the
set via the `Store.companies` CSV column — `store_mt_companies`
is the only function that should read that column. Routes,
templates, and reports go through it so adding a new company is
one config change rather than a code change.

  - `DEFAULT_MT_COMPANIES` — list[str] used when a store has an
    empty / blank `Store.companies` value. Existing stores keep
    working the moment the migration lands, new stores get a
    sensible default on signup.
  - `store_mt_companies(store)` — split the CSV, strip whitespace,
    drop empties. Returns a fresh list every call so callers can
    mutate without affecting the default.

Pure read — no DB writes, no I/O.
"""
from typing import Any


# Default money-transfer companies for a fresh store.
DEFAULT_MT_COMPANIES: list[str] = ["Intermex", "Maxi", "Barri"]


def store_mt_companies(store: Any) -> list[str]:
    """The active list of money-transfer companies for a store.

    Falls back to `DEFAULT_MT_COMPANIES` when:
      - `store` is None (defensive — superadmin views, edge cases)
      - `Store.companies` is empty / whitespace-only

    Returns a fresh list every call (copy from DEFAULT_MT_COMPANIES
    or new list from CSV split), so callers can mutate freely.
    """
    if store is None or not (getattr(store, "companies", None) or "").strip():
        return list(DEFAULT_MT_COMPANIES)
    return [c.strip() for c in store.companies.split(",") if c.strip()]
