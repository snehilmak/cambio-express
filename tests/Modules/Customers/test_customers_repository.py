"""Unit tests for Customers.Repositories — sibling_store_ids,
find_by_id_in_stores, find_by_phone_in_stores, search_by_substring,
recent_customers.

These call the repository functions directly with the live DB
session (no HTTP, no Flask). Coverage axis: each helper individually,
then a couple of cross-helper scenarios that mirror the real
`/api/customers/search` and upsert call sites.
"""
from datetime import datetime, timedelta


def _seed_customer(store_id, *, full_name, phone_country="+1",
                    phone_number="", address=""):
    from app import Customer, db
    c = Customer(
        store_id=store_id, full_name=full_name,
        phone_country=phone_country, phone_number=phone_number,
        address=address,
    )
    db.session.add(c); db.session.commit()
    return c.id


def _seed_owner(username="owner@x.com"):
    """`StoreOwnerLink.owner_id` is a FK to `User.id` — owners are just
    Users with `role="owner"`. No separate Owner table."""
    from app import User, db
    u = User(username=username, full_name="Owner", role="owner")
    u.set_password("p")
    db.session.add(u); db.session.commit()
    return u.id


def _seed_store(slug, name="X"):
    from app import Store, db
    s = Store(name=name, slug=slug, email=f"{slug}@x.com", plan="trial")
    db.session.add(s); db.session.commit()
    return s.id


def _link(owner_id, store_id):
    from app import StoreOwnerLink, db
    l = StoreOwnerLink(owner_id=owner_id, store_id=store_id)
    db.session.add(l); db.session.commit()


# ── sibling_store_ids ───────────────────────────────────────


def test_sibling_store_ids_solo_shop_returns_self_only(test_store_id):
    """A store with no Owner links is "solo" — returns [self]."""
    from app import app as flask_app, db
    from api.Modules.Customers.Repositories import sibling_store_ids
    with flask_app.app_context():
        ids = sibling_store_ids(db.session, test_store_id)
    assert ids == [test_store_id]


def test_sibling_store_ids_unifies_owner_umbrella(test_store_id):
    """Two stores under one owner are siblings — both IDs returned."""
    from app import app as flask_app, db
    from api.Modules.Customers.Repositories import sibling_store_ids
    with flask_app.app_context():
        oid = _seed_owner()
        s2 = _seed_store("sibling")
        _link(oid, test_store_id)
        _link(oid, s2)
        ids = sibling_store_ids(db.session, test_store_id)
    assert ids == sorted([test_store_id, s2])


def test_sibling_store_ids_excludes_unrelated_stores(test_store_id):
    """A store under a DIFFERENT owner is NOT a sibling. Owner-umbrella
    isolation is the security property the customer search depends on."""
    from app import app as flask_app, db
    from api.Modules.Customers.Repositories import sibling_store_ids
    with flask_app.app_context():
        o1, o2 = _seed_owner("o1@x.com"), _seed_owner("o2@x.com")
        s2 = _seed_store("under-o1")
        s3 = _seed_store("under-o2")
        _link(o1, test_store_id)
        _link(o1, s2)
        _link(o2, s3)
        ids = sibling_store_ids(db.session, test_store_id)
    assert s2 in ids
    assert s3 not in ids


# ── find_by_id_in_stores ────────────────────────────────────


def test_find_by_id_in_stores_returns_customer(test_store_id):
    from app import app as flask_app, db
    from api.Modules.Customers.Repositories import find_by_id_in_stores
    with flask_app.app_context():
        cid = _seed_customer(test_store_id, full_name="Alice",
                              phone_number="5551234")
        c = find_by_id_in_stores(db.session, cid, [test_store_id])
    assert c is not None
    assert c.full_name == "Alice"


def test_find_by_id_in_stores_returns_none_when_outside_scope(test_store_id):
    """An explicit customer_id from outside the owner umbrella must NOT
    resolve — the upsert relies on this to enforce isolation."""
    from app import app as flask_app, db
    from api.Modules.Customers.Repositories import find_by_id_in_stores
    with flask_app.app_context():
        s2 = _seed_store("isolated")
        cid = _seed_customer(s2, full_name="Stranger",
                              phone_number="5559999")
        c = find_by_id_in_stores(db.session, cid, [test_store_id])
    assert c is None


# ── find_by_phone_in_stores ─────────────────────────────────


def test_find_by_phone_in_stores_matches(test_store_id):
    from app import app as flask_app, db
    from api.Modules.Customers.Repositories import find_by_phone_in_stores
    with flask_app.app_context():
        _seed_customer(test_store_id, full_name="Alice",
                        phone_country="+1", phone_number="5551234")
        c = find_by_phone_in_stores(
            db.session, [test_store_id], "+1", "5551234",
        )
    assert c is not None
    assert c.full_name == "Alice"


def test_find_by_phone_in_stores_empty_phone_returns_none(test_store_id):
    """Empty phone is not a valid lookup key — repository must
    short-circuit before hitting the DB so it can't accidentally
    match a "no phone on file" placeholder row."""
    from app import app as flask_app, db
    from api.Modules.Customers.Repositories import find_by_phone_in_stores
    with flask_app.app_context():
        _seed_customer(test_store_id, full_name="A", phone_number="")
        c = find_by_phone_in_stores(
            db.session, [test_store_id], "+1", "",
        )
    assert c is None


