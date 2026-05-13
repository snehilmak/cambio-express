"""Unit tests for Audit.Services.recorder (PR 52)."""
from unittest.mock import MagicMock


# ── record_superadmin_action ───────────────────────────────


def test_superadmin_records_with_full_kwargs():
    from api.Modules.Audit.Services import record_superadmin_action
    db = MagicMock()
    row = record_superadmin_action(
        db,
        admin_id=7,
        admin_name="Alice Admin",
        action="extend_trial",
        target_type="store",
        target_id="42",
        details="extended by 14 days",
    )
    assert row.admin_id == 7
    assert row.admin_name == "Alice Admin"
    assert row.action == "extend_trial"
    assert row.target_type == "store"
    assert row.target_id == "42"
    assert row.details == "extended by 14 days"
    assert db.add.call_count == 1


def test_superadmin_records_with_optional_kwargs_omitted():
    """target_type/id/details default to '' so a no-target action
    (like 'logout' or 'restart_cron') is still loggable."""
    from api.Modules.Audit.Services import record_superadmin_action
    db = MagicMock()
    row = record_superadmin_action(
        db,
        admin_id=1,
        admin_name="root",
        action="restart_cron",
    )
    assert row.target_type == ""
    assert row.target_id == ""
    assert row.details == ""
    assert db.add.call_count == 1


def test_superadmin_truncates_long_strings():
    """Schema columns cap at 30/60/2000 chars; the recorder must
    truncate rather than rely on DB-side errors."""
    from api.Modules.Audit.Services import record_superadmin_action
    db = MagicMock()
    long_target_type = "x" * 100
    long_target_id = "y" * 100
    long_details = "z" * 5000
    row = record_superadmin_action(
        db,
        admin_id=1,
        admin_name="root",
        action="trim_test",
        target_type=long_target_type,
        target_id=long_target_id,
        details=long_details,
    )
    assert len(row.target_type) == 30
    assert len(row.target_id) == 60
    assert len(row.details) == 2000


def test_superadmin_coerces_non_string_target():
    """Callers pass int target_id (e.g. a Store.id) — the recorder
    str()-coerces it without surprise."""
    from api.Modules.Audit.Services import record_superadmin_action
    db = MagicMock()
    row = record_superadmin_action(
        db,
        admin_id=1,
        admin_name="root",
        action="comp_plan",
        target_id=42,  # int, not str
    )
    assert row.target_id == "42"


def test_superadmin_admin_id_can_be_none():
    """Edge case: deleted/system actions may have no admin row.
    Schema allows admin_id NULL."""
    from api.Modules.Audit.Services import record_superadmin_action
    db = MagicMock()
    row = record_superadmin_action(
        db,
        admin_id=None,
        admin_name="system",
        action="auto_purge",
    )
    assert row.admin_id is None
    assert row.admin_name == "system"


def test_superadmin_does_not_commit():
    """Caller wraps the audit row in their own transaction."""
    from api.Modules.Audit.Services import record_superadmin_action
    db = MagicMock()
    record_superadmin_action(
        db,
        admin_id=1, admin_name="root", action="x",
    )
    assert db.commit.call_count == 0


# ── record_operator_action ─────────────────────────────────


def test_operator_records_with_full_kwargs():
    from api.Modules.Audit.Services import record_operator_action
    db = MagicMock()
    row = record_operator_action(
        db,
        store_id=99,
        user_id=12,
        user_name="Cashier Carla",
        user_role="employee",
        target_type="transfer",
        target_id="555",
        target_label="$120 to MX",
        action="delete",
        summary="customer changed mind",
    )
    assert row.store_id == 99
    assert row.user_id == 12
    assert row.user_name == "Cashier Carla"
    assert row.user_role == "employee"
    assert row.target_type == "transfer"
    assert row.target_id == "555"
    assert row.target_label == "$120 to MX"
    assert row.action == "delete"
    assert row.summary == "customer changed mind"
    assert db.add.call_count == 1


def test_operator_truncates_long_strings():
    from api.Modules.Audit.Services import record_operator_action
    db = MagicMock()
    row = record_operator_action(
        db,
        store_id=1, user_id=1,
        user_name="x" * 200,
        user_role="r" * 50,
        target_type="t" * 100,
        target_id="i" * 100,
        target_label="L" * 300,
        action="a" * 80,
        summary="s" * 5000,
    )
    assert len(row.user_name) == 120
    assert len(row.user_role) == 20
    assert len(row.target_type) == 30
    assert len(row.target_id) == 60
    assert len(row.target_label) == 160
    assert len(row.action) == 30
    assert len(row.summary) == 2000


def test_operator_user_id_nullable():
    """Anonymous / system actions may have no user row."""
    from api.Modules.Audit.Services import record_operator_action
    db = MagicMock()
    row = record_operator_action(
        db,
        store_id=1,
        user_id=None,
        user_name="system",
        user_role="",
        target_type="batch",
        action="auto_lock",
    )
    assert row.user_id is None


def test_operator_does_not_commit():
    from api.Modules.Audit.Services import record_operator_action
    db = MagicMock()
    record_operator_action(
        db,
        store_id=1, user_id=1, user_name="x", user_role="admin",
        target_type="t", action="a",
    )
    assert db.commit.call_count == 0


# ── legacy Flask wrappers ──────────────────────────────────




