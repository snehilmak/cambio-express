"""Tests for the shared audit helpers (api/Core/Audit.py).

Covers audit_operator() + audit_superadmin() + the @audit_action
decorator. Verifies the JWT-claims-aware extraction works and
that schema limits are still enforced through the underlying
recorder.
"""
import pytest

from tests._app import db, db_session
from tests.conftest import login_admin, login_superadmin


def test_audit_operator_extracts_identity_from_claims(test_store_id):
    from api.Core.Audit import audit_operator
    from api.Modules.Audit.Models import OperatorAuditLog

    claims = {
        "sub": 42,
        "username": "admin@test.com",
        "role": "admin",
        "store_id": test_store_id,
    }
    with db_session():
        before = db.session.query(OperatorAuditLog).count()
        audit_operator(
            db.session, claims,
            action="test_action",
            target_type="thing",
            target_id="99",
            target_label="The Thing",
            summary="did a thing",
        )
        db.session.commit()
        after = db.session.query(OperatorAuditLog).count()
        assert after == before + 1
        row = (
            db.session.query(OperatorAuditLog)
            .order_by(OperatorAuditLog.id.desc())
            .first()
        )
        assert row.user_id == 42
        assert row.user_name == "admin@test.com"
        assert row.user_role == "admin"
        assert row.store_id == test_store_id
        assert row.action == "test_action"
        assert row.target_type == "thing"
        assert row.summary == "did a thing"


def test_audit_operator_falls_back_to_full_name(test_store_id):
    """When username missing, use full_name."""
    from api.Core.Audit import audit_operator
    from api.Modules.Audit.Models import OperatorAuditLog

    claims = {
        "sub": 1,
        "full_name": "Jane Doe",
        "role": "admin",
        "store_id": test_store_id,
    }
    with db_session():
        audit_operator(
            db.session, claims,
            action="test", target_type="thing",
        )
        db.session.commit()
        row = (
            db.session.query(OperatorAuditLog)
            .order_by(OperatorAuditLog.id.desc())
            .first()
        )
        assert row.user_name == "Jane Doe"


def test_audit_operator_explicit_store_id_override(test_store_id):
    """Owners with no store_id in JWT can pass it explicitly."""
    from api.Core.Audit import audit_operator
    from api.Modules.Audit.Models import OperatorAuditLog

    claims = {
        "sub": 99,
        "username": "owner@x.com",
        "role": "owner",
        "store_id": None,
    }
    with db_session():
        audit_operator(
            db.session, claims,
            store_id=test_store_id,
            action="cross_store_op", target_type="thing",
        )
        db.session.commit()
        row = (
            db.session.query(OperatorAuditLog)
            .order_by(OperatorAuditLog.id.desc())
            .first()
        )
        assert row.store_id == test_store_id


def test_audit_operator_handles_missing_user_id():
    """Anonymous/system actions still get a row."""
    from api.Core.Audit import audit_operator
    from api.Modules.Audit.Models import OperatorAuditLog

    claims = {
        "username": "system",
        "role": "admin",
        "store_id": 1,
    }
    with db_session():
        audit_operator(
            db.session, claims,
            action="auto", target_type="cron",
        )
        db.session.commit()
        row = (
            db.session.query(OperatorAuditLog)
            .order_by(OperatorAuditLog.id.desc())
            .first()
        )
        assert row.user_id is None


def test_audit_superadmin_records_with_user_row():
    from api.Core.Audit import audit_superadmin
    from api.Modules.Audit.Models import SuperadminAuditLog
    from api.Modules.Tenancy.Models import User

    with db_session():
        sa = (
            db.session.query(User)
            .filter_by(role="superadmin")
            .first()
        )
        assert sa is not None
        audit_superadmin(
            db.session, sa,
            action="test_action",
            target_type="store",
            target_id="42",
            details="some details",
        )
        db.session.commit()
        row = (
            db.session.query(SuperadminAuditLog)
            .order_by(SuperadminAuditLog.id.desc())
            .first()
        )
        assert row.admin_id == sa.id
        assert row.action == "test_action"
        assert row.target_id == "42"
        assert row.details == "some details"


