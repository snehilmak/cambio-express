"""Tests for the Owners Repositories.

Pure SQL helpers — no permission checks, no audit, no commits.
These tests verify the query shape: correct filters, correct
ordering, correct empty-input handling.
"""
from datetime import datetime, timedelta

from tests._app import db, db_session


def _make_owner(username: str = "test-owner@x.com"):
    from api.Modules.Tenancy.Models import User
    with db_session():
        u = User(username=username, full_name="Test Owner", role="owner",
                 store_id=None, is_active=True)
        u.set_password("ownerpw1!")
        db.session.add(u)
        db.session.commit()
        return u.id


class TestConnectCodes:
    def test_list_codes_for_owner_empty(self):
        from api.Modules.Owners.Repositories import list_codes_for_owner
        with db_session():
            rows = list_codes_for_owner(db.session, owner_id=99999)
            assert rows == []

    def test_list_codes_for_owner_returns_newest_first(self):
        from api.Modules.Owners.Repositories import list_codes_for_owner
        from api.Modules.Tenancy.Models import OwnerConnectCode

        owner_id = _make_owner("newest-first@x.com")
        with db_session():
            older = OwnerConnectCode(
                owner_id=owner_id, code="OLD12345",
                created_at=datetime.utcnow() - timedelta(days=5),
                expires_at=datetime.utcnow() + timedelta(days=7),
            )
            newer = OwnerConnectCode(
                owner_id=owner_id, code="NEW12345",
                created_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=7),
            )
            db.session.add_all([older, newer])
            db.session.commit()

            rows = list_codes_for_owner(db.session, owner_id=owner_id)
            assert len(rows) == 2
            assert rows[0].code == "NEW12345"
            assert rows[1].code == "OLD12345"

    def test_find_owner_code_owner_isolation(self):
        """An owner cannot see another owner's code by id."""
        from api.Modules.Owners.Repositories import find_owner_code
        from api.Modules.Tenancy.Models import OwnerConnectCode

        owner_a = _make_owner("iso-a@x.com")
        owner_b = _make_owner("iso-b@x.com")
        with db_session():
            code = OwnerConnectCode(
                owner_id=owner_a, code="ISO12345",
                created_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=7),
            )
            db.session.add(code)
            db.session.commit()
            code_id = code.id

            assert find_owner_code(db.session, code_id, owner_a) is not None
            assert find_owner_code(db.session, code_id, owner_b) is None

    def test_find_owner_code_returns_none_for_missing(self):
        from api.Modules.Owners.Repositories import find_owner_code
        with db_session():
            assert find_owner_code(db.session, 999999, 1) is None


class TestStoreLinks:
    def test_find_link_missing(self):
        from api.Modules.Owners.Repositories import find_link
        with db_session():
            assert find_link(db.session, owner_id=99999, store_id=99999) is None

    def test_find_link_present(self, test_store_id):
        from api.Modules.Owners.Repositories import find_link
        from api.Modules.Tenancy.Models import StoreOwnerLink

        owner_id = _make_owner("link-test@x.com")
        with db_session():
            link = StoreOwnerLink(owner_id=owner_id, store_id=test_store_id)
            db.session.add(link)
            db.session.commit()

            found = find_link(db.session, owner_id, test_store_id)
            assert found is not None
            assert found.owner_id == owner_id
            assert found.store_id == test_store_id


class TestStores:
    def test_get_store_returns_row(self, test_store_id):
        from api.Modules.Owners.Repositories import get_store
        with db_session():
            store = get_store(db.session, test_store_id)
            assert store is not None
            assert store.id == test_store_id

    def test_get_store_returns_none_missing(self):
        from api.Modules.Owners.Repositories import get_store
        with db_session():
            assert get_store(db.session, 999999) is None

    def test_get_store_names_map_empty_input(self):
        from api.Modules.Owners.Repositories import get_store_names_map
        with db_session():
            assert get_store_names_map(db.session, []) == {}
            assert get_store_names_map(db.session, set()) == {}

    def test_get_store_names_map_returns_dict(self, test_store_id):
        from api.Modules.Owners.Repositories import get_store_names_map
        with db_session():
            result = get_store_names_map(db.session, [test_store_id])
            assert test_store_id in result
            assert isinstance(result[test_store_id], str)

    def test_get_store_names_map_ignores_missing_ids(self, test_store_id):
        """Missing ids are silently dropped — empty map for ghost ids."""
        from api.Modules.Owners.Repositories import get_store_names_map
        with db_session():
            result = get_store_names_map(
                db.session, [test_store_id, 999999],
            )
            assert 999999 not in result
            assert test_store_id in result


class TestUsersInStoresQuery:
    def test_returns_users_for_store(self, test_store_id):
        from api.Modules.Owners.Repositories import users_in_stores_query
        with db_session():
            q = users_in_stores_query(db.session, [test_store_id])
            rows = q.all()
            assert all(u.store_id == test_store_id for u in rows)
            assert len(rows) >= 1

    def test_empty_store_list_returns_empty(self):
        from api.Modules.Owners.Repositories import users_in_stores_query
        with db_session():
            q = users_in_stores_query(db.session, [])
            assert q.all() == []

    def test_search_filters_by_username_or_full_name(self, test_store_id):
        from api.Modules.Owners.Repositories import users_in_stores_query
        from api.Modules.Auth.Models import User
        with db_session():
            u = User(
                store_id=test_store_id,
                username="searchable@x.com",
                full_name="Findable Name",
                role="employee",
                is_active=True,
            )
            u.set_password("searchpw1!")
            db.session.add(u)
            db.session.commit()

            q = users_in_stores_query(
                db.session, [test_store_id], search="searchable",
            )
            rows = q.all()
            assert any(u.username == "searchable@x.com" for u in rows)

            q2 = users_in_stores_query(
                db.session, [test_store_id], search="Findable",
            )
            rows2 = q2.all()
            assert any(u.full_name == "Findable Name" for u in rows2)

    def test_search_returns_query_not_list(self, test_store_id):
        """The repo returns a Query so callers can paginate/count."""
        from api.Modules.Owners.Repositories import users_in_stores_query
        from sqlalchemy.orm import Query
        with db_session():
            q = users_in_stores_query(db.session, [test_store_id])
            assert isinstance(q, Query)

    def test_search_trims_whitespace(self, test_store_id):
        """A search of all-whitespace should not apply a filter."""
        from api.Modules.Owners.Repositories import users_in_stores_query
        with db_session():
            q1 = users_in_stores_query(db.session, [test_store_id])
            q2 = users_in_stores_query(
                db.session, [test_store_id], search="   ",
            )
            assert q1.count() == q2.count()
