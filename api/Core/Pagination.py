"""Reusable pagination helpers for FastAPI list endpoints.

Standardises the boilerplate that previously lived in every list
endpoint:

  page: int = Query(1, ge=1)
  per_page: int = Query(50, ge=1, le=200)
  ...
  total = query.count()
  total_pages = max(1, -(-total // per_page))
  rows = query.offset((page - 1) * per_page).limit(per_page).all()
  return {"rows": rows, "total": total, "page": page, "total_pages": total_pages}

After this module:

  from api.Core.Pagination import PaginationParams, paginate

  @router.get("/things")
  def list_things(
      pagination: PaginationParams = Depends(),
      db: Session = Depends(get_db),
  ) -> dict:
      query = db.query(Thing).order_by(Thing.created_at.desc())
      return paginate(query, pagination)

The returned dict matches the existing ``{rows, total, page,
total_pages}`` shape so the SPA query hooks need no changes.

For typed responses, callers can wrap the result in their own
Pydantic model — ``paginate()`` returns a plain dict to keep it
generic across modules.
"""
from __future__ import annotations

from math import ceil
from typing import Any, Callable, TypeVar

from fastapi import Query
from sqlalchemy.orm import Query as SAQuery

T = TypeVar("T")

DEFAULT_PER_PAGE = 50
MAX_PER_PAGE = 200


class PaginationParams:
    """FastAPI dependency that pulls ``page`` + ``per_page`` from
    the query string. Use as ``pagination: PaginationParams = Depends()``.

    Sensible defaults match the legacy hand-written endpoints:
    page=1, per_page=50, max per_page=200.

    Also constructible directly (``PaginationParams(page=2, per_page=10)``)
    for use in unit tests or in-memory pagination outside FastAPI."""

    def __init__(
        self,
        page: int = 1,
        per_page: int = DEFAULT_PER_PAGE,
    ) -> None:
        self.page = page
        self.per_page = per_page

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page

    @property
    def limit(self) -> int:
        return self.per_page


def pagination_dep(
    page: int = Query(1, ge=1, description="1-based page number"),
    per_page: int = Query(
        DEFAULT_PER_PAGE, ge=1, le=MAX_PER_PAGE,
        description="Rows per page (1 to 200)",
    ),
) -> PaginationParams:
    """FastAPI dependency factory. Use as
    ``pagination: PaginationParams = Depends(pagination_dep)``."""
    return PaginationParams(page=page, per_page=per_page)


def paginate(
    query: SAQuery,
    pagination: PaginationParams,
    *,
    adapter: Callable[[Any], Any] | None = None,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run ``query`` with offset/limit and wrap the result in the
    canonical ``{rows, total, page, total_pages}`` shape.

    ``adapter`` is called once per row when you need to transform
    ORM rows into a serialisable dict (e.g., joining columns,
    formatting timestamps). Omit it to return raw ORM objects —
    fine when the response_model handles serialisation.

    ``extras`` lets you merge extra top-level fields into the
    response (e.g., ``{"page_amount": ..., "page_fees": ...}`` for
    the transfers list).
    """
    total = query.count()
    total_pages = max(1, ceil(total / pagination.per_page)) if total else 1
    rows_raw = (
        query.offset(pagination.offset)
             .limit(pagination.limit)
             .all()
    )
    rows = [adapter(r) for r in rows_raw] if adapter else rows_raw
    payload: dict[str, Any] = {
        "rows": rows,
        "total": total,
        "page": pagination.page,
        "total_pages": total_pages,
    }
    if extras:
        payload.update(extras)
    return payload


def paginate_list(
    items: list[T],
    pagination: PaginationParams,
    *,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Like ``paginate()`` but for in-memory lists (e.g., a merged
    union of two queries that can't be expressed as a single SQL
    ``Query``). Slices the list and returns the same envelope."""
    total = len(items)
    total_pages = max(1, ceil(total / pagination.per_page)) if total else 1
    start = pagination.offset
    end = start + pagination.limit
    payload: dict[str, Any] = {
        "rows": items[start:end],
        "total": total,
        "page": pagination.page,
        "total_pages": total_pages,
    }
    if extras:
        payload.update(extras)
    return payload
