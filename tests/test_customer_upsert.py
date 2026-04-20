"""Tests for find_or_upsert_customer() and sibling_store_ids() (CLAUDE.md #5).

A multi-store owner should see a unified customer list across their
portfolio (owner umbrella). Lookup priority:
  1. explicit customer_id — accepted only if the target lives in a sibling store;
  2. (phone_country, phone_number) across the sibling set;
  3. otherwise create a new record pinned to the current store.

Unrelated stores (no shared owner) must remain fully isolated.
"""
from datetime import date


def _make_store(name, slug, plan="basic"):
    from app import db, Store
    s = Store(name=name, slug=slug, email=f"{slug}@test.com", plan=plan)
    db.session.add(s); db.session.flush()
    return s


def _make_owner(username="owner1@example.com"):
    from app import db, User
    u = User(username=username, full_name="Owner One", role="owner",
             store_id=None)
    u.set_password("ownerpass!")
    db.session.add(u); db.session.flush()
    return u


def _link(owner, store):
    from app import db, StoreOwnerLink
    db.session.add(StoreOwnerLink(owner_id=owner.id, store_id=store.id))
    db.session.flush()


# ── sibling_store_ids ───────────────────────────────────────────────────────

def test_sibling_ids_solo_store_returns_itself(client):
    """Store with no owner links is its own sole sibling — not an empty list."""
    from app import sibling_store_ids, Store
    with client.application.app_context():
        sid = Store.query.filter_by(slug="test-store").one().id
        assert sibling_store_ids(sid) == [sid]


def test_sibling_ids_spans_all_stores_with_shared_owner(client):
    from app import db, sibling_store_ids
    with client.application.app_context():
        a = _make_store("A", "store-a")
        b = _make_store("B", "store-b")
        c = _make_store("C", "store-c")
        owner = _make_owner()
        _link(owner, a); _link(owner, b); _link(owner, c)
        db.session.commit()
        siblings = sibling_store_ids(a.id)
        assert set(siblings) == {a.id, b.id, c.id}


def test_sibling_ids_isolates_unrelated_stores(client):
    """Two owners with disjoint portfolios must never see each other's stores."""
    from app import db, sibling_store_ids
    with client.application.app_context():
        a = _make_store("A", "store-a"); b = _make_store("B", "store-b")
        x = _make_store("X", "store-x"); y = _make_store("Y", "store-y")
        o1 = _make_owner("owner1@test.com")
        o2 = _make_owner("owner2@test.com")
        _link(o1, a); _link(o1, b)
        _link(o2, x); _link(o2, y)
        db.session.commit()
        assert set(sibling_store_ids(a.id)) == {a.id, b.id}
        assert set(sibling_store_ids(x.id)) == {x.id, y.id}


def test_sibling_ids_merges_across_shared_owner(client):
    """If one owner sits in both A and B, A sees B — even if only owner2 is in X."""
    from app import db, sibling_store_ids
    with client.application.app_context():
        a = _make_store("A", "store-a"); b = _make_store("B", "store-b")
        x = _make_store("X", "store-x")
        o1 = _make_owner("owner1@test.com")
        o2 = _make_owner("owner2@test.com")
        _link(o1, a); _link(o1, b)
        _link(o2, b); _link(o2, x)
        db.session.commit()
        # Walking from A via o1 reaches B, and via B's o2 reaches X.
        # The function does one hop (direct owners of A), so A → {A, B}.
        # X has o2 only; o2 is in B too, so X → {X, B}.
        assert set(sibling_store_ids(a.id)) == {a.id, b.id}
        assert set(sibling_store_ids(x.id)) == {x.id, b.id}


# ── find_or_upsert_customer ─────────────────────────────────────────────────

def test_upsert_creates_new_customer_when_no_match(client):
    from app import db, Customer, find_or_upsert_customer, Store
    with client.application.app_context():
        sid = Store.query.filter_by(slug="test-store").one().id
        cust = find_or_upsert_customer(
            store_id=sid, full_name="Alice Alpha",
            phone_country="+1", phone_number="5550100",
            address="123 Main", dob=date(1990, 1, 1),
        )
        db.session.commit()
        assert cust.id is not None
        assert cust.store_id == sid
        assert cust.full_name == "Alice Alpha"
        assert cust.phone_number == "5550100"
        assert cust.address == "123 Main"
        assert cust.dob == date(1990, 1, 1)


def test_upsert_dedup_by_phone_within_same_store(client):
    """Same phone in same store => single Customer row, latest data wins."""
    from app import db, Customer, find_or_upsert_customer, Store
    with client.application.app_context():
        sid = Store.query.filter_by(slug="test-store").one().id
        c1 = find_or_upsert_customer(
            store_id=sid, full_name="Alice Old",
            phone_country="+1", phone_number="5550100",
            address="Old Address",
        )
        db.session.commit()
        c2 = find_or_upsert_customer(
            store_id=sid, full_name="Alice New",
            phone_country="+1", phone_number="5550100",
            address="New Address",
        )
        db.session.commit()
        assert c1.id == c2.id
        assert Customer.query.count() == 1
        # Newest values overwrite.
        assert c2.full_name == "Alice New"
        assert c2.address == "New Address"


