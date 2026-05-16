"""Customers module — Controllers (FastAPI router).

Mounts at `/api/v2/customers/*` (the parent router in `api/main.py`
adds `/customers`; the FastAPI app's `root_path="/api/v2"` carries
the version prefix).

Routes:

  GET  /search       → autocomplete; mirrors `/api/customers/search`
                        Flask body.
  POST /upsert       → create or update a customer; mirrors
                        `find_or_upsert_customer` from app.py.
  GET  /{id}         → single-customer detail (umbrella-scoped).
  GET  /export.csv   → admin-only CSV dump of every customer in the
                        owner umbrella. Streams as ``text/csv``
                        with a ``Content-Disposition`` filename.

The autocomplete + upsert routes still take ``?store_id=`` as a
query param (legacy callers); the export route reads the store
scope from the JWT claims so a cashier can't request another
store's directory by tweaking the URL.

Layer rules:
    Controller → Service     ✓
    Controller → Repository  ✓ (for read-only export)
    Controller → DB session  ✓ (only via `Depends(get_db)`)
"""
import csv
import io
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Auth.Controllers import get_principal
from api.Modules.Customers.Repositories import (
    find_by_id_in_stores,
    list_for_export,
    sibling_store_ids,
)
from api.Modules.Customers.Requests import (
    CustomerResponse,
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


@router.get("/export.csv")
def export_csv_route(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> Response:
    """Admin-only CSV dump of every customer in the caller's owner
    umbrella.

    Tenancy is derived from the JWT (``claims["store_id"]``) — not
    from a query param — so a cashier can't request another
    store's directory by tweaking the URL. Role gating mirrors
    the other admin-only exports (``/admin/tax-export.zip``):
    admin / owner / superadmin only.

    The CSV columns + ordering are the ones operators asked for
    in chat: identification first (name + phone), then context
    (DOB / address / home store) so a 1099 workflow can be done
    without bouncing back to the app.

    Declared BEFORE the ``/{customer_id}`` route so FastAPI's
    path matcher doesn't try to coerce ``"export.csv"`` to an
    integer ID first.
    """
    sid = claims.get("store_id")
    if sid is None:
        raise HTTPException(
            status_code=403,
            detail="JWT does not carry a store scope.",
        )
    if claims.get("role") not in ("admin", "owner", "superadmin"):
        raise HTTPException(
            status_code=403,
            detail="Only store admins can export the customer directory.",
        )
    sid = int(sid)
    siblings = sibling_store_ids(db, sid)
    rows = list_for_export(db, siblings)
    home_names = _resolve_home_names(db, rows, sid)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "Full name",
        "Phone country",
        "Phone number",
        "DOB",
        "Address",
        "Home store",
        "Created",
        "Last updated",
    ])
    for c in rows:
        w.writerow([
            c.full_name or "",
            c.phone_country or "",
            c.phone_number or "",
            c.dob.isoformat() if c.dob else "",
            c.address or "",
            (
                home_names.get(c.store_id, "")
                if c.store_id != sid else "(this store)"
            ),
            c.created_at.isoformat() if c.created_at else "",
            c.updated_at.isoformat() if c.updated_at else "",
        ])
    today = datetime.utcnow().strftime("%Y-%m-%d")
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition":
                f'attachment; filename="customers_{today}.csv"',
        },
    )


@router.get("/{customer_id}", response_model=CustomerResponse)
def get_route(
    customer_id: int = Path(..., ge=1),
    store_id: int = Query(
        ...,
        description=(
            "Caller's current store. Lookup is scoped to the owner "
            "umbrella that contains this store. Customers in unrelated "
            "stores 404."
        ),
    ),
    db: Session = Depends(get_db),
) -> CustomerResponse:
    siblings = sibling_store_ids(db, store_id)
    cust = find_by_id_in_stores(db, customer_id, siblings)
    if cust is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    home_names = _resolve_home_names(db, [cust], store_id)
    return CustomerResponse(customer=_row(cust, store_id, home_names))
