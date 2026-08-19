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

Since the Settings "Money transfer companies" section landed, the
roster also carries an enabled/disabled toggle per company: the
`Store.companies_disabled` CSV holds the subset of the roster that's
toggled OFF. A disabled company keeps its historical data (the
MT-summary rows still reference it by name) but is hidden from the
daily book's breakdown and the transfer form.

Pure functions — no DB writes, no I/O. The write path goes through
`update_store_info` (Admin Services), which encodes via
`encode_mt_companies` below.
"""
from typing import Any


# Default money-transfer companies for a fresh store.
DEFAULT_MT_COMPANIES: list[str] = ["Intermex", "Maxi", "Barri"]

# Roster limits. Company names land in MoneyTransferSummary.company
# (String(40)) so the per-name cap must not exceed that column.
MAX_MT_COMPANIES = 20
MAX_MT_COMPANY_NAME_LEN = 40


def _split_csv(raw: Any) -> list[str]:
    return [c.strip() for c in str(raw or "").split(",") if c.strip()]


def store_mt_company_roster(store: Any) -> list[tuple[str, bool]]:
    """The store's full company roster as ``(name, enabled)`` pairs,
    in roster order. Falls back to `DEFAULT_MT_COMPANIES` (all
    enabled unless individually disabled) when the store is None or
    `Store.companies` is empty — same fallback contract as
    `store_mt_companies`. This is the Settings read shape.
    """
    roster = _split_csv(getattr(store, "companies", None) if store else None)
    if not roster:
        roster = list(DEFAULT_MT_COMPANIES)
    disabled = {
        c.lower()
        for c in _split_csv(
            getattr(store, "companies_disabled", None) if store else None
        )
    }
    return [(name, name.lower() not in disabled) for name in roster]


def store_mt_companies(store: Any) -> list[str]:
    """The ACTIVE list of money-transfer companies for a store —
    the roster minus any toggled-off names. This is what the daily
    book breakdown and the transfer form consume.

    Falls back to `DEFAULT_MT_COMPANIES` when:
      - `store` is None (defensive — superadmin views, edge cases)
      - `Store.companies` is empty / whitespace-only

    Returns a fresh list every call, so callers can mutate freely.
    """
    return [name for name, enabled in store_mt_company_roster(store) if enabled]


def encode_mt_companies(entries: list[Any]) -> tuple[str, str]:
    """Validate + encode the Settings payload (a list of objects with
    ``name`` + ``enabled``) into the two CSV columns
    ``(companies, companies_disabled)``. Raises ValueError with an
    operator-readable message on bad input.

    Rules:
      - 1..MAX_MT_COMPANIES companies on the roster
      - names trimmed, non-empty, ≤MAX_MT_COMPANY_NAME_LEN chars
      - no commas in a name (CSV encoding)
      - no case-insensitive duplicates
    An all-disabled roster is allowed — the daily book + transfer
    form show their empty states until something is re-enabled.
    """
    names: list[str] = []
    disabled: list[str] = []
    seen: set[str] = set()
    for e in entries:
        name = str(getattr(e, "name", None) or (
            e.get("name") if isinstance(e, dict) else ""
        ) or "").strip()
        enabled = bool(getattr(e, "enabled", None) if not isinstance(e, dict)
                       else e.get("enabled", True))
        if not name:
            raise ValueError("Company names cannot be empty.")
        if len(name) > MAX_MT_COMPANY_NAME_LEN:
            raise ValueError(
                f"Company name {name!r} is too long "
                f"(max {MAX_MT_COMPANY_NAME_LEN} characters)."
            )
        if "," in name:
            raise ValueError("Company names cannot contain commas.")
        key = name.lower()
        if key in seen:
            raise ValueError(f"Duplicate company {name!r}.")
        seen.add(key)
        names.append(name)
        if not enabled:
            disabled.append(name)
    if not names:
        raise ValueError("Keep at least one money-transfer company.")
    if len(names) > MAX_MT_COMPANIES:
        raise ValueError(
            f"At most {MAX_MT_COMPANIES} companies are supported."
        )
    return ",".join(names), ",".join(disabled)
