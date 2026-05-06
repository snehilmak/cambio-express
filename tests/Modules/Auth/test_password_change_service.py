"""Unit tests for Auth.Services.password_change (PR 40)."""


def _seed_user(store_id, *, username, password="oldpassword"):
    from app import User, db
    u = User(
        store_id=store_id, username=username, role="employee",
    )
    u.set_password(password)
    db.session.add(u); db.session.commit()
    return u


# ── change_password ─────────────────────────────────────────


def test_change_password_success(test_store_id):
    from app import app as flask_app, db
    from api.Modules.Auth.Services import change_password
    with flask_app.app_context():
        u = _seed_user(test_store_id, username="user@x.com")
        errors = change_password(
            db.session, u,
            current_pw="oldpassword",
            new_pw="newpassword123",
            confirm_pw="newpassword123",
        )
        db.session.commit()
        assert errors == {}
        assert u.check_password("newpassword123")
        assert not u.check_password("oldpassword")


def test_change_password_rejects_wrong_current(test_store_id):
    from app import app as flask_app, db
    from api.Modules.Auth.Services import change_password
    with flask_app.app_context():
        u = _seed_user(test_store_id, username="user@x.com")
        errors = change_password(
            db.session, u,
            current_pw="WRONG",
            new_pw="newpassword123",
            confirm_pw="newpassword123",
        )
    assert "current_password" in errors
    assert "incorrect" in errors["current_password"].lower()


def test_change_password_rejects_too_short(test_store_id):
    from app import app as flask_app, db
    from api.Modules.Auth.Services import change_password
    with flask_app.app_context():
        u = _seed_user(test_store_id, username="user@x.com")
        errors = change_password(
            db.session, u,
            current_pw="oldpassword",
            new_pw="short",
            confirm_pw="short",
        )
    assert "new_password" in errors
    assert "at least 8" in errors["new_password"]


def test_change_password_rejects_mismatch(test_store_id):
    from app import app as flask_app, db
    from api.Modules.Auth.Services import change_password
    with flask_app.app_context():
        u = _seed_user(test_store_id, username="user@x.com")
        errors = change_password(
            db.session, u,
            current_pw="oldpassword",
            new_pw="abcdefghi",
            confirm_pw="differenttext",
        )
    assert "confirm_password" in errors


def test_change_password_does_not_apply_when_invalid(test_store_id):
    """Validation failures must NOT mutate the user row."""
    from app import app as flask_app, db
    from api.Modules.Auth.Services import change_password
    with flask_app.app_context():
        u = _seed_user(test_store_id, username="user@x.com")
        change_password(
            db.session, u,
            current_pw="WRONG",
            new_pw="newpassword123",
            confirm_pw="newpassword123",
        )
        # Old password still works
        assert u.check_password("oldpassword")


# ── admin_set_password ──────────────────────────────────────


def test_admin_set_password_success(test_store_id):
    """Admin path doesn't require a current password — different
    surface."""
    from app import app as flask_app, db
    from api.Modules.Auth.Services import admin_set_password
    with flask_app.app_context():
        u = _seed_user(test_store_id, username="emp@x.com")
        errors = admin_set_password(
            db.session, u,
            new_pw="freshpw1234",
            confirm_pw="freshpw1234",
        )
        db.session.commit()
        assert errors == {}
        assert u.check_password("freshpw1234")


def test_admin_set_password_rejects_too_short(test_store_id):
    from app import app as flask_app, db
    from api.Modules.Auth.Services import admin_set_password
    with flask_app.app_context():
        u = _seed_user(test_store_id, username="emp@x.com")
        errors = admin_set_password(
            db.session, u,
            new_pw="short",
            confirm_pw="short",
        )
    assert "new_password" in errors


def test_admin_set_password_rejects_mismatch(test_store_id):
    from app import app as flask_app, db
    from api.Modules.Auth.Services import admin_set_password
    with flask_app.app_context():
        u = _seed_user(test_store_id, username="emp@x.com")
        errors = admin_set_password(
            db.session, u,
            new_pw="abcdefghi",
            confirm_pw="zyxwvutsr",
        )
    assert "confirm_password" in errors


def test_admin_set_password_does_not_apply_when_invalid(test_store_id):
    from app import app as flask_app, db
    from api.Modules.Auth.Services import admin_set_password
    with flask_app.app_context():
        u = _seed_user(test_store_id, username="emp@x.com")
        admin_set_password(
            db.session, u, new_pw="x", confirm_pw="x",
        )
        # Original password still works
        assert u.check_password("oldpassword")
