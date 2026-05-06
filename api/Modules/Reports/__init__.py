"""Reports module — first vertical slice migrated per the ADR.

Five layers (per `docs/architecture/MIGRATION_ADR.md` §2):

    Models/        — re-exports of the legacy SQLAlchemy models
                     during migration; eventually owns its own
                     model definitions when sibling modules
                     finish migrating their tables.
    Repositories/  — query intent → DB. One method = one query.
    Services/      — business logic (period math, grouping rules,
                     CSV/JSON formatting). Composes repositories.
    Requests/      — Pydantic schemas (request + response).
    Controllers/   — FastAPI APIRouter. Validates input, delegates
                     to services, serializes output.

Reports was picked first because it's read-heavy and self-contained
(no writes, no external integrations beyond the DB). It's the
reference implementation every later module copies the shape from.
"""
