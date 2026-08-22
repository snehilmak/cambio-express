"""Lottery module — Controllers (FastAPI router).

Mounts at `/api/v2/lottery/*`:

  GET  /games                    list games (?include_inactive=1)
  POST /games                    create game
  PUT  /games/{id}               update game / deactivate
  GET  /packs                    list packs (?status=)
  POST /packs                    receive a pack
  POST /packs/{id}/activate      received → active (bin + opening #)
  POST /packs/{id}/settle        active → settled
  POST /packs/{id}/return        received|active → returned
  GET  /day/{date}               day-close summary (sold + value
                                 per pack; flags uncounted packs)
  POST /day/{date}/counts        upsert one pack's day-close count

Cashiers (employees) hold lottery.create/read so they can enter
day-close counts; game/pack lifecycle needs admin update rights.
Every mutation records an operator-audit row (invariant #7).
"""
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Core.Money import to_dollars
from api.Modules.Auth.Controllers import get_principal
from api.Modules.Auth.Services.principal import (
    require_permission,
    resolve_store_scope,
)
from api.Modules.Lottery.Models import LotteryPack, PACK_STATUSES
from api.Modules.Lottery.Requests import (
    DayCountRow,
    DayCountWriteRequest,
    DaySummaryResponse,
    GameListResponse,
    GameResponse,
    GameRow,
    GameUpdateRequest,
    GameWriteRequest,
    PackActivateRequest,
    PackDateRequest,
    PackListResponse,
    PackReceiveRequest,
    PackResponse,
    PackRow,
)
from api.Modules.Lottery.Services import (
    LotteryNotFoundError,
    LotteryStateError,
    activate_pack,
    create_game,
    day_summary,
    list_games,
    list_packs,
    previous_reference,
    receive_pack,
    record_day_count,
    return_pack,
    settle_pack,
    update_game,
)

router = APIRouter(prefix="/lottery", tags=["lottery"])


def _audit(
    db: Session, *, claims: dict[str, Any], action: str,
    target_type: str, target_id: str, summary: str,
) -> None:
    """Operator-audit emitter — CLAUDE.md invariant #7."""
    from api.Modules.Audit.Services import record_operator_action
    record_operator_action(
        db,
        store_id=int(claims["store_id"]),
        user_id=int(claims["sub"]),
        user_name=claims.get("name") or claims.get("username") or "",
        user_role=claims.get("role") or "",
        target_type=target_type,
        action=action,
        target_id=target_id,
        summary=summary[:255],
    )


def _parse_date(raw: str, field: str) -> date:
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail={"field": field, "message": "Use YYYY-MM-DD."},
        )


def _game_row(g) -> GameRow:
    return GameRow(
        id=g.id, game_number=g.game_number or "", name=g.name or "",
        ticket_price=g.ticket_price,
        tickets_per_pack=int(g.tickets_per_pack or 0),
        is_active=bool(g.is_active),
    )


def _pack_row(p: LotteryPack) -> PackRow:
    return PackRow(
        id=p.id, game_id=p.game_id,
        game_number=p.game.game_number or "",
        game_name=p.game.name or "",
        ticket_price=p.game.ticket_price,
        tickets_per_pack=int(p.game.tickets_per_pack or 0),
        pack_number=p.pack_number or "",
        status=p.status or "",
        bin_number=p.bin_number or "",
        received_on=p.received_on.isoformat() if p.received_on else None,
        activated_on=p.activated_on.isoformat() if p.activated_on else None,
        settled_on=p.settled_on.isoformat() if p.settled_on else None,
        opening_ticket=int(p.opening_ticket or 0),
    )


# ── Games ──────────────────────────────────────────────────


@router.get("/games", response_model=GameListResponse)
def list_games_route(
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> GameListResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "lottery", "read")
    return GameListResponse(
        games=[_game_row(g) for g in list_games(
            db, sid, include_inactive=include_inactive,
        )],
    )


@router.post("/games", response_model=GameResponse, status_code=201)
def create_game_route(
    body: GameWriteRequest,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> GameResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "lottery", "update")
    try:
        game = create_game(
            db, sid, game_number=body.game_number.strip(),
            name=body.name.strip(), ticket_price=body.ticket_price,
            tickets_per_pack=body.tickets_per_pack,
        )
    except LotteryStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    _audit(
        db, claims=claims, action="create_lottery_game",
        target_type="lottery_game", target_id=str(game.id),
        summary=f"game #{game.game_number} {game.name} "
                f"${game.ticket_price:,.2f} x{game.tickets_per_pack}",
    )
    db.commit()
    return GameResponse(game=_game_row(game))


@router.put("/games/{game_id}", response_model=GameResponse)
def update_game_route(
    game_id: int = Path(..., ge=1),
    body: GameUpdateRequest = ...,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> GameResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "lottery", "update")
    try:
        game = update_game(
            db, sid, game_id,
            name=body.name.strip() if body.name is not None else None,
            ticket_price=body.ticket_price,
            tickets_per_pack=body.tickets_per_pack,
            is_active=body.is_active,
        )
    except LotteryNotFoundError:
        raise HTTPException(status_code=404, detail="Game not found")
    _audit(
        db, claims=claims, action="update_lottery_game",
        target_type="lottery_game", target_id=str(game.id),
        summary=f"game #{game.game_number} updated",
    )
    db.commit()
    return GameResponse(game=_game_row(game))


