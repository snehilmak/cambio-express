"""Tests for the shared Pagination helpers.

Covers PaginationParams + paginate() + paginate_list() — the three
primitives that replace ~75 lines of per-endpoint pagination
boilerplate.
"""
from api.Core.Pagination import (
    DEFAULT_PER_PAGE, MAX_PER_PAGE, PaginationParams,
    paginate, paginate_list,
)


def test_pagination_params_defaults():
    p = PaginationParams()
    assert p.page == 1
    assert p.per_page == DEFAULT_PER_PAGE
    assert p.offset == 0
    assert p.limit == DEFAULT_PER_PAGE


def test_pagination_params_computes_offset():
    p = PaginationParams(page=3, per_page=20)
    assert p.offset == 40
    assert p.limit == 20


def test_pagination_params_first_page_offset_zero():
    p = PaginationParams(page=1, per_page=50)
    assert p.offset == 0


def test_paginate_list_first_page():
    items = list(range(100))
    p = PaginationParams(page=1, per_page=10)
    result = paginate_list(items, p)
    assert result["rows"] == list(range(10))
    assert result["total"] == 100
    assert result["page"] == 1
    assert result["total_pages"] == 10


def test_paginate_list_middle_page():
    items = list(range(100))
    p = PaginationParams(page=3, per_page=10)
    result = paginate_list(items, p)
    assert result["rows"] == list(range(20, 30))
    assert result["page"] == 3


def test_paginate_list_last_partial_page():
    items = list(range(25))
    p = PaginationParams(page=3, per_page=10)
    result = paginate_list(items, p)
    assert result["rows"] == [20, 21, 22, 23, 24]
    assert result["total_pages"] == 3


def test_paginate_list_empty():
    p = PaginationParams(page=1, per_page=10)
    result = paginate_list([], p)
    assert result["rows"] == []
    assert result["total"] == 0
    assert result["total_pages"] == 1


def test_paginate_list_page_beyond_returns_empty():
    p = PaginationParams(page=99, per_page=10)
    result = paginate_list([1, 2, 3], p)
    assert result["rows"] == []
    assert result["total"] == 3
    assert result["total_pages"] == 1


def test_paginate_list_with_extras():
    p = PaginationParams(page=1, per_page=10)
    result = paginate_list(
        [1, 2, 3], p, extras={"page_total": 6.0},
    )
    assert result["page_total"] == 6.0
    assert result["rows"] == [1, 2, 3]


def test_paginate_with_sqlalchemy_query(client, test_store_id):
    """Integration test using a real DB query through paginate()."""
    from tests._app import db, db_session
    from api.Modules.Tenancy.Models import Store

    with db_session():
        q = db.session.query(Store).order_by(Store.id)
        p = PaginationParams(page=1, per_page=10)
        result = paginate(q, p)
        assert result["total"] >= 1
        assert result["page"] == 1
        assert isinstance(result["rows"], list)


def test_paginate_with_adapter(client, test_store_id):
    """paginate() should call the adapter once per row."""
    from tests._app import db, db_session
    from api.Modules.Tenancy.Models import Store

    with db_session():
        q = db.session.query(Store).order_by(Store.id)
        p = PaginationParams(page=1, per_page=10)
        result = paginate(q, p, adapter=lambda s: {"id": s.id, "name": s.name})
        assert all("id" in row and "name" in row for row in result["rows"])


def test_max_per_page_constant_matches_pagination_params():
    """The constant should match the Query() le= limit."""
    assert MAX_PER_PAGE == 200
