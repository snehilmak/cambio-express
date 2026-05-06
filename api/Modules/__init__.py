"""Bounded contexts. Each module is a self-contained vertical slice.

Per `docs/architecture/MIGRATION_ADR.md` §2, every module follows
the same five-layer shape:

    Modules/<Name>/
      Controllers/    # FastAPI APIRouter — request/response, no logic
      Services/       # business logic, workflows, transactions
      Repositories/   # DB queries
      Models/         # SQLAlchemy table definitions
      Requests/       # Pydantic schemas

Layer rules:
    Controller → Service     ✓
    Service    → Repository  ✓
    Service    → Provider    ✓
    Repository → Model       ✓
    everything else          ✗  (review-time check)

Modules MAY NOT import from each other's internals. Cross-module
needs go via Core (e.g. shared identifiers / events).
"""
