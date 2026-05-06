"""Customers module — Controllers (FastAPI router).

Mounts at `/api/v2/customers/*` (the parent router in `api/main.py`
adds `/customers`; the FastAPI app's `root_path="/api/v2"` carries
the version prefix).

Two routes today:

  GET  /search  → autocomplete; mirrors `/api/customers/search` Flask body.
  POST /upsert  → create or update a customer; mirrors
                  `find_or_upsert_customer` from app.py.

Auth gating is intentionally NOT here yet — auth migration is module
5 of 6 in the ADR. The dispatch path is internal-only at this point
(Flask still serves the user-facing transfer form, which calls the
legacy `/api/customers/search` route).

Layer rules:
    Controller → Service     ✓
    Controller → Repository  ✗
    Controller → DB session  ✓ (only via `Depends(get_db)`)
"""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Customers.Requests import (
    CustomerRow,
    CustomerSearchResponse,
    CustomerUpsertRequest,
    CustomerUpsertResponse,
)
from api.Modules.Customers.Services import search, upsert


router = APIRouter()


def _row(c, current_store_id: int, home_names: dict[int, str]) -> CustomerRow:
    """Adapter — turns a SQLAlchemy `Customer` row into the JSON shape
    the React frontend (and the legacy autocomplete) expects.

    Centralised so the search and upsert routes can't drift from each
    other on field naming or empty-value defaults.
    """
    return CustomerRow(
        id=c.id,
        full_name=c.full_name,
        dob=c.dob.isoformat() if c.dob else "",
        address=c.address or "",
        phone_country=c.phone_country or "",
        phone_number=c.phone_number or "",
        home_store_id=c.store_id,
        home_store_name=(
            home_names.get(c.store_id, "")
            if c.store_id != current_store_id else ""
        ),
    )


def _resolve_home_names(db: Session, rows, current_store_id: int) -> dict:
    """Bulk-fetch the Store names for every cross-store row in one query.
    Mirrors `app.py::api_customers_search`'s precompute step."""
    other_ids = {c.store_id for c in rows if c.store_id != current_store_id}
    if not other_ids:
        return {}
    from api.Modules.Customers.Models import Store
    return {
        s.id: s.name for s in
        db.query(Store).filter(Store.id.in_(other_ids)).all()
    }


@router.get("/search", response_model=CustomerSearchResponse)
def search_route(
    store_id: int = Query(
        ...,
        description=(
            "Caller's current store. Search is scoped to the owner "
            "umbrella that contains this store — sibling stores share "
            "their customer directory; unrelated stores stay isolated."
        ),
    ),
    q: str = Query(
        "", description="Search text. <2 chars returns an empty envelope.",
    ),
    db: Session = Depends(get_db),
) -> CustomerSearchResponse:
    matches, suggestions = search(db, store_id, q)
    home_names = _resolve_home_names(
        db, list(matches) + list(suggestions), store_id,
    )
    return CustomerSearchResponse(
        matches=[_row(c, store_id, home_names) for c in matches],
        suggestions=[_row(c, store_id, home_names) for c in suggestions],
    )


@router.post("/upsert", response_model=CustomerUpsertResponse)
def upsert_route(
    body: CustomerUpsertRequest,
    store_id: int = Query(..., description="Caller's current store."),
    db: Session = Depends(get_db),
) -> CustomerUpsertResponse:
    parsed_dob: date | None = None
    if body.dob:
        try:
            parsed_dob = datetime.strptime(body.dob, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail="dob must be YYYY-MM-DD",
            )
    cust = upsert(
        db, store_id, body.full_name,
        body.phone_country, body.phone_number,
        address=body.address, dob=parsed_dob,
        customer_id=body.customer_id,
    )
    db.commit()
    home_names = _resolve_home_names(db, [cust], store_id)
    return CustomerUpsertResponse(customer=_row(cust, store_id, home_names))
