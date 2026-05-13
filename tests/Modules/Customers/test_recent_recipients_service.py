"""Unit tests for Customers.Services.list_recent_recipients (PR 38)."""
from datetime import date, timedelta


def _seed_customer(store_id, *, full_name="C", phone_number=""):
    from api.Modules.Customers.Models import Customer
    from app import db
    c = Customer(
        store_id=store_id, full_name=full_name,
        phone_country="+1", phone_number=phone_number,
    )
    db.session.add(c); db.session.commit()
    return c.id


def _seed_transfer(store_id, customer_id, *, recipient_name="R",
                    country="MX", phone="", send_date=None,
                    status="Sent", confirm_number=None):
    from api.Modules.Transfers.Models import Transfer
    from app import db
    t = Transfer(
        store_id=store_id, customer_id=customer_id,
        send_date=send_date or date.today(),
        company="Intermex", service_type="Money Transfer",
        sender_name="S", recipient_name=recipient_name,
        country=country, recipient_phone=phone,
        confirm_number=confirm_number or f"X-{recipient_name}",
        send_amount=100.0, fee=2.0, federal_tax=1.0,
        status=status,
    )
    db.session.add(t); db.session.commit()
    return t.id


def _seed_owner(username="owner-rr@x.com"):
    from api.Modules.Tenancy.Models import User
    from app import db
    u = User(username=username, full_name="Owner", role="owner")
    u.set_password("p")
    db.session.add(u); db.session.commit()
    return u.id


def _seed_store(slug):
    from api.Modules.Tenancy.Models import Store
    from app import db
    s = Store(name="X", slug=slug, email=f"{slug}@x.com", plan="trial")
    db.session.add(s); db.session.commit()
    return s.id


def _link(owner_id, store_id):
    from api.Modules.Tenancy.Models import StoreOwnerLink
    from app import db
    db.session.add(StoreOwnerLink(owner_id=owner_id, store_id=store_id))
    db.session.commit()


# ── list_recent_recipients ──────────────────────────────────


def test_returns_distinct_recipients_in_recency_order(test_store_id):
    from app import app as flask_app, db
    from api.Modules.Customers.Services import list_recent_recipients
    today = date.today()
    yesterday = today - timedelta(days=1)
    last_week = today - timedelta(days=7)
    with flask_app.app_context():
        cid = _seed_customer(test_store_id, full_name="Sender")
        # Three distinct recipients on three distinct dates; one
        # duplicate to test "distinct".
        _seed_transfer(test_store_id, cid, recipient_name="Alice",
                        send_date=last_week, confirm_number="X1")
        _seed_transfer(test_store_id, cid, recipient_name="Bob",
                        send_date=yesterday, confirm_number="X2")
        _seed_transfer(test_store_id, cid, recipient_name="Carol",
                        send_date=today, confirm_number="X3")
        # Duplicate: same name/country/phone shouldn't double up
        _seed_transfer(test_store_id, cid, recipient_name="Carol",
                        send_date=today - timedelta(days=2),
                        confirm_number="X4")
        rows = list_recent_recipients(
            db.session, cid, viewer_store_id=test_store_id,
        )
    names = [r.name for r in rows]
    # Recency desc: Carol (today), Bob (yesterday), Alice (last_week)
    assert names == ["Carol", "Bob", "Alice"]


def test_excludes_canceled_and_rejected_status(test_store_id):
    """Canceled/Rejected transfers' recipients aren't ones the sender
    will reuse."""
    from app import app as flask_app, db
    from api.Modules.Customers.Services import list_recent_recipients
    today = date.today()
    with flask_app.app_context():
        cid = _seed_customer(test_store_id)
        _seed_transfer(test_store_id, cid, recipient_name="Sent",
                        send_date=today, status="Sent",
                        confirm_number="X-S")
        _seed_transfer(test_store_id, cid, recipient_name="Cancelled",
                        send_date=today, status="Canceled",
                        confirm_number="X-C")
        _seed_transfer(test_store_id, cid, recipient_name="Rejected",
                        send_date=today, status="Rejected",
                        confirm_number="X-R")
        rows = list_recent_recipients(
            db.session, cid, viewer_store_id=test_store_id,
        )
    names = {r.name for r in rows}
    assert names == {"Sent"}


