"""Unit tests for Auth.Repositories.users."""
from tests._app import db, db_session


def _seed_user(store_id, *, username, role="employee", full_name="",
                is_active=True):
    from api.Modules.Tenancy.Models import User
    from tests._app import db
    u = User(
        store_id=store_id, username=username, role=role,
        full_name=full_name, is_active=is_active,
    )
    u.set_password("p")
    db.session.add(u); db.session.commit()
    return u.id


# ── find_user_by_id ─────────────────────────────────────────


def test_find_user_by_id_returns_user(test_admin_id):
    from tests._app import db
    from api.Modules.Auth.Repositories import find_user_by_id
    with db_session():
        u = find_user_by_id(db.session, test_admin_id)
    assert u is not None
    assert u.username == "admin@test.com"


def test_find_user_by_id_returns_none_when_missing():
    from tests._app import db
    from api.Modules.Auth.Repositories import find_user_by_id
    with db_session():
        u = find_user_by_id(db.session, 999_999)
    assert u is None


# ── find_user_by_username_in_store ──────────────────────────


def test_find_user_by_username_in_store_returns_match(test_store_id):
    from tests._app import db
    from api.Modules.Auth.Repositories import find_user_by_username_in_store
    with db_session():
        u = find_user_by_username_in_store(
            db.session, test_store_id, "admin@test.com",
        )
    assert u is not None
    assert u.role == "admin"


def test_find_user_by_username_in_store_returns_none_for_other_store(test_store_id):
    """Cross-store lookup must miss — the unique constraint allows the
    same username at different stores, but each request scope is one
    store."""
    from api.Modules.Tenancy.Models import Store
    from tests._app import db
    from api.Modules.Auth.Repositories import find_user_by_username_in_store
    with db_session():
        s2 = Store(name="Other", slug="other-auth",
                    email="o@x.com", plan="trial")
        db.session.add(s2); db.session.commit()
        sid2 = s2.id
        # Lookup admin@test.com inside the OTHER store — should miss.
        u = find_user_by_username_in_store(
            db.session, sid2, "admin@test.com",
        )
    assert u is None


def test_find_user_by_username_in_store_finds_superadmin():
    """`store_id=None` is the superadmin scope. The seeded fixture
    creates `superadmin / super2025!` at store_id=None."""
    from tests._app import db
    from api.Modules.Auth.Repositories import find_user_by_username_in_store
    with db_session():
        u = find_user_by_username_in_store(
            db.session, None, "superadmin",
        )
    assert u is not None
    assert u.role == "superadmin"


def test_find_user_by_username_in_store_returns_none_for_empty_username(test_store_id):
    """Empty/whitespace username never matches — defensive against
    callers that don't strip the form input."""
    from tests._app import db
    from api.Modules.Auth.Repositories import find_user_by_username_in_store
    with db_session():
        assert find_user_by_username_in_store(
            db.session, test_store_id, "",
        ) is None


# ── find_user_by_username ───────────────────────────────────


def test_find_user_by_username_finds_match():
    """Cross-store username lookup. Used by the password-reset path
    where the caller types just the email and we figure out which
    store to mail."""
    from tests._app import db
    from api.Modules.Auth.Repositories import find_user_by_username
    with db_session():
        u = find_user_by_username(db.session, "admin@test.com")
    assert u is not None


def test_find_user_by_username_role_filter_excludes_normal_users():
    """`role="superadmin"` filter must reject regular users — the
    legacy reset-superadmin CLI relies on this to refuse promotion."""
    from tests._app import db
    from api.Modules.Auth.Repositories import find_user_by_username
    with db_session():
        u = find_user_by_username(
            db.session, "admin@test.com", role="superadmin",
        )
    assert u is None


def test_find_user_by_username_role_filter_finds_superadmin():
    from tests._app import db
    from api.Modules.Auth.Repositories import find_user_by_username
    with db_session():
        u = find_user_by_username(
            db.session, "superadmin", role="superadmin",
        )
    assert u is not None


# ── list_users_in_store ─────────────────────────────────────


def test_list_users_in_store_orders_by_id(test_store_id):
    from tests._app import db
    from api.Modules.Auth.Repositories import list_users_in_store
    with db_session():
        _seed_user(test_store_id, username="emp1@x.com")
        _seed_user(test_store_id, username="emp2@x.com")
        users = list_users_in_store(db.session, test_store_id)
    # Seeded admin@test.com (id=2) + emp1 + emp2 in insertion order.
    usernames = [u.username for u in users]
    assert usernames == ["admin@test.com", "emp1@x.com", "emp2@x.com"]


def test_list_users_in_store_role_filter(test_store_id):
    from tests._app import db
    from api.Modules.Auth.Repositories import list_users_in_store
    with db_session():
        _seed_user(test_store_id, username="emp@x.com", role="employee")
        users = list_users_in_store(
            db.session, test_store_id, roles=["admin"],
        )
    assert {u.username for u in users} == {"admin@test.com"}


def test_list_users_in_store_active_only(test_store_id):
    from tests._app import db
    from api.Modules.Auth.Repositories import list_users_in_store
    with db_session():
        _seed_user(test_store_id, username="quit@x.com", is_active=False)
        users = list_users_in_store(
            db.session, test_store_id, active_only=True,
        )
    assert "quit@x.com" not in {u.username for u in users}


def test_list_users_in_store_isolates_other_stores(test_store_id):
    from api.Modules.Tenancy.Models import Store
    from tests._app import db
    from api.Modules.Auth.Repositories import list_users_in_store
    with db_session():
        s2 = Store(name="Other", slug="other-auth-list",
                    email="o@x.com", plan="trial")
        db.session.add(s2); db.session.commit()
        _seed_user(s2.id, username="hidden@x.com")
        users = list_users_in_store(db.session, test_store_id)
    assert "hidden@x.com" not in {u.username for u in users}