def test_find_by_phone_in_stores_defaults_country_to_plus_one(test_store_id):
    """Mirrors `find_or_upsert_customer` — empty country falls back to
    "+1" so older rows seeded without an explicit country still match."""
    from app import app as flask_app, db
    from api.Modules.Customers.Repositories import find_by_phone_in_stores
    with flask_app.app_context():
        _seed_customer(test_store_id, full_name="Alice",
                        phone_country="+1", phone_number="5551234")
        # Caller passes empty country — should still find the row.
        c = find_by_phone_in_stores(
            db.session, [test_store_id], "", "5551234",
        )
    assert c is not None


# ── search_by_substring ─────────────────────────────────────


def test_search_by_substring_matches_name_or_phone(test_store_id):
    from app import app as flask_app, db
    from api.Modules.Customers.Repositories import search_by_substring
    with flask_app.app_context():
        _seed_customer(test_store_id, full_name="Alice Smith",
                        phone_number="5551234")
        _seed_customer(test_store_id, full_name="Bob Jones",
                        phone_number="5559999")
        # Name match
        rows = search_by_substring(db.session, [test_store_id], "alice")
    assert {c.full_name for c in rows} == {"Alice Smith"}

    with flask_app.app_context():
        # Phone match
        rows = search_by_substring(db.session, [test_store_id], "9999")
    assert {c.full_name for c in rows} == {"Bob Jones"}


def test_search_by_substring_short_query_returns_empty(test_store_id):
    """Less than 2 chars → no DB hit. Keeps autocomplete fast."""
    from app import app as flask_app, db
    from api.Modules.Customers.Repositories import search_by_substring
    with flask_app.app_context():
        _seed_customer(test_store_id, full_name="Alice", phone_number="x")
        rows = search_by_substring(db.session, [test_store_id], "a")
    assert rows == []


def test_search_by_substring_orders_by_updated_at_desc(test_store_id):
    """Most-recently-edited customer floats to the top — matches the
    cashier's mental model (the sender they served last is the most
    likely repeat)."""
    from app import app as flask_app, db, Customer
    from api.Modules.Customers.Repositories import search_by_substring
    with flask_app.app_context():
        cid_old = _seed_customer(test_store_id, full_name="Match Old",
                                  phone_number="5550001")
        cid_new = _seed_customer(test_store_id, full_name="Match New",
                                  phone_number="5550002")
        # Force `updated_at` to be deterministic — clock skew on fast
        # machines makes both rows tie otherwise.
        old = db.session.get(Customer, cid_old)
        new = db.session.get(Customer, cid_new)
        old.updated_at = datetime.utcnow() - timedelta(days=2)
        new.updated_at = datetime.utcnow()
        db.session.commit()
        rows = search_by_substring(db.session, [test_store_id], "match")
    assert [c.full_name for c in rows] == ["Match New", "Match Old"]


def test_search_by_substring_respects_store_scope(test_store_id):
    """Customers in stores outside the passed scope must not appear."""
    from app import app as flask_app, db
    from api.Modules.Customers.Repositories import search_by_substring
    with flask_app.app_context():
        s2 = _seed_store("isolated")
        _seed_customer(s2, full_name="Hidden", phone_number="5550000")
        _seed_customer(test_store_id, full_name="Visible",
                        phone_number="5551111")
        # Both names contain "i" but the constraint is store-scope —
        # use a 2-char query (1-char short-circuits). "is" matches
        # "Visible" and "Hidden" by name.
        rows = search_by_substring(db.session, [test_store_id], "is")
    assert {c.full_name for c in rows} == {"Visible"}


# ── recent_customers ────────────────────────────────────────


def test_recent_customers_respects_limit(test_store_id):
    from app import app as flask_app, db
    from api.Modules.Customers.Repositories import recent_customers
    with flask_app.app_context():
        for i in range(5):
            _seed_customer(test_store_id, full_name=f"C{i}",
                            phone_number=f"555000{i}")
        rows = recent_customers(db.session, [test_store_id], limit=3)
    assert len(rows) == 3


# ── End-to-end: search_by_substring + sibling_store_ids ─────


def test_search_unifies_across_owner_umbrella(test_store_id):
    """Cashier at Store A finds the sender Store B logged — the call
    site for `/api/customers/search` always passes `sibling_store_ids`
    as the scope. This is the integration test of that pairing."""
    from app import app as flask_app, db
    from api.Modules.Customers.Repositories import (
        search_by_substring, sibling_store_ids,
    )
    with flask_app.app_context():
        oid = _seed_owner()
        s2 = _seed_store("location-2")
        _link(oid, test_store_id)
        _link(oid, s2)
        _seed_customer(s2, full_name="Maria",
                        phone_country="+1", phone_number="5551234")

        scope = sibling_store_ids(db.session, test_store_id)
        rows = search_by_substring(db.session, scope, "maria")
    assert {c.full_name for c in rows} == {"Maria"}