def test_excludes_empty_recipient_name(test_store_id):
    from app import app as flask_app, db
    from api.Modules.Customers.Services import list_recent_recipients
    today = date.today()
    with flask_app.app_context():
        cid = _seed_customer(test_store_id)
        _seed_transfer(test_store_id, cid, recipient_name="Real",
                        send_date=today, confirm_number="X-R")
        _seed_transfer(test_store_id, cid, recipient_name="",
                        send_date=today, confirm_number="X-empty")
        rows = list_recent_recipients(
            db.session, cid, viewer_store_id=test_store_id,
        )
    assert {r.name for r in rows} == {"Real"}


def test_returns_empty_when_customer_outside_umbrella(test_store_id):
    """Cross-umbrella customer lookup returns empty (matches the
    legacy "404 → empty list" UX) — no leakage to a stranger
    store's chip data."""
    from app import app as flask_app, db
    from api.Modules.Customers.Services import list_recent_recipients
    today = date.today()
    with flask_app.app_context():
        s2 = _seed_store("stranger-rr")
        cid = _seed_customer(s2)
        _seed_transfer(s2, cid, recipient_name="Hidden",
                        send_date=today, confirm_number="X-H")
        rows = list_recent_recipients(
            db.session, cid, viewer_store_id=test_store_id,
        )
    assert rows == []


def test_finds_in_owner_umbrella(test_store_id):
    """Customer + their transfers at sibling store are reachable
    when the viewer is at the original store."""
    from app import app as flask_app, db
    from api.Modules.Customers.Services import list_recent_recipients
    today = date.today()
    with flask_app.app_context():
        oid = _seed_owner()
        s2 = _seed_store("loc-rr")
        _link(oid, test_store_id)
        _link(oid, s2)
        cid = _seed_customer(s2)
        _seed_transfer(s2, cid, recipient_name="Maria",
                        send_date=today, confirm_number="X-M")
        rows = list_recent_recipients(
            db.session, cid, viewer_store_id=test_store_id,
        )
    assert {r.name for r in rows} == {"Maria"}


def test_returns_empty_for_unknown_customer(test_store_id):
    from app import app as flask_app, db
    from api.Modules.Customers.Services import list_recent_recipients
    with flask_app.app_context():
        rows = list_recent_recipients(
            db.session, 99999, viewer_store_id=test_store_id,
        )
    assert rows == []


def test_respects_limit(test_store_id):
    from app import app as flask_app, db
    from api.Modules.Customers.Services import list_recent_recipients
    today = date.today()
    with flask_app.app_context():
        cid = _seed_customer(test_store_id)
        for i in range(8):
            _seed_transfer(
                test_store_id, cid, recipient_name=f"R{i}",
                send_date=today - timedelta(days=i),
                confirm_number=f"X-{i}",
            )
        rows = list_recent_recipients(
            db.session, cid, viewer_store_id=test_store_id, limit=3,
        )
    assert len(rows) == 3


def test_recent_recipient_to_dict_shape(test_store_id):
    """Wire shape matches the legacy JSON the frontend already
    consumes: keys = name / country / phone, all strings."""
    from app import app as flask_app, db
    from api.Modules.Customers.Services import list_recent_recipients
    today = date.today()
    with flask_app.app_context():
        cid = _seed_customer(test_store_id)
        _seed_transfer(
            test_store_id, cid, recipient_name="Maria",
            country="GT", phone="+5023334444",
            send_date=today, confirm_number="X-M",
        )
        rows = list_recent_recipients(
            db.session, cid, viewer_store_id=test_store_id,
        )
        d = rows[0].to_dict()
    assert d == {"name": "Maria", "country": "GT", "phone": "+5023334444"}
