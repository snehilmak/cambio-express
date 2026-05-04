"""Tests for the customer dedupe + recent-recipients API enhancements.

The /api/customers/search endpoint now returns a {matches, suggestions}
envelope. Suggestions are fuzzy near-misses (Levenshtein-style ratio via
difflib.SequenceMatcher) — they catch the "Maria Gonzales vs Maria
Gonzalez" duplicate-creation case where an exact substring search misses.

The new /api/customers/<id>/recent-recipients endpoint powers the
chip strip above the recipient_name input on the transfer form.
"""
import json
from datetime import date


def _admin_login(client, store_id):
    from app import User, Store, db
    with client.application.app_context():
        u = User.query.filter_by(store_id=store_id, role="admin").first()
        uid = u.id
        s = db.session.get(Store, store_id)
        s.plan = "pro"
        db.session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "admin"
        sess["store_id"] = store_id


def _make_customer(client, store_id, *, full_name, phone="5551234"):
    from app import Customer, db
    with client.application.app_context():
        c = Customer(store_id=store_id, full_name=full_name,
                     phone_country="+1", phone_number=phone)
        db.session.add(c); db.session.commit()
        return c.id


def _make_transfer(client, store_id, *, customer_id, recipient_name,
                    recipient_country="MX", recipient_phone="",
                    days_ago=0):
    from app import Transfer, db
    with client.application.app_context():
        t = Transfer(
            store_id=store_id, customer_id=customer_id,
            send_date=date.today(),
            sender_name="Sender", recipient_name=recipient_name,
            country=recipient_country, recipient_phone=recipient_phone,
            confirm_number=f"X{days_ago}", company="Intermex",
            send_amount=100.0, fee=2.0, federal_tax=1.0,
            status="Sent",
        )
        db.session.add(t); db.session.commit()
        return t.id


# ── Search envelope ──────────────────────────────────────────


def test_search_returns_envelope_shape(client, test_store_id):
    _admin_login(client, test_store_id)
    _make_customer(client, test_store_id, full_name="Alice Smith")
    resp = client.get("/api/customers/search?q=Alice")
    assert resp.status_code == 200
    payload = json.loads(resp.data)
    assert "matches" in payload
    assert "suggestions" in payload
    assert isinstance(payload["matches"], list)
    assert isinstance(payload["suggestions"], list)
    # Direct match found.
    assert any("Alice" in m.get("full_name", "") for m in payload["matches"])


def test_search_suggestions_catch_fuzzy_near_miss(client, test_store_id):
    """Typing a misspelled name should turn up the existing record as
    a suggestion, not nothing."""
    _admin_login(client, test_store_id)
    _make_customer(client, test_store_id, full_name="Maria Gonzalez")
    resp = client.get("/api/customers/search?q=Maria%20Gonzales")  # mis-spelled
    payload = json.loads(resp.data)
    # No exact-substring match (Gonzales != Gonzalez).
    assert payload["matches"] == []
    # Fuzzy suggestion picks up the real record.
    assert len(payload["suggestions"]) >= 1
    assert any("Gonzalez" in s.get("full_name", "")
               for s in payload["suggestions"])


def test_search_suggestions_skip_when_query_too_short(client, test_store_id):
    """4-char minimum on the suggestion path so single-letter queries
    don't trigger expensive fuzzy ranking."""
    _admin_login(client, test_store_id)
    _make_customer(client, test_store_id, full_name="Maria Gonzalez")
    resp = client.get("/api/customers/search?q=Mar")
    payload = json.loads(resp.data)
    # Substring matches still work.
    assert len(payload["matches"]) >= 1
    # No suggestions because q is < 4 chars.
    assert payload["suggestions"] == []


def test_search_no_duplicate_between_matches_and_suggestions(client, test_store_id):
    """A row that exact-matches must not also appear in the suggestion
    list — the UI would render it twice."""
    _admin_login(client, test_store_id)
    _make_customer(client, test_store_id, full_name="Alice Smith")
    resp = client.get("/api/customers/search?q=Alice")
    payload = json.loads(resp.data)
    match_ids = {m["id"] for m in payload["matches"]}
    suggest_ids = {s["id"] for s in payload["suggestions"]}
    assert match_ids.isdisjoint(suggest_ids)


# ── Recent recipients ────────────────────────────────────────


def test_recent_recipients_returns_distinct_recent(client, test_store_id):
    _admin_login(client, test_store_id)
    cid = _make_customer(client, test_store_id, full_name="Carlos Sender")
    _make_transfer(client, test_store_id, customer_id=cid,
                    recipient_name="Maria Recipient",
                    recipient_country="MX", recipient_phone="9991111")
    _make_transfer(client, test_store_id, customer_id=cid,
                    recipient_name="Pedro Recipient",
                    recipient_country="GT", recipient_phone="9992222")
    # Same recipient twice — should dedupe.
    _make_transfer(client, test_store_id, customer_id=cid,
                    recipient_name="Maria Recipient",
                    recipient_country="MX", recipient_phone="9991111")

    resp = client.get(f"/api/customers/{cid}/recent-recipients")
    assert resp.status_code == 200
    rows = json.loads(resp.data)
    names = [r["name"] for r in rows]
    assert "Maria Recipient" in names
    assert "Pedro Recipient" in names
    # Distinct — Maria appears once even though there are two transfers.
    assert names.count("Maria Recipient") == 1


def test_recent_recipients_empty_for_unknown_customer(client, test_store_id):
    _admin_login(client, test_store_id)
    resp = client.get("/api/customers/999999/recent-recipients")
    assert resp.status_code == 200
    assert json.loads(resp.data) == []


def test_recent_recipients_excludes_canceled(client, test_store_id):
    """Canceled / Rejected transfers' recipients shouldn't show up — the
    sender isn't going to retry sending to a canceled recipient."""
    _admin_login(client, test_store_id)
    cid = _make_customer(client, test_store_id, full_name="Test Sender")
    from app import Transfer, db
    with client.application.app_context():
        t = Transfer(
            store_id=test_store_id, customer_id=cid,
            send_date=date.today(),
            sender_name="Test Sender", recipient_name="Canceled Recipient",
            country="MX", confirm_number="C1", company="Intermex",
            send_amount=100.0, fee=0, federal_tax=0,
            status="Canceled",
        )
        db.session.add(t); db.session.commit()
    resp = client.get(f"/api/customers/{cid}/recent-recipients")
    rows = json.loads(resp.data)
    assert all(r["name"] != "Canceled Recipient" for r in rows)


def test_recent_recipients_blocked_for_other_store_customer(client, test_store_id):
    """A customer from an unrelated store can't be queried — scoped to
    the umbrella, never to the whole platform."""
    _admin_login(client, test_store_id)
    from app import Store, Customer, db
    with client.application.app_context():
        other_store = Store(name="other", slug="other-store",
                            plan="trial", is_active=True)
        db.session.add(other_store); db.session.commit()
        c = Customer(store_id=other_store.id, full_name="Stranger")
        db.session.add(c); db.session.commit()
        cid = c.id
    resp = client.get(f"/api/customers/{cid}/recent-recipients")
    assert resp.status_code == 200
    assert json.loads(resp.data) == []
