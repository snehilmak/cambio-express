"""BankSync module — Controllers (FastAPI router).

Mounts at `/api/v2/bank/*`. Read-side endpoints:

  GET /bank/transactions → paginated list of BankTransaction rows
  GET /bank/rules        → operator-managed BankRule list
  GET /bank/accounts     → connected Stripe FC accounts

All three derive `store_id` from the JWT principal — pre-JWT
versions accepted an explicit `store_ids` query param, but with
auth in place we trust claims.store_id as the single source of
truth. Owner-umbrella support (multi-store query) lives on the
roadmap but ships with the owner portal migration, not here.

Write-side endpoints (rule CRUD, manual categorization, daily-
book post) come in subsequent PRs.
"""
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from api.Core.Database import get_db
from api.Modules.Auth.Controllers import get_principal
from api.Modules.BankSync.Models import (
    BankRule, BankTransaction, StripeBankAccount,
)
from api.Modules.BankSync.Repositories import (
    BankTransactionFilters,
    list_accounts,
    list_rules,
)
from api.Modules.BankSync.Requests import (
    BankAccountListResponse,
    BankAccountRow,
    BankRuleListResponse,
    BankRuleResponse,
    BankRuleRow,
    BankRuleToggleRequest,
    BankRuleWriteRequest,
    BankTransactionListResponse,
    BankTransactionRow,
    CategorizeRequest,
    CategorizeResponse,
)
from api.Modules.BankSync.Services import (
    categorize_transaction,
    list_transactions_page,
    uncategorize_transaction,
)


router = APIRouter()


def _require_store_scope(claims: dict) -> int:
    sid = claims.get("store_id")
    if sid is None:
        raise HTTPException(
            status_code=403,
            detail="JWT does not carry a store scope.",
        )
    return int(sid)


def _account_labels(db: Session, ids: list[int]) -> dict[int, str]:
    """Bulk-fetch the StripeBankAccount.label for every account_id in
    `ids`. Centralised so the row adapter doesn't N+1."""
    if not ids:
        return {}
    rows = (
        db.query(StripeBankAccount)
          .filter(StripeBankAccount.id.in_(set(ids)))
          .all()
    )
    return {a.id: a.label for a in rows}


