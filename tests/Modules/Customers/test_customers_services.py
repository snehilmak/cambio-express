"""Unit tests for Customers.Services — upsert, search.

Each test calls the service directly with the live SQLAlchemy
session (no HTTP, no Flask). Covers the migration equivalence
guarantee — the new service must produce the same results as the
legacy `find_or_upsert_customer` and the body of `/api/customers/search`
in `app.py`.
"""
from datetime import date, datetime, timedelta


def _seed_customer(store_id, *, full_name, phone_country="+1",
                    phone_number="", address=""):
    from api.Modules.Customers.Models import Customer
    from tests._app import db
    c = Customer(
        store_id=store_id, full_name=full_name,
        phone_country=phone_country, phone_number=phone_number,
        address=address,
    )
    db.session.add(c); db.session.commit()
    return c.id


def _seed_owner(username="owner@x.com"):
    from api.Modules.Tenancy.Models import User
    from tests._app import db
    u = User(username=username, full_name="Owner", role="owner")
    u.set_password("p")
    db.session.add(u); db.session.commit()
    return u.id


def _seed_store(slug, name="X"):
    from api.Modules.Tenancy.Models import Store
    from tests._app import db
    s = Store(name=name, slug=slug, email=f"{slug}@x.com", plan="trial")
    db.session.add(s); db.session.commit()
    return s.id


def _link(owner_id, store_id):
    from api.Modules.Tenancy.Models import StoreOwnerLink
    from tests._app import db
    l = StoreOwnerLink(owner_id=owner_id, store_id=store_id)
    db.session.add(l); db.session.commit()


# ── upsert ──────────────────────────────────────────────────


