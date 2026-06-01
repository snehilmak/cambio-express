"""Tests for the Superadmin Repositories.

Pure SQL helpers — no permission checks, no audit, no commits.
Verifies query shape: filters, ordering, edge cases.
"""
from datetime import datetime, timedelta

from tests._app import db, db_session


class TestStoresRepository:
    def test_list_all_stores_returns_rows(self, test_store_id):
        from api.Modules.Superadmin.Repositories import list_all_stores
        with db_session():
            stores = list_all_stores(db.session)
            assert len(stores) >= 1
            assert any(s.id == test_store_id for s in stores)

    def test_list_all_stores_newest_first_ordering(self):
        from api.Modules.Superadmin.Repositories import list_all_stores_newest_first
        from api.Modules.Tenancy.Models import Store
        with db_session():
            older = Store(
                name="OlderStore", slug="older-store",
                created_at=datetime.utcnow() - timedelta(days=10),
            )
            newer = Store(
                name="NewerStore", slug="newer-store",
                created_at=datetime.utcnow(),
            )
            db.session.add_all([older, newer])
            db.session.commit()

            stores = list_all_stores_newest_first(db.session)
            slugs = [s.slug for s in stores]
            assert slugs.index("newer-store") < slugs.index("older-store")

    def test_list_stores_by_ids_empty_input(self):
        from api.Modules.Superadmin.Repositories import list_stores_by_ids
        with db_session():
            assert list_stores_by_ids(db.session, []) == []

    def test_list_stores_by_ids_returns_matching(self, test_store_id):
        from api.Modules.Superadmin.Repositories import list_stores_by_ids
        with db_session():
            stores = list_stores_by_ids(
                db.session, [test_store_id, 999999],
            )
            assert len(stores) == 1
            assert stores[0].id == test_store_id

    def test_get_store_by_slug_present(self, test_store_id):
        from api.Modules.Superadmin.Repositories import get_store_by_slug
        from api.Modules.Tenancy.Models import Store
        with db_session():
            store = db.session.get(Store, test_store_id)
            assert store is not None
            found = get_store_by_slug(db.session, store.slug)
            assert found is not None
            assert found.id == test_store_id

    def test_get_store_by_slug_missing(self):
        from api.Modules.Superadmin.Repositories import get_store_by_slug
        with db_session():
            assert get_store_by_slug(db.session, "does-not-exist-xxx") is None

    def test_count_all_stores(self):
        from api.Modules.Superadmin.Repositories import (
            count_all_stores, list_all_stores,
        )
        with db_session():
            n = count_all_stores(db.session)
            assert n == len(list_all_stores(db.session))


class TestUsersRepository:
    def test_list_users_in_store_filters_correctly(self, test_store_id):
        from api.Modules.Superadmin.Repositories import list_users_in_store
        with db_session():
            users = list_users_in_store(db.session, test_store_id)
            assert all(u.store_id == test_store_id for u in users)
            assert len(users) >= 1

    def test_list_users_in_store_oldest_first(self, test_store_id):
        from api.Modules.Superadmin.Repositories import list_users_in_store
        with db_session():
            users = list_users_in_store(db.session, test_store_id)
            if len(users) >= 2:
                # created_at ascending
                assert all(
                    users[i].created_at <= users[i + 1].created_at
                    for i in range(len(users) - 1)
                )

    def test_list_active_admins_filters_role_and_status(self, test_store_id):
        from api.Modules.Superadmin.Repositories import list_active_admins_for_store
        from api.Modules.Auth.Models import User
        with db_session():
            # Add an inactive admin — should NOT appear
            inactive = User(
                store_id=test_store_id,
                username="inactive-admin@x.com",
                full_name="Inactive Admin",
                role="admin",
                is_active=False,
            )
            inactive.set_password("inactivepw1!")
            db.session.add(inactive)
            db.session.commit()

            admins = list_active_admins_for_store(db.session, test_store_id)
            assert all(a.role == "admin" for a in admins)
            assert all(a.is_active for a in admins)
            assert not any(a.username == "inactive-admin@x.com" for a in admins)

    def test_list_active_admins_excludes_employees(self, test_store_id):
        from api.Modules.Superadmin.Repositories import list_active_admins_for_store
        with db_session():
            admins = list_active_admins_for_store(db.session, test_store_id)
            assert not any(a.role == "employee" for a in admins)

    def test_count_all_users(self):
        from api.Modules.Superadmin.Repositories import count_all_users
        with db_session():
            n = count_all_users(db.session)
            assert n >= 1


class TestDiscountsRepository:
    def test_list_discount_codes_empty(self):
        from api.Modules.Superadmin.Repositories import list_discount_codes
        with db_session():
            rows = list_discount_codes(db.session)
            assert isinstance(rows, list)

    def test_get_discount_code_missing(self):
        from api.Modules.Superadmin.Repositories import get_discount_code
        with db_session():
            assert get_discount_code(db.session, 999999) is None


class TestAuditRepository:
    def test_superadmin_audit_query_returns_query(self):
        from api.Modules.Superadmin.Repositories import superadmin_audit_query
        from sqlalchemy.orm import Query
        with db_session():
            q = superadmin_audit_query(db.session)
            assert isinstance(q, Query)

    def test_superadmin_audit_query_filters_by_action(self):
        from api.Modules.Superadmin.Repositories import superadmin_audit_query
        from api.Modules.Audit.Models import SuperadminAuditLog
        with db_session():
            db.session.add(SuperadminAuditLog(
                admin_id=None, admin_name="x",
                action="extend_trial",
                target_type="store", target_id="1", details="",
            ))
            db.session.add(SuperadminAuditLog(
                admin_id=None, admin_name="x",
                action="comp_plan",
                target_type="store", target_id="1", details="",
            ))
            db.session.commit()

            q1 = superadmin_audit_query(db.session, action="extend")
            actions = [r.action for r in q1.all()]
            assert "extend_trial" in actions
            assert "comp_plan" not in actions


class TestWebhooksRepository:
    def test_email_events_query_no_filter(self):
        from api.Modules.Superadmin.Repositories import email_events_query
        from sqlalchemy.orm import Query
        with db_session():
            q = email_events_query(db.session)
            assert isinstance(q, Query)

    def test_email_events_query_filters_by_search(self):
        from api.Modules.Superadmin.Repositories import email_events_query
        from api.Modules.Webhooks.Models import EmailEvent
        with db_session():
            db.session.add(EmailEvent(
                to_addr="findme@x.com",
                event_type="delivered",
                created_at=datetime.utcnow(),
            ))
            db.session.add(EmailEvent(
                to_addr="other@x.com",
                event_type="delivered",
                created_at=datetime.utcnow(),
            ))
            db.session.commit()

            q = email_events_query(db.session, search="findme")
            addrs = [r.to_addr for r in q.all()]
            assert "findme@x.com" in addrs
            assert "other@x.com" not in addrs

    def test_email_events_query_filters_by_type(self):
        from api.Modules.Superadmin.Repositories import email_events_query
        from api.Modules.Webhooks.Models import EmailEvent
        with db_session():
            db.session.add(EmailEvent(
                to_addr="t@x.com",
                event_type="bounced",
                created_at=datetime.utcnow(),
            ))
            db.session.add(EmailEvent(
                to_addr="t2@x.com",
                event_type="delivered",
                created_at=datetime.utcnow(),
            ))
            db.session.commit()

            q = email_events_query(db.session, event_type="bounced")
            types = [r.event_type for r in q.all()]
            assert all(t == "bounced" for t in types)
