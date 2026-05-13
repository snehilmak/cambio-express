"""TV Display module — Controllers (FastAPI router).

Mounts at `/api/v2/tv-display/*`. Endpoints:

  Read:
    GET /tv-display/overview            → display config + countries
         with bank/rate counts + active Fire TV pairing summary.
    GET /tv-display/countries/{id}      → full drill-down for one
         country (banks with sparse rate matrix).

  Write (admin-landing actions):
    POST   /tv-display/settings                       → save title /
           subtitle / orientation / theme
    POST   /tv-display/regenerate-token               → rotate the
           per-store public_token (TV URL changes)
    POST   /tv-display/claim                          → claim a 6-char
           pair code shown on a Fire TV
    POST   /tv-display/pairings/{pairing_id}/revoke   → unpair a Fire TV
    POST   /tv-display/countries                      → add a new
           country section (header only; banks + rates land in the
           legacy editor for now)
    DELETE /tv-display/countries/{country_id}         → remove a country
           and cascade its banks + rates

Auth + gating: requires JWT principal scoped to a store; admin
or employee role; the store must have the `tv_display` add-on
active. Mirrors the legacy `_tv_required()` guard.

Country *editor* (bank+rate matrix POST at
/tv-display/countries/<id>) and the public kiosk view (/tv/<token>)
remain on legacy Flask until the next migration slice.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Auth.Controllers import get_principal
from api.Modules.TVDisplay.Requests import (
    TVDisplayBankRow,
    TVDisplayClaimRequest,
    TVDisplayCountryCreateRequest,
    TVDisplayCountryCreateResponse,
    TVDisplayCountryDetailResponse,
    TVDisplayCountryStat,
    TVDisplayOverviewResponse,
    TVDisplayRegenerateTokenResponse,
    TVDisplaySettingsUpdateRequest,
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
    from api.Modules.Billing.Services import store_has_addon
    from api.Modules.Tenancy.Models import Store
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
    from api.Modules.TVDisplay.Models import TVDisplay
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
    from api.Modules.TVDisplay.Models import TVDisplayCountry, TVDisplayPayoutBank, TVDisplayRate, TVPairing
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
    from api.Modules.TVDisplay.Models import TVDisplayCountry, TVDisplayPayoutBank, TVDisplayRate
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


# ── Write-side: admin-landing actions ──────────────────────────


_ALLOWED_ORIENTATIONS = {"auto", "landscape", "portrait"}
_ALLOWED_THEMES = {"light", "dark"}


@router.post("/settings", status_code=204)
def save_settings_route(
    payload: TVDisplaySettingsUpdateRequest,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> Response:
    """Update title/subtitle/orientation/theme. Mirrors the legacy
    /tv-display/settings POST: invalid orientation/theme falls back
    to `auto`/`light` rather than 4xx, matching the legacy form's
    forgiving behaviour. Stamps `last_updated_at` so the public
    board can decide when to refresh."""
    store = _require_tv_store(claims, db)
    display = _ensure_display(db, store)
    display.title = (payload.title or "").strip()[:120] or "Cheapest Money Transfer"
    display.subtitle = (payload.subtitle or "").strip()[:120]
    orient = (payload.orientation or "auto").strip()
    if orient not in _ALLOWED_ORIENTATIONS:
        orient = "auto"
    display.orientation = orient
    theme = (payload.theme or "light").strip()
    if theme not in _ALLOWED_THEMES:
        theme = "light"
    display.theme = theme
    display.last_updated_at = datetime.utcnow()
    db.commit()
    return Response(status_code=204)


@router.post(
    "/regenerate-token", response_model=TVDisplayRegenerateTokenResponse,
)
def regenerate_token_route(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> TVDisplayRegenerateTokenResponse:
    """Rotate the public_token. Anyone holding the old URL stops
    seeing the board on the next page load — operators rotate after
    a leak / lost device. Returns the new token + URL so the SPA can
    update its copy-to-clipboard target without a full refetch."""
    import secrets
    store = _require_tv_store(claims, db)
    display = _ensure_display(db, store)
    display.public_token = secrets.token_urlsafe(24)
    db.commit()
    return TVDisplayRegenerateTokenResponse(
        public_token=display.public_token,
        public_url=f"/tv/{display.public_token}",
    )


@router.post("/claim", status_code=204)
def claim_pair_code_route(
    payload: TVDisplayClaimRequest,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> Response:
    """Bind a Fire TV's 6-char code to this store's TVDisplay.
    Mirrors the legacy /tv-display/claim POST: revokes any prior
    active TVPairing on the display, then creates a new one reusing
    the device_token from the pending row.

    All failure modes return the same opaque 400 message so a
    fishing attack can't enumerate live codes:
      - missing/malformed code (not 6 chars in alphabet)
      - unknown code
      - expired code
      - already-claimed code
    """
    store = _require_tv_store(claims, db)
    display = _ensure_display(db, store)
    # Reuse the legacy code alphabet + lifetime — these are owned by
    # the Flask /api/tv-pair/init endpoint that mints the pending row,
    # so the validator must agree on what's a valid char.
    from api.Modules.TVDisplay.Models import TVPairing, TVPendingPair
    from app import _PAIR_CODE_ALPHABET

    raw = (payload.code or "").strip().upper()
    code = "".join(c for c in raw if c in _PAIR_CODE_ALPHABET)
    if len(code) != 6:
        raise HTTPException(
            status_code=400,
            detail="Code not found or expired.",
        )

    pending = (
        db.query(TVPendingPair)
          .filter(TVPendingPair.code == code)
          .one_or_none()
    )
    now = datetime.utcnow()
    if (pending is None
            or pending.claimed_at is not None
            or pending.expires_at < now):
        raise HTTPException(
            status_code=400,
            detail="Code not found or expired.",
        )

    # One Fire TV at a time per subscription — revoke any prior active
    # pairing on this display before claiming the new one.
    (db.query(TVPairing)
       .filter(TVPairing.display_id == display.id,
               TVPairing.revoked_at.is_(None))
       .update({"revoked_at": now}, synchronize_session=False))

    pairing = TVPairing(
        display_id=display.id,
        device_token=pending.device_token,
        device_label=pending.device_label,
        paired_at=now,
        last_seen_at=now,
    )
    db.add(pairing)
    db.flush()

    pending.claimed_at = now
    pending.claimed_pairing_id = pairing.id
    display.last_updated_at = now
    db.commit()
    return Response(status_code=204)


@router.post("/pairings/{pairing_id}/revoke", status_code=204)
def revoke_pairing_route(
    pairing_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> Response:
    """Manually unpair a Fire TV. Sets revoked_at = now; the device's
    URL 404s on its next 30-second refresh and routes back to the
    pairing screen. Tenant-scoped — pairings on other stores' displays
    return 404 (opaque)."""
    store = _require_tv_store(claims, db)
    display = _ensure_display(db, store)
    from api.Modules.TVDisplay.Models import TVPairing
    pairing = (
        db.query(TVPairing)
          .filter(TVPairing.id == pairing_id,
                  TVPairing.display_id == display.id)
          .one_or_none()
    )
    if pairing is None:
        raise HTTPException(status_code=404, detail="Pairing not found")
    if pairing.revoked_at is None:
        pairing.revoked_at = datetime.utcnow()
        db.commit()
    return Response(status_code=204)


@router.post(
    "/countries", response_model=TVDisplayCountryCreateResponse,
    status_code=201,
)
def create_country_route(
    payload: TVDisplayCountryCreateRequest,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> TVDisplayCountryCreateResponse:
    """Add a new country section. Mirrors the legacy
    /tv-display/countries/new POST: country_code is uppercased + cap
    4 chars; sort_order defaults to (max + 10) so manual reordering
    has room. Banks + rates aren't created here — the operator goes
    to the country editor next to fill those in."""
    store = _require_tv_store(claims, db)
    display = _ensure_display(db, store)
    from api.Modules.TVDisplay.Models import TVDisplayCountry

    name = (payload.country_name or "").strip()[:80]
    if not name:
        raise HTTPException(
            status_code=422, detail="Country name is required.",
        )
    code = (payload.country_code or "").strip().upper()[:4]
    last = (
        db.query(func.max(TVDisplayCountry.sort_order))
          .filter(TVDisplayCountry.display_id == display.id)
          .scalar()
        or 0
    )
    country = TVDisplayCountry(
        display_id=display.id,
        country_code=code,
        country_name=name,
        sort_order=last + 10,
        mt_companies=(payload.mt_companies or "").strip()[:500],
    )
    db.add(country)
    display.last_updated_at = datetime.utcnow()
    db.commit()
    db.refresh(country)
    return TVDisplayCountryCreateResponse(
        id=country.id,
        country_name=country.country_name,
        country_code=country.country_code or "",
    )


@router.delete("/countries/{country_id}", status_code=204)
def delete_country_route(
    country_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> Response:
    """Remove a country section. Manual cascade across banks → rates
    (mirrors the retention purge pattern). Tenant-scoped — countries
    on other stores' displays return 404."""
    store = _require_tv_store(claims, db)
    display = _ensure_display(db, store)
    from api.Modules.TVDisplay.Models import TVDisplayCountry, TVDisplayPayoutBank, TVDisplayRate
    country = (
        db.query(TVDisplayCountry)
          .filter(TVDisplayCountry.id == country_id,
                  TVDisplayCountry.display_id == display.id)
          .one_or_none()
    )
    if country is None:
        raise HTTPException(status_code=404, detail="Country not found")
    bank_ids = [
        b.id for b in
        db.query(TVDisplayPayoutBank)
          .filter(TVDisplayPayoutBank.country_id == country.id)
          .all()
    ]
    if bank_ids:
        (db.query(TVDisplayRate)
           .filter(TVDisplayRate.bank_id.in_(bank_ids))
           .delete(synchronize_session=False))
    (db.query(TVDisplayPayoutBank)
       .filter(TVDisplayPayoutBank.country_id == country.id)
       .delete(synchronize_session=False))
    db.delete(country)
    display.last_updated_at = datetime.utcnow()
    db.commit()
    return Response(status_code=204)