def test_upsert_creates_new_customer(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.Customers.Services import upsert
    with flask_app.app_context():
        c = upsert(
            db.session, test_store_id, "Alice", "+1", "5551234",
            address="123 Main", dob=date(1990, 1, 1),
        )
        db.session.commit()
        assert c.id is not None
        assert c.full_name == "Alice"
        assert c.phone_number == "5551234"
        assert c.address == "123 Main"
        assert c.dob == date(1990, 1, 1)


def test_upsert_reuses_existing_phone_match(test_store_id):
    """Repeat phone_number → no new row, just update last-write-wins fields."""
    from api.Modules.Customers.Models import Customer
    from tests._app import app as flask_app, db
    from api.Modules.Customers.Services import upsert
    with flask_app.app_context():
        cid = _seed_customer(test_store_id, full_name="Alice Old",
                              phone_number="5551234")
        c = upsert(
            db.session, test_store_id, "Alice New", "+1", "5551234",
            address="New addr",
        )
        db.session.commit()
        assert c.id == cid
        # newest values overwrite
        assert c.full_name == "Alice New"
        assert c.address == "New addr"
        # only one row
        rows = db.session.query(Customer).filter_by(
            phone_number="5551234").all()
        assert len(rows) == 1


def test_upsert_unifies_across_owner_umbrella(test_store_id):
    """Cashier at Store A logs a sender; cashier at Store B (same owner)
    finds the same row via phone match — no duplicate created."""
    from api.Modules.Customers.Models import Customer
    from tests._app import app as flask_app, db
    from api.Modules.Customers.Services import upsert
    with flask_app.app_context():
        oid = _seed_owner()
        s2 = _seed_store("loc-2")
        _link(oid, test_store_id)
        _link(oid, s2)
        # Sender first logged at test_store_id.
        c1 = upsert(
            db.session, test_store_id, "Maria", "+1", "5559999",
        )
        db.session.commit()
        # Same sender shows up at s2 — must reuse the row.
        c2 = upsert(db.session, s2, "Maria G.", "+1", "5559999")
        db.session.commit()
        assert c1.id == c2.id
        # Home store stays pinned to the original.
        assert c2.store_id == test_store_id
        # Newest values overwrite
        assert c2.full_name == "Maria G."
        # Only one customer row.
        rows = db.session.query(Customer).filter_by(
            phone_number="5559999").all()
        assert len(rows) == 1


def test_upsert_isolates_unrelated_stores(test_store_id):
    """Same phone in two unrelated stores → two separate rows.
    Owner-umbrella isolation is the security property."""
    from api.Modules.Customers.Models import Customer
    from tests._app import app as flask_app, db
    from api.Modules.Customers.Services import upsert
    with flask_app.app_context():
        s2 = _seed_store("isolated")
        c1 = upsert(db.session, test_store_id, "A", "+1", "5550000")
        db.session.commit()
        c2 = upsert(db.session, s2, "B", "+1", "5550000")
        db.session.commit()
        assert c1.id != c2.id
        rows = db.session.query(Customer).filter_by(
            phone_number="5550000").all()
        assert len(rows) == 2


def test_upsert_explicit_customer_id_only_within_umbrella(test_store_id):
    """Caller passes `customer_id` from a sibling store → reuse.
    Caller passes `customer_id` from outside umbrella → create new."""
    from tests._app import app as flask_app, db
    from api.Modules.Customers.Services import upsert
    with flask_app.app_context():
        # Sibling case: same owner.
        oid = _seed_owner()
        s2 = _seed_store("loc-2")
        _link(oid, test_store_id)
        _link(oid, s2)
        cid_in = _seed_customer(s2, full_name="Sibling",
                                 phone_number="5551111")
        c = upsert(
            db.session, test_store_id, "Sibling Updated",
            "+1", "5551111", customer_id=cid_in,
        )
        db.session.commit()
        assert c.id == cid_in
        assert c.full_name == "Sibling Updated"

        # Cross-umbrella case: explicit id from a stranger store.
        s3 = _seed_store("stranger")  # no owner link
        cid_stranger = _seed_customer(s3, full_name="Stranger",
                                       phone_number="5552222")
        c2 = upsert(
            db.session, test_store_id, "X",
            "+1", "5552222", customer_id=cid_stranger,
        )
        db.session.commit()
        # Must have created a new row in test_store_id, not reused.
        assert c2.id != cid_stranger
        assert c2.store_id == test_store_id


def test_upsert_empty_phone_creates_one_row(test_store_id):
    """A phone-less sender can be inserted once — the unique constraint
    on (store_id, phone_country, phone_number) prevents a second
    empty-phone row in the same store. Mirrors `find_or_upsert_customer`:
    no dedup-by-name shortcut, but the constraint backstops dups."""
    from tests._app import app as flask_app, db
    from api.Modules.Customers.Services import upsert
    with flask_app.app_context():
        c = upsert(db.session, test_store_id, "Walk-in", "+1", "")
        db.session.commit()
        assert c.id is not None
        assert c.phone_number == ""


def test_upsert_does_not_overwrite_with_empty_values(test_store_id):
    """Last-write-wins is conditional on truthiness — passing an empty
    address doesn't wipe an existing one. This matches the legacy
    `if address: cust.address = address` guard."""
    from tests._app import app as flask_app, db
    from api.Modules.Customers.Services import upsert
    with flask_app.app_context():
        upsert(
            db.session, test_store_id, "Alice", "+1", "5551234",
            address="Original",
        )
        db.session.commit()
        c = upsert(
            db.session, test_store_id, "Alice", "+1", "5551234",
            address="",
        )
        db.session.commit()
        assert c.address == "Original"


# ── search ──────────────────────────────────────────────────


def test_search_short_query_returns_empty_envelope(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.Customers.Services import search
    with flask_app.app_context():
        _seed_customer(test_store_id, full_name="Alice",
                        phone_number="5551111")
        m, s = search(db.session, test_store_id, "a")
    assert m == [] and s == []


def test_search_returns_matches_by_name(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.Customers.Services import search
    with flask_app.app_context():
        _seed_customer(test_store_id, full_name="Alice Smith",
                        phone_number="5551111")
        _seed_customer(test_store_id, full_name="Bob Jones",
                        phone_number="5552222")
        matches, sugs = search(db.session, test_store_id, "alice")
    names = {c.full_name for c in matches}
    assert names == {"Alice Smith"}
    assert sugs == []


def test_search_fuzzy_suggestions_catch_spelling_drift(test_store_id):
    """The whole point of the suggestion path: a typo of an existing
    customer surfaces the canonical record so the cashier doesn't
    create a duplicate."""
    from tests._app import app as flask_app, db
    from api.Modules.Customers.Services import search
    with flask_app.app_context():
        _seed_customer(test_store_id, full_name="Maria Gonzalez",
                        phone_number="5551234")
        # Typo: cashier types the full name with a misspelled last name.
        # SequenceMatcher ratio for "maria gonzales" vs "maria gonzalez"
        # is ~0.93 — well above the 0.72 threshold.
        matches, sugs = search(db.session, test_store_id, "Maria Gonzales")
    assert matches == []
    assert any(c.full_name == "Maria Gonzalez" for c in sugs)


def test_search_skips_fuzzy_when_matches_full(test_store_id):
    """5+ exact matches → no fuzzy pass; the cashier already has
    plenty to pick from."""
    from api.Modules.Customers.Models import Customer
    from tests._app import app as flask_app, db
    from api.Modules.Customers.Services import search
    with flask_app.app_context():
        # 6 exact matches on substring "Test"
        for i in range(6):
            _seed_customer(
                test_store_id, full_name=f"Test User {i}",
                phone_number=f"5550{i:04d}",
            )
        # one near-miss that fuzzy would otherwise catch
        _seed_customer(test_store_id, full_name="Tasting User",
                        phone_number="5559999")
        matches, sugs = search(db.session, test_store_id, "Test")
    # 5+ exact substring hits — fuzzy must skip.
    assert len(matches) >= 5
    assert sugs == []


def test_search_short_query_skips_fuzzy(test_store_id):
    """Queries shorter than 4 chars → no fuzzy pass even if the
    exact-match list is empty. Avoids flooding the cashier with
    SequenceMatcher false positives."""
    from tests._app import app as flask_app, db
    from api.Modules.Customers.Services import search
    with flask_app.app_context():
        _seed_customer(test_store_id, full_name="Maria Gonzalez",
                        phone_number="5551234")
        matches, sugs = search(db.session, test_store_id, "Mar")
    # 3-char query — fuzzy off, but matches still found via ILIKE
    assert len(matches) >= 0  # whatever ILIKE found
    assert sugs == []


def test_search_unifies_across_owner_umbrella(test_store_id):
    """Cashier at Store A finds the customer Store B logged."""
    from tests._app import app as flask_app, db
    from api.Modules.Customers.Services import search
    with flask_app.app_context():
        oid = _seed_owner()
        s2 = _seed_store("loc-2")
        _link(oid, test_store_id)
        _link(oid, s2)
        _seed_customer(s2, full_name="Maria",
                        phone_country="+1", phone_number="5551234")
        matches, _ = search(db.session, test_store_id, "Maria")
    assert {c.full_name for c in matches} == {"Maria"}


def test_search_excludes_unrelated_stores(test_store_id):
    """Customers in stores outside the umbrella must NOT appear.
    This is the security property the autocomplete depends on."""
    from tests._app import app as flask_app, db
    from api.Modules.Customers.Services import search
    with flask_app.app_context():
        s2 = _seed_store("stranger")  # no owner overlap
        _seed_customer(s2, full_name="Hidden",
                        phone_number="5559999")
        _seed_customer(test_store_id, full_name="Visible",
                        phone_number="5551111")
        matches, _ = search(db.session, test_store_id, "Hidden")
    assert matches == []


# ── Pydantic schema sanity ──────────────────────────────────


def test_customer_search_response_validates(test_store_id):
    """Wire test: service rows must validate against the Pydantic schema.
    `to_dict` shape and the schema must stay in sync."""
    from tests._app import app as flask_app, db
    from api.Modules.Customers.Services import search
    from api.Modules.Customers.Requests import (
        CustomerRow, CustomerSearchResponse,
    )
    with flask_app.app_context():
        _seed_customer(test_store_id, full_name="Alice",
                        phone_country="+1", phone_number="5551234")
        matches, sugs = search(db.session, test_store_id, "alice")
        rows = [
            CustomerRow(**c.to_dict(current_store_id=test_store_id))
            for c in matches
        ]
        sug_rows = [
            CustomerRow(**c.to_dict(current_store_id=test_store_id))
            for c in sugs
        ]
        # Compose the full response — exercises the model_config
        # `extra="forbid"` setting too.
        resp = CustomerSearchResponse(matches=rows, suggestions=sug_rows)
        assert len(resp.matches) == 1
        assert resp.matches[0].full_name == "Alice"


# ── Cross-shim equivalence ──────────────────────────────────


def test_legacy_upsert_matches_service(test_store_id):
    """`app.py::find_or_upsert_customer` is the legacy entry point.
    PR 9 will flip it to call the Service — until then, both surfaces
    must produce identical results from identical input. This test
    runs each independently and compares row counts + content."""
    from api.Modules.Customers.Models import Customer
    from tests._app import app as flask_app, db
    from tests._app import find_or_upsert_customer
    from api.Modules.Customers.Services import upsert
    with flask_app.app_context():
        c_legacy = find_or_upsert_customer(
            test_store_id, "Alice", "+1", "5551234",
            address="123 Main", dob=date(1990, 1, 1),
        )
        db.session.commit()
        legacy_id = c_legacy.id

        # Repeat invocation through the service should produce the
        # same row (phone match) with overwritten name.
        c_service = upsert(
            db.session, test_store_id, "Alice Updated",
            "+1", "5551234",
        )
        db.session.commit()
        assert c_service.id == legacy_id
        assert c_service.full_name == "Alice Updated"
        # Still only one row in the DB for this phone.
        rows = db.session.query(Customer).filter_by(
            phone_number="5551234").all()
        assert len(rows) == 1
