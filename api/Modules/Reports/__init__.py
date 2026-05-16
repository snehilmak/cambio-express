"""Reports module.

Five layers (per ``docs/architecture/MIGRATION_ADR.md`` §2):

    Models/        — re-exports of the SQLAlchemy models the
                     reports read from. Tables live in their
                     owner modules (Transfers, BankSync, etc.).
    Repositories/  — query intent → DB. One method = one query.
    Services/      — business logic (period math, grouping rules,
                     CSV/JSON formatting). Composes repositories.
    Requests/      — Pydantic schemas (request + response).
    Controllers/   — FastAPI APIRouter. Validates input, delegates
                     to services, serializes output.

Reports is the reference implementation later modules copied
the layer shape from — read-heavy and self-contained (no writes,
no external integrations beyond the DB).
"""