def test_upsert_dedup_across_sibling_stores(client):
    """A cashier at store B finds the customer logged at store A (same owner)."""
    from app import db, Customer, find_or_upsert_customer
    with client.application.app_context():
        a = _make_store("A", "store-a"); b = _make_store("B", "store-b")
        owner = _make_owner()
        _link(owner, a); _link(owner, b)
        db.session.commit()
        # Log customer at A.
        c_at_a = find_or_upsert_customer(
            store_id=a.id, full_name="Bob Beta",
            phone_country="+1", phone_number="5550200",
        )
        db.session.commit()
        # Look up at B — should return the same row, still pinned to A.
        c_at_b = find_or_upsert_customer(
            store_id=b.id, full_name="Bob Beta Jr",
            phone_country="+1", phone_number="5550200",
        )
        db.session.commit()
        assert c_at_a.id == c_at_b.id
        # Customer stays pinned to its home store (A), not reassigned to B.
        assert c_at_b.store_id == a.id
        assert Customer.query.count() == 1


def test_upsert_isolation_between_unrelated_stores(client):
    """No shared owner => two separate Customer rows even with same phone."""
    from app import db, Customer, find_or_upsert_customer
    with client.application.app_context():
        a = _make_store("A", "store-a"); x = _make_store("X", "store-x")
        o1 = _make_owner("owner1@test.com")
        o2 = _make_owner("owner2@test.com")
        _link(o1, a); _link(o2, x)
        db.session.commit()
        find_or_upsert_customer(
            store_id=a.id, full_name="Phone Twin",
            phone_country="+1", phone_number="5550300",
        )
        find_or_upsert_customer(
            store_id=x.id, full_name="Phone Twin",
            phone_country="+1", phone_number="5550300",
        )
        db.session.commit()
        # Two rows — unrelated stores must not share customers.
        assert Customer.query.count() == 2
        store_ids = {c.store_id for c in Customer.query.all()}
        assert store_ids == {a.id, x.id}


def test_upsert_explicit_customer_id_from_sibling_accepted(client):
    from app import db, find_or_upsert_customer
    with client.application.app_context():
        a = _make_store("A", "store-a"); b = _make_store("B", "store-b")
        owner = _make_owner()
        _link(owner, a); _link(owner, b)
        db.session.commit()
        c_at_a = find_or_upsert_customer(
            store_id=a.id, full_name="Cara",
            phone_country="+1", phone_number="5550400",
        )
        db.session.commit()
        # Caller at B passes the sibling customer's id explicitly.
        c_at_b = find_or_upsert_customer(
            store_id=b.id, full_name="Cara Updated",
            phone_country="+1", phone_number="5550400",
            customer_id=c_at_a.id,
        )
        db.session.commit()
        assert c_at_b.id == c_at_a.id
        assert c_at_b.full_name == "Cara Updated"


def test_upsert_explicit_customer_id_from_unrelated_store_ignored(client):
    """Passing a Customer id from outside the umbrella must NOT reuse it.

    This is the fence that keeps unrelated stores from cross-reading each
    other's customers through a guessed id.
    """
    from app import db, Customer, find_or_upsert_customer
    with client.application.app_context():
        a = _make_store("A", "store-a"); x = _make_store("X", "store-x")
        o1 = _make_owner("owner1@test.com")
        o2 = _make_owner("owner2@test.com")
        _link(o1, a); _link(o2, x)
        db.session.commit()
        c_at_a = find_or_upsert_customer(
            store_id=a.id, full_name="Alice",
            phone_country="+1", phone_number="5550500",
        )
        db.session.commit()
        # Caller at X tries to claim customer a.id — must be rejected AND
        # a new customer must be created pinned to X (different phone so
        # phone-lookup doesn't salvage it either).
        c_at_x = find_or_upsert_customer(
            store_id=x.id, full_name="Alice Impostor",
            phone_country="+1", phone_number="5550599",
            customer_id=c_at_a.id,
        )
        db.session.commit()
        assert c_at_x.id != c_at_a.id
        assert c_at_x.store_id == x.id
        # The A-home customer must not have been mutated via the X call.
        refreshed_a = db.session.get(Customer, c_at_a.id)
        assert refreshed_a.full_name == "Alice"
        assert refreshed_a.store_id == a.id


def test_upsert_empty_fields_do_not_overwrite_stored_values(client):
    """Blank address/dob on a new visit must not wipe existing data."""
    from app import db, find_or_upsert_customer, Store
    with client.application.app_context():
        sid = Store.query.filter_by(slug="test-store").one().id
        find_or_upsert_customer(
            store_id=sid, full_name="Dana Delta",
            phone_country="+1", phone_number="5550600",
            address="456 Oak", dob=date(1985, 5, 5),
        )
        db.session.commit()
        # Returning visit with blank address/dob.
        c = find_or_upsert_customer(
            store_id=sid, full_name="Dana Delta",
            phone_country="+1", phone_number="5550600",
            address="", dob=None,
        )
        db.session.commit()
        assert c.address == "456 Oak"
        assert c.dob == date(1985, 5, 5)


def test_upsert_default_phone_country_is_plus_one(client):
    """Missing phone_country falls back to +1 for both the filter and the row."""
    from app import db, find_or_upsert_customer, Customer, Store
    with client.application.app_context():
        sid = Store.query.filter_by(slug="test-store").one().id
        c = find_or_upsert_customer(
            store_id=sid, full_name="Eli Echo",
            phone_country="", phone_number="5550700",
        )
        db.session.commit()
        assert c.phone_country == "+1"
        # Second lookup with explicit +1 must find the same row.
        c2 = find_or_upsert_customer(
            store_id=sid, full_name="Eli Echo",
            phone_country="+1", phone_number="5550700",
        )
        db.session.commit()
        assert c.id == c2.id
        assert Customer.query.count() == 1
