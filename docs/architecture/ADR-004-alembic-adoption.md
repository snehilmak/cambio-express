# ADR-004 — Alembic for migrations

> **Status:** PROPOSED.
> **Last updated:** 2026-05-11
> **Authors:** Claude (drafting).
> **Tracked by:** BACKLOG.md item D4.

## Context

Today every schema change happens in one of two places in `app.py`:

1. **New tables** — define the `db.Model` class. `db.create_all()`
   on boot creates it. Idempotent.
2. **New columns on existing tables** — append a tuple to
   `_ADDED_COLUMNS` near the bottom of `app.py`:
   ```python
   ("table_name", "column_name", "<DDL after ADD COLUMN>"),
   ```
   `_ensure_added_columns()` runs on boot and is idempotent — safe
   on every restart.

This is intentionally low-ceremony and has worked well for ~18 months
of solo development. The problems we've started hitting:

- **No `DROP COLUMN`, no `RENAME COLUMN`, no `ALTER COLUMN TYPE`.**
  `_ADDED_COLUMNS` only handles `ADD COLUMN`. CLAUDE.md explicitly
  says "Never drop a column from a running database — rename/backfill
  in a follow-up deploy if you really need to remove one." That
  workaround is fine when the answer is "live with a dead column
  forever" but bad when we actually need to evolve the schema.
- **No backfill story.** Adding `Customer.preferred_language NOT NULL
  DEFAULT 'en'` is fine. Adding `Transfer.total_collected_cents` and
  copying the value from `total_collected * 100` is currently a
  manual SQL script someone has to remember to run.
- **No way to test a migration.** `_ADDED_COLUMNS` runs at boot, but
  the test suite uses `db.create_all()` against a fresh in-memory
  SQLite — it doesn't exercise the migration path at all. A bug in
  the DDL would only show up on the next Render deploy.
- **No rollback.** Production is an irreversible append-only schema
  in the current model. If a deploy is bad, the only "rollback" is
  another forward migration.
- **No multi-developer story.** Solo dev today, but the moment two
  branches both add a column, `_ADDED_COLUMNS` becomes a merge
  conflict zone with no enforcement that the rows are in the right
  order.
- **No customer-deployable story.** MIGRATION_ADR.md §3 commits to
  customer-deployable Docker images. Those need a real
  forward-rolling migration tool; the customer can't be expected to
  read `_ADDED_COLUMNS` and run idempotent boot DDL.

## Decision

