# DineroBook Architecture Decision Records

This directory is the long-running record of architecture decisions for
DineroBook. Each ADR captures **a single decision**, the context it was
made in, and the tradeoffs we accepted — so that six months from now
the answer to "why is auth a JWT and not a session cookie?" is a single
file away.

## Format

Every ADR follows the same skeleton:

```
> Status: PROPOSED | ACCEPTED | SUPERSEDED-BY <other-adr> | REJECTED
> Last updated: YYYY-MM-DD
> Authors: …

## Context        — what's true today, what problem we're solving
## Decision       — the one-paragraph answer
## Consequences   — what changes, what gets harder, what we accept
## Alternatives   — what we considered and why we didn't pick them
## Implementation — concrete steps, file paths, migration order
```

We do not edit an accepted ADR in place. If the world changes, write
a follow-up ADR that supersedes it (link both ways) and update the
status header of the old one. The old reasoning stays readable.

## Index

| ID | Title | Status | Notes |
|---|---|---|---|
| [MIGRATION_ADR](MIGRATION_ADR.md) | Flask monolith → modular FastAPI + React SPA | ACCEPTED — executed | The umbrella ADR for the May 2026 migration. Everything below is a follow-up. |
| [ADR-001](ADR-001-spa-migration.md) | SPA migration recap | ACCEPTED — executed | What we actually shipped vs. what MIGRATION_ADR.md proposed. |
| [ADR-002](ADR-002-jwt-only-auth.md) | JWT-only auth (retire Flask cookie sessions) | PROPOSED | Tracks backlog D3. |
| [ADR-003](ADR-003-background-job-queue.md) | Background job queue (RQ + Redis) | PROPOSED | Tracks backlog D5. |
| [ADR-004](ADR-004-alembic-adoption.md) | Alembic for migrations | PROPOSED — phase 1 shipped | Tracks backlog D4. Baseline migration + scaffolding live; cutover (alembic stamp + retire `_ADDED_COLUMNS`) is a follow-up PR. Workflow doc: [migrations.md](migrations.md). |

## Runbooks + design docs (non-ADR)

| Doc | Topic |
|---|---|
| [request-lifecycle.md](request-lifecycle.md) | End-to-end trace of how a request flows from Cloudflare → Render → `asgi.py` → Flask Blueprint or FastAPI module → SQLAlchemy → Postgres. Also covers Sentry / structured-logs / request-ID middleware on both sides. Tracks backlog F2. |
| [migrations.md](migrations.md) | Alembic + `_ADDED_COLUMNS` workflow. Tracks ADR-004 phase 1. |
| [deployment.md](deployment.md) | Render deploy runbook — env vars, secret rotation, backup verification, data-retention purge, incident playbook. Tracks the "Deployment runbook" item in BACKLOG's "Before going live" list. |
| [MIGRATION_ADR.md](MIGRATION_ADR.md) | Umbrella ADR for the May 2026 SPA migration. |

## Writing a new ADR

1. Pick the next number. Don't reuse a superseded one.
2. Filename: `ADR-NNN-short-kebab-slug.md`.
3. Status starts at `PROPOSED`. Move to `ACCEPTED` only after the
   software lead signs off in a PR review.
4. Reference the BACKLOG item it tracks (if any) and link the ADR
   from the BACKLOG entry too.
5. Keep it short. An ADR is a decision artifact, not a design doc.
   If you need 10 pages, write a design doc and link to it.
