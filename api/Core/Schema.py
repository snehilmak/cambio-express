"""Table-naming convention (S-1).

Every application table is named ``<area>_<thing>``. The prefix says
what part of the product a table belongs to — which module folder
owns it and which ``INVARIANTS.md`` to read before touching it. It
is deliberately an *area*, not a tenancy marker: whether a row is
pinned to one store is already visible on the row as ``store_id``,
and tables like auth, billing and audit serve every product line.

Adding a table
--------------
1. Put the model in the module that owns it.
2. Name the table with that module's prefix from ``MODULE_PREFIX``.
3. Run ``python -m scripts.dump_schema_doc`` and commit the
   regenerated ``docs/SCHEMA.md``.

``tests/Core/test_table_prefixes.py`` fails when a model's table
does not start with its module's prefix, when a module with models
is missing from the map, or when the committed doc is stale.

Adding a module
---------------
Add it to ``MODULE_PREFIX``. Prefer an existing area; a new area
needs a row in ``AREAS`` too, with a one-line description of what
belongs there.

Library-owned tables (``alembic_version``, ``casbin_rule``) keep
their upstream names and are listed in ``LIBRARY_TABLES``.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Table

# Area prefix → what belongs there. Ten areas; two of them carry the
# product line (msb / retail), the other eight name shared layers
# explicitly instead of lumping them under "global".
AREAS: dict[str, str] = {
    "tenancy_": "Who exists: stores, users, employees, owner links, "
                "roles. The rows everything else points at.",
    "auth_": "Credentials and sessions. Governed by Auth/INVARIANTS.md; "
             "changes need the security-review header.",
    "billing_": "Plans, feature flags, discounts, referrals. Stripe is "
                "the counterpart.",
    "platform_": "Superadmin-owned, no store: settings, webhook ingest, "
                 "announcements, push.",
    "support_": "Tickets between a store and the platform.",
    "audit_": "Append-only history. Never edited, never purged early.",
    "bank_": "Bank feed via Stripe Financial Connections. Shared across "
             "product lines.",
    "hr_": "Time clock now, payroll later. People-hours, not money.",
    "msb_": "Remittance money: transfers, senders, ACH batches, the MSB "
            "daily book, monthly P&L, returned checks, the rate board.",
    "retail_": "C-store money: registers, departments, the Store daily "
               "book, lottery, POS journal ingest, price book, vendors, "
               "purchases.",
}

# Module folder under api/Modules → area prefix. A module may only
# map to ONE prefix; several modules may share one.
MODULE_PREFIX: dict[str, str] = {
    "Tenancy": "tenancy_",
    "Auth": "auth_",
    "Billing": "billing_",
    "FeatureFlags": "billing_",
    "Superadmin": "platform_",
    "Webhooks": "platform_",
    "Announcements": "platform_",
    "Support": "support_",
    "Audit": "audit_",
    "BankSync": "bank_",
    "TimeClock": "hr_",
    "Transfers": "msb_",
    "Customers": "msb_",
    "Batches": "msb_",
    "DailyBook": "msb_",
    "Monthly": "msb_",
    "ReturnChecks": "msb_",
    "TVDisplay": "msb_",
    "DayClose": "retail_",
    "StoreBook": "retail_",
    "Lottery": "retail_",
    "PosImport": "retail_",
    "Catalog": "retail_",
}

LIBRARY_TABLES: frozenset[str] = frozenset({"alembic_version", "casbin_rule"})


@dataclass(frozen=True)
class TableInfo:
    table: str
    model: str
    module: str
    prefix: str
    scope: str            # "global" | "store" | "user" | "owner" | "<parent> (FK)"
    foreign_keys: tuple[str, ...]
    invariants: str | None  # repo-relative path when the module has one


def module_of(model_cls: type) -> str:
    """``api.Modules.Lottery.Models`` → ``"Lottery"``. Raises for a
    model that does not live under api/Modules."""
    parts = model_cls.__module__.split(".")
    if len(parts) < 3 or parts[:2] != ["api", "Modules"]:
        raise ValueError(
            f"{model_cls.__name__} lives in {model_cls.__module__}, "
            "not under api.Modules"
        )
    return parts[2]


def _scope(columns: set[str], fks: list[str], prefix: str) -> str:
    """What a row is pinned to. ``store`` / ``owner`` / ``user`` when
    the column is on the row; ``<parent> (FK)`` for a child table that
    hangs off a parent in the SAME area (``msb_tv_display_rate`` →
    ``msb_tv_display_payout_bank``); otherwise ``global``. A foreign
    key into another area (Store → referral code) is a reference, not
    a scope."""
    if "store_id" in columns:
        return "store"
    if "owner_id" in columns:
        return "owner"
    if "user_id" in columns:
        return "user"
    for fk in fks:
        parent = fk.split(".")[0]
        if prefix and parent.startswith(prefix):
            return f"{parent} (FK)"
    return "global"


def load_all_models() -> None:
    """Import every ``api.Modules.<X>.Models`` package.

    ``create_app()`` is not enough: some modules (Superadmin,
    TVDisplay, Webhooks) import their models lazily inside request
    handlers, so their tables are missing from ``Base.metadata``
    until the first request touches them. An inventory built on top
    of that would silently drop a dozen tables.
    """
    root = Path(__file__).resolve().parents[1] / "Modules"
    for d in sorted(root.iterdir()):
        if (d / "Models").is_dir() or (d / "Models.py").exists():
            importlib.import_module(f"api.Modules.{d.name}.Models")


def table_inventory() -> list[TableInfo]:
    """One row per mapped model, sorted by prefix then name. Not for
    use from a migration — it imports application code."""
    from api.Core.Database.session import Base

    load_all_models()
    repo = Path(__file__).resolve().parents[2]
    rows: list[TableInfo] = []
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        table = mapper.local_table
        if not isinstance(table, Table):
            continue
        module = module_of(cls)
        cols = {c.name for c in table.columns}
        fks = sorted({
            f"{fk.column.table.name}.{fk.column.name}"
            for fk in table.foreign_keys
        })
        inv = repo / "api" / "Modules" / module / "INVARIANTS.md"
        prefix = MODULE_PREFIX.get(module, "")
        rows.append(TableInfo(
            table=str(table.name),
            model=cls.__name__,
            module=module,
            prefix=prefix,
            scope=_scope(cols, fks, prefix),
            foreign_keys=tuple(fks),
            invariants=(
                f"api/Modules/{module}/INVARIANTS.md" if inv.exists() else None
            ),
        ))
    order = {p: i for i, p in enumerate(AREAS)}
    rows.sort(key=lambda r: (order.get(r.prefix, 99), r.table))
    return rows


def render_schema_doc(rows: list[TableInfo]) -> str:
    """docs/SCHEMA.md — generated; do not edit by hand."""
    out: list[str] = []
    out.append("# Database schema map\n")
    out.append(
        "> **Generated** by `python -m scripts.dump_schema_doc` from the "
        "SQLAlchemy models. Do not edit by hand — "
        "`tests/Core/test_table_prefixes.py` fails when this file is "
        "stale.\n"
    )
    out.append(
        "Every table is named `<area>_<thing>`. The prefix says which "
        "part of the product owns it; whether a row is pinned to one "
        "store is on the row itself as `store_id`. Convention and "
        "module map: `api/Core/Schema.py`.\n"
    )
    out.append("## Areas\n")
    out.append("| Prefix | What belongs there | Modules |")
    out.append("|---|---|---|")
    for prefix, what in AREAS.items():
        mods = ", ".join(sorted(m for m, p in MODULE_PREFIX.items() if p == prefix))
        out.append(f"| `{prefix}` | {what} | {mods} |")
    out.append("")
    out.append(
        f"Library-owned, not renamed: "
        + ", ".join(f"`{t}`" for t in sorted(LIBRARY_TABLES))
        + ".\n"
    )
    current = None
    for r in rows:
        if r.prefix != current:
            current = r.prefix
            out.append(f"## `{current}`\n")
            out.append("| Table | Model | Module | Scope | Foreign keys | Read first |")
            out.append("|---|---|---|---|---|---|")
        fks = ", ".join(f"`{f}`" for f in r.foreign_keys) or "—"
        inv = f"[INVARIANTS]({'../' + r.invariants})" if r.invariants else "—"
        out.append(
            f"| `{r.table}` | `{r.model}` | `{r.module}` | {r.scope} | {fks} | {inv} |"
        )
        if r is rows[-1] or rows[rows.index(r) + 1].prefix != current:
            out.append("")
    return "\n".join(out).rstrip() + "\n"


__all__ = [
    "AREAS", "LIBRARY_TABLES", "MODULE_PREFIX", "TableInfo",
    "load_all_models", "module_of", "render_schema_doc",
    "table_inventory",
]