def test_audit_superadmin_uses_full_name_then_username(test_store_id):
    """admin_name snapshot prefers full_name."""
    from api.Core.Audit import audit_superadmin
    from api.Modules.Audit.Models import SuperadminAuditLog
    from api.Modules.Tenancy.Models import User

    with db_session():
        sa = (
            db.session.query(User)
            .filter_by(role="superadmin")
            .first()
        )
        sa.full_name = "Mr. Superadmin"
        db.session.commit()
        audit_superadmin(db.session, sa, action="test_name")
        db.session.commit()
        row = (
            db.session.query(SuperadminAuditLog)
            .order_by(SuperadminAuditLog.id.desc())
            .first()
        )
        assert row.admin_name == "Mr. Superadmin"


def test_audit_decorator_wraps_sync_function(test_store_id):
    from api.Core.Audit import audit_action
    from api.Modules.Audit.Models import OperatorAuditLog

    @audit_action(action="decorated", target_type="thing")
    def my_endpoint(*, db, claims):
        return {"ok": True}

    claims = {
        "sub": 1, "username": "x", "role": "admin",
        "store_id": test_store_id,
    }
    with db_session():
        before = db.session.query(OperatorAuditLog).count()
        result = my_endpoint(db=db.session, claims=claims)
        assert result == {"ok": True}
        after = db.session.query(OperatorAuditLog).count()
        assert after == before + 1
        row = (
            db.session.query(OperatorAuditLog)
            .order_by(OperatorAuditLog.id.desc())
            .first()
        )
        assert row.action == "decorated"


def test_audit_decorator_supports_callable_summary(test_store_id):
    from api.Core.Audit import audit_action
    from api.Modules.Audit.Models import OperatorAuditLog

    @audit_action(
        action="upd",
        target_type="thing",
        summary=lambda **kw: f"name={kw.get('name')}",
    )
    def my_endpoint(*, db, claims, name):
        return name

    claims = {
        "sub": 1, "username": "x", "role": "admin",
        "store_id": test_store_id,
    }
    with db_session():
        my_endpoint(db=db.session, claims=claims, name="foo")
        row = (
            db.session.query(OperatorAuditLog)
            .order_by(OperatorAuditLog.id.desc())
            .first()
        )
        assert row.summary == "name=foo"


def test_audit_decorator_rejects_invalid_scope():
    from api.Core.Audit import audit_action
    with pytest.raises(ValueError, match="scope must be"):
        audit_action(action="x", target_type="y", scope="bogus")


def test_audit_decorator_does_not_run_on_exception(test_store_id):
    """If the wrapped function raises, no audit row should be written."""
    from api.Core.Audit import audit_action
    from api.Modules.Audit.Models import OperatorAuditLog

    @audit_action(action="should_not_log", target_type="thing")
    def failing_endpoint(*, db, claims):
        raise RuntimeError("boom")

    claims = {
        "sub": 1, "username": "x", "role": "admin",
        "store_id": test_store_id,
    }
    with db_session():
        before = db.session.query(OperatorAuditLog).count()
        with pytest.raises(RuntimeError):
            failing_endpoint(db=db.session, claims=claims)
        after = db.session.query(OperatorAuditLog).count()
        assert after == before


def test_audit_operator_truncates_long_strings():
    """The underlying recorder caps each field — verify the
    facade passes them through."""
    from api.Core.Audit import audit_operator
    from api.Modules.Audit.Models import OperatorAuditLog

    long_label = "x" * 500
    long_summary = "y" * 5000
    claims = {"sub": 1, "username": "x", "role": "admin", "store_id": 1}
    with db_session():
        audit_operator(
            db.session, claims,
            action="trunc_test",
            target_type="thing",
            target_label=long_label,
            summary=long_summary,
        )
        db.session.commit()
        row = (
            db.session.query(OperatorAuditLog)
            .order_by(OperatorAuditLog.id.desc())
            .first()
        )
        assert len(row.target_label) <= 160
        assert len(row.summary) <= 2000
