"""Tests for the TimeClock Repositories."""
from datetime import datetime

from tests._app import db, db_session


class TestEmployeesRepository:
    def test_get_employee_name_map_empty_input(self):
        from api.Modules.TimeClock.Repositories import get_employee_name_map
        with db_session():
            assert get_employee_name_map(db.session, []) == {}
            assert get_employee_name_map(db.session, set()) == {}

    def test_get_employee_name_map_returns_dict(self, test_store_id):
        from api.Modules.TimeClock.Repositories import get_employee_name_map
        from api.Modules.Tenancy.Models import StoreEmployee
        with db_session():
            emp = StoreEmployee(
                store_id=test_store_id, name="Alice", is_active=True,
            )
            db.session.add(emp)
            db.session.commit()
            result = get_employee_name_map(db.session, [emp.id])
            assert result[emp.id] == "Alice"

    def test_get_employee_name_map_ignores_missing_ids(self, test_store_id):
        from api.Modules.TimeClock.Repositories import get_employee_name_map
        from api.Modules.Tenancy.Models import StoreEmployee
        with db_session():
            emp = StoreEmployee(
                store_id=test_store_id, name="Bob", is_active=True,
            )
            db.session.add(emp)
            db.session.commit()
            result = get_employee_name_map(db.session, [emp.id, 99999])
            assert emp.id in result
            assert 99999 not in result

    def test_list_active_employees_filters_inactive(self, test_store_id):
        from api.Modules.TimeClock.Repositories import list_active_employees
        from api.Modules.Tenancy.Models import StoreEmployee
        with db_session():
            db.session.query(StoreEmployee).filter_by(
                store_id=test_store_id,
            ).delete()
            db.session.add_all([
                StoreEmployee(store_id=test_store_id, name="Active1",
                               is_active=True),
                StoreEmployee(store_id=test_store_id, name="Inactive",
                               is_active=False),
                StoreEmployee(store_id=test_store_id, name="Active2",
                               is_active=True),
            ])
            db.session.commit()
            rows = list_active_employees(db.session, test_store_id)
            assert all(r.is_active for r in rows)
            names = [r.name for r in rows]
            assert "Inactive" not in names

    def test_list_active_employees_orders_by_name(self, test_store_id):
        from api.Modules.TimeClock.Repositories import list_active_employees
        from api.Modules.Tenancy.Models import StoreEmployee
        with db_session():
            db.session.query(StoreEmployee).filter_by(
                store_id=test_store_id,
            ).delete()
            db.session.add_all([
                StoreEmployee(store_id=test_store_id, name="Zoe",
                               is_active=True),
                StoreEmployee(store_id=test_store_id, name="Alice",
                               is_active=True),
                StoreEmployee(store_id=test_store_id, name="Mark",
                               is_active=True),
            ])
            db.session.commit()
            rows = list_active_employees(db.session, test_store_id)
            assert [r.name for r in rows] == ["Alice", "Mark", "Zoe"]


class TestHistoryRepository:
    def test_list_entry_history_empty(self, test_store_id):
        from api.Modules.TimeClock.Repositories import list_entry_history
        with db_session():
            rows = list_entry_history(db.session, test_store_id, 99999)
            assert rows == []

    def test_list_entry_history_filters_by_target(self, test_store_id):
        from api.Modules.TimeClock.Repositories import list_entry_history
        from api.Modules.Audit.Models import OperatorAuditLog
        with db_session():
            db.session.add_all([
                OperatorAuditLog(
                    store_id=test_store_id, user_id=None,
                    user_name="x", user_role="admin",
                    action="edit", target_type="time_clock_entry",
                    target_id="42", target_label="", summary="",
                    created_at=datetime.utcnow(),
                ),
                OperatorAuditLog(
                    store_id=test_store_id, user_id=None,
                    user_name="x", user_role="admin",
                    action="edit", target_type="other_thing",
                    target_id="42", target_label="", summary="",
                    created_at=datetime.utcnow(),
                ),
                OperatorAuditLog(
                    store_id=test_store_id, user_id=None,
                    user_name="x", user_role="admin",
                    action="edit", target_type="time_clock_entry",
                    target_id="99", target_label="", summary="",
                    created_at=datetime.utcnow(),
                ),
            ])
            db.session.commit()
            rows = list_entry_history(db.session, test_store_id, 42)
            assert len(rows) == 1
            assert rows[0].target_id == "42"
            assert rows[0].target_type == "time_clock_entry"

    def test_list_entry_history_newest_first(self, test_store_id):
        from api.Modules.TimeClock.Repositories import list_entry_history
        from api.Modules.Audit.Models import OperatorAuditLog
        with db_session():
            for i in range(3):
                db.session.add(OperatorAuditLog(
                    store_id=test_store_id, user_id=None,
                    user_name="x", user_role="admin",
                    action=f"edit-{i}",
                    target_type="time_clock_entry",
                    target_id="55", target_label="", summary="",
                    created_at=datetime.utcnow(),
                ))
            db.session.commit()
            rows = list_entry_history(db.session, test_store_id, 55)
            ids = [r.id for r in rows]
            assert ids == sorted(ids, reverse=True)
