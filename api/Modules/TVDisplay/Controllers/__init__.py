"""TV Display module — Controllers (FastAPI router).

Mounts at `/api/v2/tv-display/*`. Endpoints:

  GET /tv-display/overview            → display config + countries
       with bank/rate counts + active Fire TV pairing summary.
  GET /tv-display/countries/{id}      → full drill-down for one
       country (banks with sparse rate matrix).

Auth + gating: requires JWT principal scoped to a store; admin
or employee role; the store must have the `tv_display` add-on
active. Mirrors the legacy `_tv_required()` guard.

Read-only by design. Write-side (mint countries, edit rates,
pair/revoke Fire TVs) stays on the legacy Flask routes for now —
those endpoints integrate with token rotation, MT-company catalog
auto-slug, and the per-device pairing flow that's safer to leave
on the existing tested code path until the WSGI bridge retires.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Auth.Controllers import get_principal
from api.Modules.TVDisplay.Requests import (
    TVDisplayBankRow,
    TVDisplayCountryDetailResponse,
    TVDisplayCountryStat,
    TVDisplayOverviewResponse,
    TVPairingSummary,
)


router = APIRouter()


def _require_tv_store(claims: dict, db: Session):
    """Mirrors legacy `_tv_required()`: store-scoped JWT, admin or
    employee role, store has the tv_display add-on active."""
    sid = claims.get("store_id")
    if sid is None:
        raise HTTPException(status_code=404, detail="Not found")
    if claims.get("role") not in ("admin", "employee"):
        raise HTTPException(status_code=404, detail="Not found")
    from app import Store, store_has_addon
    store = db.query(Store).filter(Store.id == int(sid)).one_or_none()
    if store is None:
        raise HTTPException(status_code=404, detail="Not found")
    if not store_has_addon(store, "tv_display"):
        raise HTTPException(
            status_code=409,
            detail=(
                "The TV Display add-on isn't active for this store. "
                "Turn it on from your subscription page."
            ),
        )
    return store


def _iso(dt) -> str:
    return dt.isoformat() if dt else ""


def _csv_split(s: str) -> list[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def _ensure_display(db: Session, store):
    """Get-or-create the store's TVDisplay row. Mirrors legacy
    `_ensure_tv_display()` but routes through the FastAPI session."""
    import secrets
    from app import TVDisplay
    d = db.query(TVDisplay).filter(TVDisplay.store_id == store.id).one_or_none()
    if d is None:
        d = TVDisplay(
            store_id=store.id, public_token=secrets.token_urlsafe(24),
        )
        db.add(d)
        db.commit()
        db.refresh(d)
    return d


@router.get("/overview", response_model=TVDisplayOverviewResponse)
def overview_route(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> TVDisplayOverviewResponse:
    """Per-store TV display config + countries with stats + active
    Fire TV pairing (if any). Same data the legacy /tv-display
    landing page renders — just JSON-shaped."""
    store = _require_tv_store(claims, db)
    display = _ensure_display(db, store)
    from app import TVDisplayCountry, TVDisplayPayoutBank, TVDisplayRate, TVPairing
    countries = (
        db.query(TVDisplayCountry)
          .filter(TVDisplayCountry.display_id == display.id)
          .order_by(TVDisplayCountry.sort_order, TVDisplayCountry.id)
          .all()
    )
    country_rows: list[TVDisplayCountryStat] = []
    for c in countries:
        bank_count = (
            db.query(TVDisplayPayoutBank)
              .filter(TVDisplayPayoutBank.country_id == c.id)
              .count()
        )
        rate_count = (
            db.query(TVDisplayRate)
              .join(
                  TVDisplayPayoutBank,
                  TVDisplayRate.bank_id == TVDisplayPayoutBank.id,
              )
              .filter(TVDisplayPayoutBank.country_id == c.id)
              .count()
        )
        country_rows.append(TVDisplayCountryStat(
            id=c.id,
            country_code=c.country_code or "",
            country_name=c.country_name or "",
            sort_order=c.sort_order or 0,
            mt_companies=c.mt_companies or "",
            bank_count=bank_count,
            rate_count=rate_count,
        ))
    pairing_row = (
        db.query(TVPairing)
          .filter(
              TVPairing.display_id == display.id,
              TVPairing.revoked_at.is_(None),
          )
          .order_by(TVPairing.paired_at.desc())
          .first()
    )
    pairing_summary = None
    if pairing_row is not None:
        pairing_summary = TVPairingSummary(
            id=pairing_row.id,
            device_label=pairing_row.device_label or "",
            paired_at=_iso(pairing_row.paired_at),
            last_seen_at=_iso(pairing_row.last_seen_at),
        )
    # Public URL: assembled relative to the request host. The token
    # is non-secret in the sense that anyone with it can view, but we
    # don't hardcode the domain — the legacy admin page uses
    # `url_for(_external=True)` which respects SERVER_NAME / Forwarded.
    # Here we return the path-only form; the SPA already knows its
    # own origin.
    public_url = f"/tv/{display.public_token}"
    return TVDisplayOverviewResponse(
        display_id=display.id,
        title=display.title or "",
        subtitle=display.subtitle or "",
        orientation=display.orientation or "auto",
        theme=display.theme or "light",
        public_token=display.public_token,
        public_url=public_url,
        last_updated_at=_iso(display.last_updated_at),
        countries=country_rows,
        active_pairing=pairing_summary,
    )


@router.get(
    "/countries/{country_id}",
    response_model=TVDisplayCountryDetailResponse,
)
def country_detail_route(
    country_id: int,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> TVDisplayCountryDetailResponse:
    """Drill-down for one country: bank list with their filled-in
    rate cells. Cross-store country IDs return 404 (opaque tenancy)
    — the country must belong to the principal's TVDisplay row."""
    store = _require_tv_store(claims, db)
    display = _ensure_display(db, store)
    from app import TVDisplayCountry, TVDisplayPayoutBank, TVDisplayRate
    country = (
        db.query(TVDisplayCountry)
          .filter(
              TVDisplayCountry.id == country_id,
              TVDisplayCountry.display_id == display.id,
          )
          .one_or_none()
    )
    if country is None:
        raise HTTPException(status_code=404, detail="Country not found")
    banks = (
        db.query(TVDisplayPayoutBank)
          .filter(TVDisplayPayoutBank.country_id == country.id)
          .order_by(TVDisplayPayoutBank.sort_order, TVDisplayPayoutBank.id)
          .all()
    )
    rates = (
        db.query(TVDisplayRate)
          .join(
              TVDisplayPayoutBank,
              TVDisplayRate.bank_id == TVDisplayPayoutBank.id,
          )
          .filter(TVDisplayPayoutBank.country_id == country.id)
          .all()
    )
    rates_by_bank: dict[int, dict[str, float]] = {}
    for r in rates:
        rates_by_bank.setdefault(r.bank_id, {})[r.mt_company] = float(r.rate)
    bank_rows = [
        TVDisplayBankRow(
            id=b.id,
            bank_name=b.bank_name or "",
            sort_order=b.sort_order or 0,
            rates=rates_by_bank.get(b.id, {}),
        )
        for b in banks
    ]
    return TVDisplayCountryDetailResponse(
        id=country.id,
        country_code=country.country_code or "",
        country_name=country.country_name or "",
        sort_order=country.sort_order or 0,
        mt_companies=_csv_split(country.mt_companies),
        banks=bank_rows,
    )
