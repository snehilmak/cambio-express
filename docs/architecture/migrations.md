# Database migrations workflow

> See also: [ADR-004 — Alembic adoption](ADR-004-alembic-adoption.md).

DineroBook is mid-migration between two schema-evolution mechanisms:

| | Legacy (still active) | Target |
|---|---|---|
| Mechanism | `_ADDED_COLUMNS` list + `_ensure_added_columns()` in `app.py` | Alembic revisions in `alembic/versions/` |
| Triggered by | Every app boot | `alembic upgrade head` on deploy |
| Capabilities | `ADD COLUMN` only, idempotent | Full DDL — drop, rename, alter, backfill, downgrade |

The cutover is staged across multiple PRs so production never sees
both running at the same time. This doc describes how to write
schema changes today (during the staged migration) and how the flow
shifts once the cutover lands.

## Today — both mechanisms coexist

Until the cutover PR retires `_ADDED_COLUMNS`:

- **`db.create_all()` runs on every app boot** and picks up new
  tables from `db.metadata`.
- **`_ensure_added_columns()` runs on every app boot** and applies
  every entry in `_ADDED_COLUMNS`. Idempotent.
- **Alembic baseline migration exists** (`alembic/versions/*baseline*.py`)
  but is **never auto-run**. It encodes the exact schema that
  `db.create_all` + `_ensure_added_columns` produce, so a fresh
  install can be brought up via either mechanism.

### Adding a new column today

Still do what you've always done — add a row to `_ADDED_COLUMNS`:

```python
("table_name", "column_name", "<DDL after ADD COLUMN>"),
```

And in the same PR, add a follow-up Alembic revision so the two
stay in sync:

```bash
DINEROBOOK_SKIP_INIT_DB=1 \
DATABASE_URL=sqlite:///tmp/scratch.db \
SECRET_KEY=dev \
STRIPE_SECRET_KEY=sk_test \
STRIPE_BASIC_PRICE_ID=p \
STRIPE_PRO_PRICE_ID=p \
STRIPE_WEBHOOK_SECRET=ws \
alembic revision --autogenerate -m "add <column> to <table>"
```

Review the generated revision under `alembic/versions/`, then commit
it. The `test_alembic_baseline_produces_same_columns_as_create_all`
test in `tests/test_alembic_baseline.py` will fail in CI if the
Alembic revisions drift from `db.metadata`.

### Adding a new table today

`db.create_all()` picks it up automatically. Generate the matching
Alembic revision in the same PR (same command as above) so a future
`alembic upgrade head` against a stamped DB will create it too.

## Cutover PR (future)

The cutover PR (per ADR-004 §6) does three things in one deploy:

1. Runs `alembic stamp head` against production once to mark the
   baseline as applied (no DDL).
2. Adds `preDeploy: alembic upgrade head` to `render.yaml`.
3. Deletes `_ADDED_COLUMNS` and `_ensure_added_columns()` from
   `app.py`.

After the cutover, `db.create_all()` stays — it's still used by the
test suite, which creates a fresh in-memory SQLite DB per session.

## After cutover — Alembic only

The standard SQLAlchemy / Alembic workflow:

1. Change a model in `api/Modules/<Module>/Models/` (or, while the
   monolith still owns models, in `app.py`).
2. Generate a revision:
   ```bash
   alembic revision --autogenerate -m "what changed"
   ```
3. **Review the generated revision.** Autogenerate isn't perfect — it
   misses index renames, some constraint changes, and anything
   custom. Edit the upgrade/downgrade bodies as needed.
4. Run it locally:
   ```bash
   alembic upgrade head
   ```
5. Run the test suite. The Alembic-baseline-parity test in
   `tests/test_alembic_baseline.py` will catch drift.
6. Open the PR. The Render deploy runs `alembic upgrade head` before
   the new container goes live.

## Merge conflicts

Two branches each add a revision → both have a child of the same
parent → conflict on `down_revision`. Resolve with:

```bash
alembic merge -m "merge <branch-a> and <branch-b>" <rev-a> <rev-b>
```

That creates a merge revision with both parents. Future revisions
point at the merge.

## Backfills

When a new column needs values from existing rows, do it in two
revisions:

1. Revision A — add the column, nullable, no default.
2. Revision B — `op.execute("UPDATE …")` or
   `op.bulk_insert(...)`, then alter the column to `NOT NULL`.

That way A can deploy first (zero-downtime — old code ignores the
new nullable column), then B can backfill safely while the new
code is reading the column.

## Rolling back

`alembic downgrade -1` exists. Use it sparingly — forward-rolling is
the healthier pattern in production. The downgrade path is mostly
useful for local development ("oops, that wasn't the change I
meant") and emergencies.

## Test environment

Tests don't run Alembic on every fixture setup — they use
`db.create_all()` against an in-memory SQLite per conftest, which
is faster. The dedicated `tests/test_alembic_baseline.py` suite
runs the migration once per session and asserts schema parity, so
drift is caught without paying the migration cost on every test.

## Dialect notes

- **Postgres (prod):** all DDL works. `op.alter_column` for type /
  default changes runs in place.
- **SQLite (dev / test):** ALTER TABLE is limited. Alembic batch
  mode (`render_as_batch=True` in `alembic/env.py`) papers over
  most of it by rebuilding the table when needed. Some constraint
  changes still fall through; if a revision blows up on SQLite but
  works on Postgres, branch on `op.get_context().dialect.name`.

## When NOT to use Alembic

- **Data backfills that take >5 minutes on a large table.** Alembic
  holds a table lock during ALTER. Use a separate management script
  outside the migration framework for long-running data fixes.
- **Multi-step "expand / migrate / contract"** patterns for
  zero-downtime breaking changes. Each phase ships as its own
  Alembic revision but the orchestration lives in the PR
  description + the deploy runbook.