@router.get("/transactions", response_model=BankTransactionListResponse)
def list_transactions_route(
    posted_from: str = Query(""),
    posted_to: str = Query(""),
    account_id: str = Query(""),
    category_slug: str = Query(""),
    sign: str = Query("", pattern="^(|credit|debit)$"),
    q: str = Query(""),
    uncategorized_only: bool = Query(False),
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> BankTransactionListResponse:
    sid = _require_store_scope(claims)
    filters = BankTransactionFilters.from_query({
        "posted_from": posted_from, "posted_to": posted_to,
        "account_id": account_id, "category_slug": category_slug,
        "sign": sign, "q": q,
        "uncategorized_only": "1" if uncategorized_only else "",
    })
    page_obj = list_transactions_page(
        db, [sid], filters, page=page, per_page=per_page,
    )
    labels = _account_labels(
        db, [r.stripe_bank_account_id for r in page_obj.rows],
    )
    rows = [
        BankTransactionRow(
            id=r.id,
            posted_at=r.posted_at.isoformat() if r.posted_at else "",
            description=r.description or "",
            amount_cents=r.amount_cents,
            amount=r.amount,
            currency=r.currency or "usd",
            status=r.status or "posted",
            category_slug=r.category_slug or "",
            account_id=r.stripe_bank_account_id,
            account_label=labels.get(r.stripe_bank_account_id, ""),
        )
        for r in page_obj.rows
    ]
    return BankTransactionListResponse(
        rows=rows,
        total=page_obj.total,
        page=page_obj.page,
        per_page=page_obj.per_page,
        total_pages=page_obj.total_pages,
        page_total_cents=page_obj.page_total_cents,
        uncategorized_count=page_obj.uncategorized_count,
    )


@router.get("/rules", response_model=BankRuleListResponse)
def list_rules_route(
    enabled_only: bool = Query(False),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> BankRuleListResponse:
    """Operator-managed BankRule list. Order matches the auto-
    categorize sync's evaluation order (priority asc, id tie-break)
    so the rules-manager UI shows what would actually fire first."""
    sid = _require_store_scope(claims)
    rules = list_rules(db, [sid], enabled_only=enabled_only)
    account_filter_ids = [
        r.account_filter_id for r in rules if r.account_filter_id is not None
    ]
    labels = _account_labels(db, account_filter_ids)
    rows = [
        BankRuleRow(
            id=r.id,
            enabled=bool(r.enabled),
            priority=r.priority,
            desc_match_type=r.desc_match_type or "",
            desc_match_value=r.desc_match_value or "",
            sign_filter=r.sign_filter or "",
            amount_min_cents=r.amount_min_cents,
            amount_max_cents=r.amount_max_cents,
            account_filter_id=r.account_filter_id,
            account_filter_label=(
                labels.get(r.account_filter_id, "")
                if r.account_filter_id is not None else ""
            ),
            target_kind=r.target_kind,
            auto_post=bool(r.auto_post),
            description=r.description or "",
            match_count=r.match_count or 0,
            last_matched_at=(
                r.last_matched_at.isoformat() if r.last_matched_at else ""
            ),
        )
        for r in rules
    ]
    return BankRuleListResponse(rows=rows, total=len(rows))


@router.get("/accounts", response_model=BankAccountListResponse)
def list_accounts_route(
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> BankAccountListResponse:
    """All connected Stripe Financial Connections accounts for the
    principal's store. Includes both enabled + disconnected accounts
    so the UI can show "previously connected" history; clients filter
    on `enabled` if they only want active ones."""
    sid = _require_store_scope(claims)
    accounts = list_accounts(db, [sid])
    rows = [
        BankAccountRow(
            id=a.id,
            institution_name=a.institution_name or "",
            display_name=a.display_name or "",
            nickname=a.nickname or "",
            last4=a.last4 or "",
            label=a.label,
            category=a.category or "",
            subcategory=a.subcategory or "",
            currency=a.currency or "usd",
            last_balance_cents=a.last_balance_cents or 0,
            last_balance=a.last_balance,
            last_balance_as_of=(
                a.last_balance_as_of.isoformat()
                if a.last_balance_as_of else ""
            ),
            enabled=bool(a.enabled),
            connected_at=(
                a.connected_at.isoformat() if a.connected_at else ""
            ),
            disconnected_at=(
                a.disconnected_at.isoformat()
                if a.disconnected_at else ""
            ),
        )
        for a in accounts
    ]
    return BankAccountListResponse(rows=rows, total=len(rows))


def _adapt_txn(db: Session, txn: BankTransaction) -> BankTransactionRow:
    """Build the response row for a single BankTransaction. Re-uses
    `_account_labels` for the per-account nickname lookup."""
    labels = _account_labels(db, [txn.stripe_bank_account_id])
    return BankTransactionRow(
        id=txn.id,
        posted_at=txn.posted_at.isoformat() if txn.posted_at else "",
        description=txn.description or "",
        amount_cents=txn.amount_cents,
        amount=txn.amount,
        currency=txn.currency or "usd",
        status=txn.status or "posted",
        category_slug=txn.category_slug or "",
        account_id=txn.stripe_bank_account_id,
        account_label=labels.get(txn.stripe_bank_account_id, ""),
    )


def _find_owned_txn(db: Session, store_id: int, txn_id: int) -> BankTransaction:
    txn = (
        db.query(BankTransaction)
          .filter(
              BankTransaction.id == txn_id,
              BankTransaction.store_id == store_id,
          )
          .one_or_none()
    )
    if txn is None:
        raise HTTPException(
            status_code=404, detail="Bank transaction not found",
        )
    return txn


@router.post(
    "/transactions/{txn_id}/categorize",
    response_model=CategorizeResponse,
)
def categorize_route(
    body: CategorizeRequest,
    txn_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> CategorizeResponse:
    """Tag a transaction with a category and (when the kind is a
    daily-book line item) auto-create the matching DailyLineItem.

    Idempotent: re-categorizing replaces any prior auto-created
    DailyLineItem before adding the new one. `post_to_daily=False`
    keeps the metadata-only path for operators who want a P&L tag
    without a daily-book mirror.
    """
    sid = _require_store_scope(claims)
    txn = _find_owned_txn(db, sid, txn_id)
    from api.Modules.BankSync.Services import is_daily_book_kind
    categorize_transaction(
        db, txn, body.target_kind,
        post_to_daily=body.post_to_daily,
        is_daily_book_kind=is_daily_book_kind,
    )
    db.commit()
    db.refresh(txn)
    return CategorizeResponse(transaction=_adapt_txn(db, txn))


@router.post(
    "/transactions/{txn_id}/uncategorize",
    response_model=CategorizeResponse,
)
def uncategorize_route(
    txn_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> CategorizeResponse:
    """Clear a transaction's category and remove any auto-created
    DailyLineItem. The row stays in the table — it just goes back
    to "uncategorized" so it can be re-tagged."""
    sid = _require_store_scope(claims)
    txn = _find_owned_txn(db, sid, txn_id)
    uncategorize_transaction(db, txn)
    db.commit()
    db.refresh(txn)
    return CategorizeResponse(transaction=_adapt_txn(db, txn))


# ── Rule CRUD ────────────────────────────────────────────────


def _adapt_rule(db: Session, r: BankRule) -> BankRuleRow:
    label = ""
    if r.account_filter_id is not None:
        labels = _account_labels(db, [r.account_filter_id])
        label = labels.get(r.account_filter_id, "")
    return BankRuleRow(
        id=r.id,
        enabled=bool(r.enabled),
        priority=r.priority,
        desc_match_type=r.desc_match_type or "",
        desc_match_value=r.desc_match_value or "",
        sign_filter=r.sign_filter or "",
        amount_min_cents=r.amount_min_cents,
        amount_max_cents=r.amount_max_cents,
        account_filter_id=r.account_filter_id,
        account_filter_label=label,
        target_kind=r.target_kind,
        auto_post=bool(r.auto_post),
        description=r.description or "",
        match_count=r.match_count or 0,
        last_matched_at=r.last_matched_at.isoformat() if r.last_matched_at else "",
    )


def _validate_rule_body(body: BankRuleWriteRequest) -> None:
    """Cross-field invariants that Pydantic Field() can't express
    on its own. Raises 422 with a `field` hint so the SPA can
    highlight the offending input."""
    # If desc_match_type is set, desc_match_value must be non-empty.
    if body.desc_match_type and not body.desc_match_value.strip():
        raise HTTPException(
            status_code=422,
            detail={
                "field": "desc_match_value",
                "message": "Description match value is required when "
                           "match type is set.",
            },
        )
    # amount_min must be ≤ amount_max if both set.
    if (
        body.amount_min_cents is not None
        and body.amount_max_cents is not None
        and body.amount_min_cents > body.amount_max_cents
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "field": "amount_max_cents",
                "message": "Max amount must be ≥ min amount.",
            },
        )


def _find_owned_rule(db: Session, store_id: int, rule_id: int) -> BankRule:
    r = (
        db.query(BankRule)
          .filter(BankRule.id == rule_id, BankRule.store_id == store_id)
          .one_or_none()
    )
    if r is None:
        raise HTTPException(status_code=404, detail="Bank rule not found")
    return r


def _validate_account_owned(db: Session, store_id: int, account_id: int | None):
    """Cross-tenant safety: refuse to attach a rule to an account
    that belongs to a different store. Returns silently if the FK
    is None (rule applies to all accounts)."""
    if account_id is None:
        return
    a = (
        db.query(StripeBankAccount)
          .filter(
              StripeBankAccount.id == account_id,
              StripeBankAccount.store_id == store_id,
          )
          .one_or_none()
    )
    if a is None:
        raise HTTPException(
            status_code=422,
            detail={
                "field": "account_filter_id",
                "message": "Account does not belong to this store.",
            },
        )


@router.post("/rules", response_model=BankRuleResponse, status_code=201)
def create_rule_route(
    body: BankRuleWriteRequest,
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> BankRuleResponse:
    sid = _require_store_scope(claims)
    _validate_rule_body(body)
    _validate_account_owned(db, sid, body.account_filter_id)
    r = BankRule(
        store_id=sid,
        enabled=body.enabled,
        priority=body.priority,
        desc_match_type=body.desc_match_type,
        desc_match_value=body.desc_match_value.strip(),
        sign_filter=body.sign_filter,
        amount_min_cents=body.amount_min_cents,
        amount_max_cents=body.amount_max_cents,
        account_filter_id=body.account_filter_id,
        target_kind=body.target_kind,
        auto_post=body.auto_post,
        description=body.description.strip(),
    )
    db.add(r); db.flush()
    db.commit()
    return BankRuleResponse(rule=_adapt_rule(db, r))


@router.put("/rules/{rule_id}", response_model=BankRuleResponse)
def update_rule_route(
    body: BankRuleWriteRequest,
    rule_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> BankRuleResponse:
    sid = _require_store_scope(claims)
    _validate_rule_body(body)
    _validate_account_owned(db, sid, body.account_filter_id)
    r = _find_owned_rule(db, sid, rule_id)
    r.enabled = body.enabled
    r.priority = body.priority
    r.desc_match_type = body.desc_match_type
    r.desc_match_value = body.desc_match_value.strip()
    r.sign_filter = body.sign_filter
    r.amount_min_cents = body.amount_min_cents
    r.amount_max_cents = body.amount_max_cents
    r.account_filter_id = body.account_filter_id
    r.target_kind = body.target_kind
    r.auto_post = body.auto_post
    r.description = body.description.strip()
    db.commit()
    return BankRuleResponse(rule=_adapt_rule(db, r))


@router.post("/rules/{rule_id}/toggle", response_model=BankRuleResponse)
def toggle_rule_route(
    body: BankRuleToggleRequest,
    rule_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> BankRuleResponse:
    sid = _require_store_scope(claims)
    r = _find_owned_rule(db, sid, rule_id)
    r.enabled = body.enabled
    db.commit()
    return BankRuleResponse(rule=_adapt_rule(db, r))


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule_route(
    rule_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    claims: dict = Depends(get_principal),
) -> None:
    sid = _require_store_scope(claims)
    r = _find_owned_rule(db, sid, rule_id)
    db.delete(r)
    db.commit()
    return None