**Adopt Alembic** (SQLAlchemy's official migration tool) and pin the
current production schema as the baseline migration. Going forward,
every schema change ships as an Alembic revision; `_ADDED_COLUMNS` and
the boot-time DDL run get retired.

Concretely:

- **One `alembic/` directory** at the repo root with `env.py`
  configured to read `DATABASE_URL` and use the existing
  `db.metadata` for autogenerate.
- **Baseline migration** — single revision that captures every
  table and column that exists in production as of cutover. New
  installs run the baseline; existing prod runs `alembic stamp head`
  once during the cutover deploy (no DDL — just marks the baseline
  as applied).
- **`alembic upgrade head` on every deploy.** Render's `preDeploy`
  hook in `render.yaml` runs the upgrade before the new web/worker
  containers go live.
- **Autogenerate-assisted revisions.** Developer changes a model,
  runs `alembic revision --autogenerate -m "add preferred_language
  to customer"`, reviews the generated DDL, edits if needed, commits.
- **Backfill steps as separate revisions** when needed —
  `op.execute("UPDATE …")` inside the revision script, or a Python
  `op.bulk_insert` / data-migration block.
- **Migration tests.** A pytest fixture runs `alembic upgrade head`
  against a fresh test DB and confirms it matches the live model
  metadata. CI gate catches drift.

## Consequences

What this unlocks:

- **Real schema evolution.** Drop columns, rename, alter types,
  backfill — all become normal PRs instead of "live with the
  legacy column forever."
- **Reviewable DDL diffs.** Every migration is a Python file in the
  PR. Reviewers see exactly what runs.
- **Rollback path.** `alembic downgrade -1` exists. We won't use it
  often (forward-rolling is healthier) but it's there for an
  emergency.
- **Test parity.** Test DB exercises the same migration path as
  production. A migration bug fails CI, not Render-deploy-at-2am.
- **Customer-deployable schema.** The Docker image runs
  `alembic upgrade head` on container start; the customer doesn't
  have to know what schema version they're on.

What gets harder:

- **One more boot step.** Web container can't start before
  `alembic upgrade head` completes. Mitigation: Render's
  `preDeploy` hook runs the migration before the new container
  receives traffic. Old container keeps serving until the new one
  passes health checks.
- **Merge conflicts on `alembic/versions/`.** Two branches each
  add a revision → both have a child of the same parent → conflict
  on the `down_revision`. Standard Alembic problem; resolved with
  `alembic merge`. We'll document the resolution pattern in
  `docs/architecture/migrations.md` after the first conflict.
- **Autogenerate isn't perfect.** It misses index renames, some
  constraint changes, and anything custom. Every autogenerated
  revision needs human review before commit. (Same standard as
  every other Alembic project.)

What we accept:

- **A one-time cutover step.** On the deploy that introduces Alembic
  we have to `alembic stamp head` against production before the
  upgrade runs — to tell Alembic "the baseline is already applied;
  don't try to run those CREATE TABLE statements." Documented in
  the cutover runbook.
- **`_ADDED_COLUMNS` and `_ensure_added_columns` get deleted.** No
  dual mechanism. Once Alembic is in, it's the only path.

## Alternatives

| Option | Why we didn't pick it |
|---|---|
| Keep `_ADDED_COLUMNS` forever | Doesn't solve drop/rename/backfill. Customer-deployable variant can't ship without a real migration tool. |
| Flask-Migrate | Thin wrapper around Alembic. We'd end up with the same Alembic surface plus a Flask import dependency that's about to go away (MIGRATION_ADR.md §2: Flask is being removed). |
| Yoyo, golang-migrate, dbmate, etc. | Decent options but none integrate with SQLAlchemy's `db.metadata` for autogenerate. We'd lose half the value. |
| Atlas / Skeema (declarative) | Interesting model — declare the desired schema, tool diffs against live and applies. Powerful but adds a non-Python tool to the deploy pipeline and the team would need to learn it. Not enough leverage over Alembic. |
| Wait until production is hot | We're early enough that the cutover cost is low. Doing this *before* we have to drop a column under pressure is the cheap path. |

## Implementation

Suggested PR sequence. Each step ships independently.

1. **Snapshot the current schema.** Dump production schema (no data)
   to a SQL file checked into `docs/architecture/schema-baseline-2026-05.sql`
   so we have a reference if Alembic's autogenerate gets it wrong.
2. **Add Alembic scaffolding.** `alembic init alembic/`. Configure
   `env.py` to read `DATABASE_URL` from env, point
   `target_metadata` at `db.metadata`. Pin Alembic version in
   `requirements.txt`.
3. **Generate baseline.** `alembic revision --autogenerate -m
   "baseline 2026-05"`. Compare the generated revision to the live
   schema (and to `schema-baseline-2026-05.sql`). Fix any drift
   manually. Commit.
4. **Wire into deploy.** Add `preDeploy: alembic upgrade head` to
   `render.yaml`. On the test DB, the fresh `db.create_all()` path
   stays for fixtures; a separate test confirms `alembic upgrade
   head` against an empty DB produces the same schema.
5. **Cutover deploy.** Run `alembic stamp head` against production
   *before* the new container goes live. (Render shell or a one-
   off Render job.) Then deploy the PR that adds `preDeploy: alembic
   upgrade head`. Old container served traffic; new container runs
   migrations on boot (no-op since stamped); becomes live.
6. **Retire `_ADDED_COLUMNS`.** Follow-up PR deletes the constant +
   `_ensure_added_columns()` + the boot-time call site. Any pending
   schema changes that were going to use `_ADDED_COLUMNS` get
   converted to Alembic revisions first.
7. **Document the workflow.** `docs/architecture/migrations.md` —
   how to write a revision, how to autogenerate, how to handle
   conflicts, how to backfill, how to roll back.

## Open questions

- **SQLite vs. Postgres dialect differences.** Dev uses SQLite, prod
  uses Postgres. Alembic mostly papers over this but some DDL is
  dialect-specific (e.g. `ALTER COLUMN TYPE` works differently on
  SQLite which mostly requires table rebuild). For now: document
  the difference, prefer Postgres-compatible patterns, accept that
  some migrations may need a `if dialect == "sqlite"` branch.
- **Online migrations on Postgres.** Drop column with billions of
  rows blocks. Not a problem today (small data) but eventually we
  want pt-osc / pg-online-schema-change patterns. Out of scope for
  this ADR; revisit when row counts grow.
- **`db.create_all()` in tests.** Tests use an in-memory SQLite DB
  created via `db.create_all()`. That stays — the migration path is
  separately tested by the "fresh DB through Alembic" pytest
  fixture. Tests don't pay the Alembic cost per-run.

## Changelog

- **2026-05-11** — Initial draft, status PROPOSED.
