"""Unit tests for Transfers.Services.form_inputs (PR 78)."""
from datetime import date

from api.Modules.Tenancy.Models import Store, StoreEmployee
from tests._app import db, db_session


def _add_store(db, *, slug="form-store"):
    s = Store(name=slug, slug=slug, plan="basic",
              email=f"{slug}@example.com")
    db.add(s); db.flush()
    return s


def _add_employee(db, store_id, *, name="Cashier", is_active=True):
    e = StoreEmployee(
        store_id=store_id,
        name=name,
        is_active=is_active,
    )
    db.add(e); db.flush()
    return e


# ── parse_dob ─────────────────────────────────────────────


def test_parse_dob_valid_iso_string():
    from api.Modules.Transfers.Services import parse_dob
    assert parse_dob("1990-04-15") == date(1990, 4, 15)


def test_parse_dob_blank_returns_none():
    """Blank form input → None so we store NULL rather than
    crash."""
    from api.Modules.Transfers.Services import parse_dob
    assert parse_dob("") is None
    assert parse_dob(None) is None


def test_parse_dob_malformed_returns_none():
    """Bad date format → None (defensive against client-side
    weirdness)."""
    from api.Modules.Transfers.Services import parse_dob
    assert parse_dob("04/15/1990") is None
    assert parse_dob("not-a-date") is None
    assert parse_dob("1990-13-99") is None  # invalid month/day


def test_parse_dob_handles_extra_whitespace():
    """The strptime format is strict; whitespace doesn't parse —
    we return None rather than mangle the value."""
    from api.Modules.Transfers.Services import parse_dob
    # Surrounding whitespace breaks strptime → None
    assert parse_dob(" 1990-04-15 ") is None


# ── active_roster ─────────────────────────────────────────


def test_active_roster_returns_only_active_employees():
    """Inactive cashiers are hidden from the dropdown so new
    transfers can't be credited to former employees."""
    from tests._app import db
    from api.Modules.Transfers.Services import active_roster
    with db_session():
        db.session.query(StoreEmployee).delete()
        db.session.commit()
        s = _add_store(db.session, slug="roster-active")
        active = _add_employee(db.session, s.id, name="Active",
                                is_active=True)
        _add_employee(db.session, s.id, name="Former",
                      is_active=False)
        db.session.flush()
        roster = active_roster(db.session, s.id)
        names = [e.name for e in roster]
        assert "Active" in names
        assert "Former" not in names


def test_active_roster_sorted_alphabetically():
    from tests._app import db
    from api.Modules.Transfers.Services import active_roster
    with db_session():
        db.session.query(StoreEmployee).delete()
        db.session.commit()
        s = _add_store(db.session, slug="roster-sort")
        for n in ("Charlie", "Alice", "Bob"):
            _add_employee(db.session, s.id, name=n)
        db.session.flush()
        roster = active_roster(db.session, s.id)
        assert [e.name for e in roster] == ["Alice", "Bob", "Charlie"]


def test_active_roster_filters_by_store():
    """Cross-store cashiers don't appear."""
    from tests._app import db
    from api.Modules.Transfers.Services import active_roster
    with db_session():
        db.session.query(StoreEmployee).delete()
        db.session.query(Store).filter(Store.slug.like("roster-x-%")).delete()
        db.session.commit()
        s1 = _add_store(db.session, slug="roster-x-1")
        s2 = _add_store(db.session, slug="roster-x-2")
        _add_employee(db.session, s1.id, name="In-Scope")
        _add_employee(db.session, s2.id, name="Out-Of-Scope")
        db.session.flush()
        roster = active_roster(db.session, s1.id)
        names = [e.name for e in roster]
        assert "In-Scope" in names
        assert "Out-Of-Scope" not in names


def test_active_roster_empty_when_no_active():
    from tests._app import db
    from api.Modules.Transfers.Services import active_roster
    with db_session():
        db.session.query(StoreEmployee).delete()
        db.session.commit()
        s = _add_store(db.session, slug="roster-empty")
        _add_employee(db.session, s.id, name="Former",
                      is_active=False)
        db.session.flush()
        assert active_roster(db.session, s.id) == []


# ── pick_employee ─────────────────────────────────────────


def test_pick_employee_returns_employee_and_name():
    from tests._app import db
    from api.Modules.Transfers.Services import pick_employee
    with db_session():
        db.session.query(StoreEmployee).delete()
        db.session.commit()
        s = _add_store(db.session, slug="pick-1")
        e = _add_employee(db.session, s.id, name="Carla")
        db.session.flush()
        emp, name = pick_employee(db.session, s.id, str(e.id))
        assert emp.id == e.id
        assert name == "Carla"


def test_pick_employee_int_id_works():
    """Form posts strings, but defensive: int input also works."""
    from tests._app import db
    from api.Modules.Transfers.Services import pick_employee
    with db_session():
        db.session.query(StoreEmployee).delete()
        db.session.commit()
        s = _add_store(db.session, slug="pick-int")
        e = _add_employee(db.session, s.id, name="Diana")
        db.session.flush()
        emp, name = pick_employee(db.session, s.id, e.id)
        assert emp.id == e.id


def test_pick_employee_blank_returns_none():
    from tests._app import db
    from api.Modules.Transfers.Services import pick_employee
    with db_session():
        s = _add_store(db.session, slug="pick-blank")
        emp, name = pick_employee(db.session, s.id, "")
        assert emp is None
        assert name == ""
        emp, name = pick_employee(db.session, s.id, None)
        assert emp is None
        assert name == ""


def test_pick_employee_bad_int_returns_none():
    """Non-numeric input shouldn't crash."""
    from tests._app import db
    from api.Modules.Transfers.Services import pick_employee
    with db_session():
        s = _add_store(db.session, slug="pick-bad")
        emp, name = pick_employee(db.session, s.id, "not-a-number")
        assert emp is None
        assert name == ""


def test_pick_employee_rejects_cross_store():
    """An attacker submitting another store's employee_id gets
    None back — the SQL filter on store_id is the gate."""
    from tests._app import db
    from api.Modules.Transfers.Services import pick_employee
    with db_session():
        db.session.query(StoreEmployee).delete()
        db.session.query(Store).filter(Store.slug.like("pick-cross-%")).delete()
        db.session.commit()
        s_a = _add_store(db.session, slug="pick-cross-a")
        s_b = _add_store(db.session, slug="pick-cross-b")
        e_b = _add_employee(db.session, s_b.id, name="Belongs to B")
        db.session.flush()
        # Pick using store A's id but trying to claim store B's
        # employee → rejected.
        emp, name = pick_employee(db.session, s_a.id, str(e_b.id))
        assert emp is None
        assert name == ""


def test_pick_employee_unknown_id_returns_none():
    from tests._app import db
    from api.Modules.Transfers.Services import pick_employee
    with db_session():
        s = _add_store(db.session, slug="pick-unknown")
        emp, name = pick_employee(db.session, s.id, "999999")
        assert emp is None
        assert name == ""


# ── legacy Flask wrappers ─────────────────────────────────