# ── Packs ──────────────────────────────────────────────────


@router.get("/packs", response_model=PackListResponse)
def list_packs_route(
    status: str | None = Query(None),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> PackListResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "lottery", "read")
    if status is not None and status not in PACK_STATUSES:
        raise HTTPException(status_code=422, detail="Unknown pack status")
    return PackListResponse(
        packs=[_pack_row(p) for p in list_packs(db, sid, status=status)],
    )


@router.post("/packs", response_model=PackResponse, status_code=201)
def receive_pack_route(
    body: PackReceiveRequest,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> PackResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "lottery", "update")
    try:
        pack = receive_pack(
            db, sid, game_id=body.game_id,
            pack_number=body.pack_number.strip(),
            received_on=_parse_date(body.received_on, "received_on"),
            created_by=int(claims["sub"]),
        )
    except LotteryNotFoundError:
        raise HTTPException(status_code=404, detail="Game not found")
    except LotteryStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    _audit(
        db, claims=claims, action="receive_lottery_pack",
        target_type="lottery_pack", target_id=str(pack.id),
        summary=f"pack {pack.pack_number} game #{pack.game.game_number}",
    )
    db.commit()
    return PackResponse(pack=_pack_row(pack))


def _pack_transition(
    db: Session, claims: dict[str, Any], pack_id: int, *,
    fn, action: str, **kwargs,
) -> PackResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "lottery", "update")
    try:
        pack = fn(db, sid, pack_id, **kwargs)
    except LotteryNotFoundError:
        raise HTTPException(status_code=404, detail="Pack not found")
    except LotteryStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    _audit(
        db, claims=claims, action=action,
        target_type="lottery_pack", target_id=str(pack.id),
        summary=f"pack {pack.pack_number} game #{pack.game.game_number} "
                f"→ {pack.status}",
    )
    db.commit()
    return PackResponse(pack=_pack_row(pack))


@router.post("/packs/{pack_id}/activate", response_model=PackResponse)
def activate_pack_route(
    pack_id: int = Path(..., ge=1),
    body: PackActivateRequest = ...,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> PackResponse:
    return _pack_transition(
        db, claims, pack_id, fn=activate_pack,
        action="activate_lottery_pack",
        activated_on=_parse_date(body.activated_on, "activated_on"),
        opening_ticket=body.opening_ticket,
        bin_number=body.bin_number.strip(),
    )


@router.post("/packs/{pack_id}/settle", response_model=PackResponse)
def settle_pack_route(
    pack_id: int = Path(..., ge=1),
    body: PackDateRequest = ...,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> PackResponse:
    return _pack_transition(
        db, claims, pack_id, fn=settle_pack,
        action="settle_lottery_pack",
        settled_on=_parse_date(body.on, "on"),
    )


@router.post("/packs/{pack_id}/return", response_model=PackResponse)
def return_pack_route(
    pack_id: int = Path(..., ge=1),
    body: PackDateRequest = ...,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> PackResponse:
    return _pack_transition(
        db, claims, pack_id, fn=return_pack,
        action="return_lottery_pack",
        returned_on=_parse_date(body.on, "on"),
    )


# ── Day close ──────────────────────────────────────────────


def _summary_response(
    db: Session, sid: int, day: date,
) -> DaySummaryResponse:
    summary = day_summary(db, sid, day)
    rows = []
    for r in summary.rows:
        rows.append(DayCountRow(
            pack_id=r.pack.id,
            pack_number=r.pack.pack_number or "",
            bin_number=r.pack.bin_number or "",
            game_number=r.pack.game.game_number or "",
            game_name=r.pack.game.name or "",
            ticket_price=r.pack.game.ticket_price,
            counted=r.counted,
            closing_ticket=r.closing_ticket,
            previous_reference=previous_reference(db, r.pack, day),
            sold=r.sold,
            value=to_dollars(r.value_cents),
        ))
    return DaySummaryResponse(
        date=day.isoformat(),
        rows=rows,
        total_sold=summary.total_sold,
        total_value=to_dollars(summary.total_value_cents),
        uncounted_active_packs=summary.uncounted_active_packs,
    )


@router.get("/day/{day}", response_model=DaySummaryResponse)
def day_summary_route(
    day: str = Path(..., min_length=10, max_length=10),
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> DaySummaryResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "lottery", "read")
    return _summary_response(db, sid, _parse_date(day, "day"))


@router.post("/day/{day}/counts", response_model=DaySummaryResponse)
def record_count_route(
    day: str = Path(..., min_length=10, max_length=10),
    body: DayCountWriteRequest = ...,
    db: Session = Depends(get_db),
    claims: dict[str, Any] = Depends(get_principal),
) -> DaySummaryResponse:
    sid = resolve_store_scope(claims)
    require_permission(claims, "lottery", "create")
    d = _parse_date(day, "day")
    try:
        row = record_day_count(
            db, sid, pack_id=body.pack_id, day=d,
            closing_ticket=body.closing_ticket,
            created_by=int(claims["sub"]),
        )
    except LotteryNotFoundError:
        raise HTTPException(status_code=404, detail="Pack not found")
    except LotteryStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    _audit(
        db, claims=claims, action="record_lottery_count",
        target_type="lottery_day_count", target_id=str(row.id),
        summary=f"pack_id={body.pack_id} {d.isoformat()} "
                f"closing={body.closing_ticket}",
    )
    db.commit()
    return _summary_response(db, sid, d)
