"""TV pair-code system — TV-initiated flow.

The Fire TV companion app calls POST /api/tv-pair/init on launch and
displays the returned 6-char code. The operator types that code into
/tv-display, which POSTs to /tv-display/claim. The Fire TV polls
GET /api/tv-pair/status to discover the claim and load its per-
device URL.

These tests pin the security-relevant invariants:
  - codes are single-use (a claimed code can never be claimed again),
  - device_tokens are stable from /init through claim (no rotation),
  - claim is gated on the tv_display addon being active,
  - claiming a new code revokes any prior active TVPairing on the
    same display (one Fire TV per subscription),
  - failure modes return indistinguishable responses (no oracle for
    brute force).
"""
from datetime import datetime, timedelta

from app import (
    db, User, Store, TVDisplay, TVPairing, TVPendingPair,
    _PAIR_CODE_ALPHABET, _PAIR_CODE_LIFETIME,
)


# ── Helpers ────────────────────────────────────────────────────

def _activate_addon(client, store_id):
    with client.application.app_context():
        s = db.session.get(Store, store_id)
        s.plan = "basic"
        s.addons = "tv_display"
        db.session.commit()


def _ensure_display(client):
    """Land on /tv-display once so _ensure_tv_display creates the row."""
    client.get("/tv-display")
    with client.application.app_context():
        return TVDisplay.query.first()


def _init(client, **payload):
    """POST /api/tv-pair/init. Returns the parsed JSON body."""
    return client.post("/api/tv-pair/init", json=payload).get_json()


def _claim(client, code, follow_redirects=False):
    """Admin-side claim. Form POST, returns the response."""
    return client.post("/tv-display/claim", data={"code": code},
                        follow_redirects=follow_redirects)


# ── /api/tv-pair/init ──────────────────────────────────────────

def test_init_returns_code_and_device_token(client):
    """Public endpoint — no auth required. Returns a 6-char code in
    the safe alphabet plus a stable device_token the Fire TV stores
    for the lifetime of this pairing attempt."""
    body = _init(client)
    assert "code" in body
    assert "device_token" in body
    assert "expires_at" in body
    assert "ttl_seconds" in body
    assert len(body["code"]) == 6
    assert all(c in _PAIR_CODE_ALPHABET for c in body["code"])
    # 32-byte URL-safe random base64 → 32+ chars on the wire.
    assert len(body["device_token"]) >= 32
    assert body["ttl_seconds"] == int(_PAIR_CODE_LIFETIME.total_seconds())


def test_init_persists_pending_pair_row(client):
    body = _init(client)
    with client.application.app_context():
        pending = TVPendingPair.query.filter_by(code=body["code"]).first()
        assert pending is not None
        assert pending.device_token == body["device_token"]
        assert pending.claimed_at is None
        assert pending.expires_at > datetime.utcnow()


def test_init_accepts_optional_device_label(client):
    body = _init(client, device_label="Fire TV — Stick 4K Max")
    with client.application.app_context():
        pending = TVPendingPair.query.filter_by(code=body["code"]).first()
        assert pending.device_label == "Fire TV — Stick 4K Max"


def test_init_each_call_mints_distinct_code_and_token(client):
    """Two Fire TVs opening the app must get different codes AND
    different tokens; otherwise a clever-but-misguided dual-launch
    could accidentally double-pair."""
    a = _init(client)
    b = _init(client)
    assert a["code"] != b["code"]
    assert a["device_token"] != b["device_token"]


# ── /api/tv-pair/status ────────────────────────────────────────

def test_status_pending_for_fresh_token(client):
    body = _init(client)
    resp = client.get("/api/tv-pair/status",
                       query_string={"token": body["device_token"]})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "pending"
    assert data["code"] == body["code"]


def test_status_expired_for_unknown_token(client):
    """Unknown tokens collapse into "expired" so the Fire TV's poll
    loop has a single recovery path: re-init."""
    resp = client.get("/api/tv-pair/status", query_string={"token": "bogus"})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "expired"


def test_status_expired_when_pending_row_aged_out(client):
    body = _init(client)
    with client.application.app_context():
        p = TVPendingPair.query.filter_by(code=body["code"]).first()
        p.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()
    resp = client.get("/api/tv-pair/status",
                       query_string={"token": body["device_token"]})
    assert resp.get_json()["status"] == "expired"


def test_status_claimed_after_admin_claims_the_code(client, logged_in_client, test_store_id):
    """End-to-end happy path: TV initiates, admin claims, TV's poll
    flips to "claimed" and gets a /tv/device/<token> URL."""
    _activate_addon(logged_in_client, test_store_id)
    _ensure_display(logged_in_client)
    body = _init(client)
    # Admin claims it.
    resp = _claim(logged_in_client, body["code"])
    assert resp.status_code == 302  # flash + redirect
    # TV's next poll sees "claimed".
    poll = client.get("/api/tv-pair/status",
                       query_string={"token": body["device_token"]}).get_json()
    assert poll["status"] == "claimed"
    assert poll["display_url"].endswith("/tv/device/" + body["device_token"])
    assert poll["store_name"] == "Test Store"
    assert "title" in poll


# ── /tv-display/claim (admin side) ─────────────────────────────

def test_claim_blocked_when_addon_off(logged_in_client, client):
    """Claim requires the addon — same gate as the rest of /tv-display."""
    body = _init(client)
    resp = logged_in_client.post("/tv-display/claim",
                                   data={"code": body["code"]})
    assert resp.status_code == 302
    assert "/admin/subscription" in resp.headers["Location"]
    # Pending row still unclaimed.
    with logged_in_client.application.app_context():
        p = TVPendingPair.query.filter_by(code=body["code"]).first()
        assert p.claimed_at is None


def test_claim_creates_tvpairing_reusing_device_token(client, logged_in_client, test_store_id):
    """The device_token from the pending row is COPIED into the new
    TVPairing — the Fire TV stores its token once at /init time and
    never sees a rotation."""
    _activate_addon(logged_in_client, test_store_id)
    _ensure_display(logged_in_client)
    body = _init(client)
    _claim(logged_in_client, body["code"])
    with client.application.app_context():
        pairing = TVPairing.query.filter_by(
            device_token=body["device_token"]).first()
        assert pairing is not None
        assert pairing.revoked_at is None
        # Pending row is marked claimed and links back to the pairing.
        pending = TVPendingPair.query.filter_by(code=body["code"]).first()
        assert pending.claimed_at is not None
        assert pending.claimed_pairing_id == pairing.id


def test_claim_strips_whitespace_and_lowercase(client, logged_in_client, test_store_id):
    """Operator pastes 'abc - 234' from a Fire TV that renders the
    code with spacing — server normalizes the same way the client
    JS does."""
    _activate_addon(logged_in_client, test_store_id)
    _ensure_display(logged_in_client)
    body = _init(client)
    munged = body["code"][:3].lower() + " - " + body["code"][3:].lower()
    resp = _claim(logged_in_client, munged)
    assert resp.status_code == 302
    with client.application.app_context():
        assert TVPairing.query.filter_by(
            device_token=body["device_token"]).first() is not None


def test_claim_is_single_use(client, logged_in_client, test_store_id):
    """*** Anti-misuse rule: a code claimed once cannot be claimed
    again. *** Even by the same admin. The pending row stays around
    for audit but its claimed_at is non-NULL forever after."""
    _activate_addon(logged_in_client, test_store_id)
    _ensure_display(logged_in_client)
    body = _init(client)
    first = _claim(logged_in_client, body["code"], follow_redirects=True)
    second = _claim(logged_in_client, body["code"], follow_redirects=True)
    assert first.status_code == 200  # 302 → 200 after follow
    assert second.status_code == 200
    # Second claim's flash carries the friendly error.
    assert b"Code not found or expired" in second.data


def test_claim_404s_message_for_unknown_code(logged_in_client, test_store_id):
    """All failure modes flash the same vague message so brute-force
    probes can't tell unknown vs expired vs already-claimed apart."""
    _activate_addon(logged_in_client, test_store_id)
    _ensure_display(logged_in_client)
    resp = logged_in_client.post("/tv-display/claim",
                                   data={"code": "ZZZZZZ"},
                                   follow_redirects=True)
    assert b"Code not found or expired" in resp.data


def test_claim_rejects_short_code(logged_in_client, test_store_id):
    _activate_addon(logged_in_client, test_store_id)
    _ensure_display(logged_in_client)
    resp = logged_in_client.post("/tv-display/claim",
                                   data={"code": "AB"},
                                   follow_redirects=True)
    assert b"6-character code" in resp.data


def test_claim_revokes_prior_pairing(client, logged_in_client, test_store_id):
    """*** Operator concern: pairing a NEW Fire TV must immediately
    disable the OLD one. *** Single-active-pairing per display
    enforces "one $5 sub = one Fire TV at a time."""
    _activate_addon(logged_in_client, test_store_id)
    _ensure_display(logged_in_client)
    # Pair Fire TV #1.
    a = _init(client)
    _claim(logged_in_client, a["code"])
    # Old TV's URL is live.
    assert client.get("/tv/device/" + a["device_token"]).status_code == 200
    # Pair Fire TV #2 (separate /init = separate pending row + token).
    b = _init(client)
    _claim(logged_in_client, b["code"])
    with client.application.app_context():
        old = TVPairing.query.filter_by(device_token=a["device_token"]).first()
        new = TVPairing.query.filter_by(device_token=b["device_token"]).first()
        assert old.revoked_at is not None
        assert new.revoked_at is None
    # Old TV's URL now 404s; new TV's URL works.
    assert client.get("/tv/device/" + a["device_token"]).status_code == 404
    assert client.get("/tv/device/" + b["device_token"]).status_code == 200
    # And the OLD TV's status poll now shows "expired" (its pending
    # row long since claimed; its pairing revoked).
    poll = client.get("/api/tv-pair/status",
                       query_string={"token": a["device_token"]}).get_json()
    assert poll["status"] == "expired"


def test_claim_404s_when_pending_already_claimed(client, logged_in_client, test_store_id):
    """Two admins racing to claim the same code (e.g. shared
    superadmin shoulder-surfing): only one wins, the other gets the
    same vague error."""
    _activate_addon(logged_in_client, test_store_id)
    _ensure_display(logged_in_client)
    body = _init(client)
    _claim(logged_in_client, body["code"])
    # Re-claim — already-claimed lands as the same error as unknown.
    resp = logged_in_client.post("/tv-display/claim",
                                   data={"code": body["code"]},
                                   follow_redirects=True)
    assert b"Code not found or expired" in resp.data


# ── /tv/device/<device_token> render path ──────────────────────

def _populate_one_country(client, store_id):
    _activate_addon(client, store_id)
    client.get("/tv-display")
    client.post("/tv-display/countries/new", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "Maxi, Vigo",
    })
    with client.application.app_context():
        from app import TVDisplayCountry
        country_id = TVDisplayCountry.query.first().id
    client.post(f"/tv-display/countries/{country_id}", data={
        "country_name": "Mexico", "country_code": "MX",
        "mt_companies": "Maxi, Vigo",
        "new_bank_name": "Bancomer",
    })


def test_device_url_renders_full_board(client, logged_in_client, test_store_id):
    _populate_one_country(logged_in_client, test_store_id)
    body = _init(client)
    _claim(logged_in_client, body["code"])
    resp = client.get("/tv/device/" + body["device_token"])
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Mexico" in html
    assert "Bancomer" in html
    assert "design-tokens.css" in html


def test_device_url_404s_after_being_superseded(client, logged_in_client, test_store_id):
    _activate_addon(logged_in_client, test_store_id)
    _ensure_display(logged_in_client)
    a = _init(client)
    _claim(logged_in_client, a["code"])
    b = _init(client)
    _claim(logged_in_client, b["code"])
    assert client.get("/tv/device/" + a["device_token"]).status_code == 404


def test_device_url_404s_when_addon_revoked(client, logged_in_client, test_store_id):
    _activate_addon(logged_in_client, test_store_id)
    _ensure_display(logged_in_client)
    body = _init(client)
    _claim(logged_in_client, body["code"])
    # Yank the addon.
    with logged_in_client.application.app_context():
        s = db.session.get(Store, test_store_id)
        s.addons = ""; db.session.commit()
    assert client.get("/tv/device/" + body["device_token"]).status_code == 404


def test_device_url_bumps_last_seen_at(client, logged_in_client, test_store_id):
    _activate_addon(logged_in_client, test_store_id)
    _ensure_display(logged_in_client)
    body = _init(client)
    _claim(logged_in_client, body["code"])
    with client.application.app_context():
        TVPairing.query.filter_by(
            device_token=body["device_token"]
        ).update({"last_seen_at": datetime.utcnow() - timedelta(minutes=5)})
        db.session.commit()
    client.get("/tv/device/" + body["device_token"])
    with client.application.app_context():
        after = TVPairing.query.filter_by(
            device_token=body["device_token"]).first().last_seen_at
        assert after > (datetime.utcnow() - timedelta(minutes=1))


def test_legacy_public_url_still_works_for_tablets(client, logged_in_client, test_store_id):
    """The user explicitly asked to keep /tv/<public_token> working
    for operators running tablets/Chromecasts. Verify the inverted
    pair flow doesn't break that path."""
    _populate_one_country(logged_in_client, test_store_id)
    with client.application.app_context():
        token = TVDisplay.query.first().public_token
    assert client.get("/tv/" + token).status_code == 200
    # And that a paired-then-revoked Fire TV doesn't affect it.
    a = _init(client)
    _claim(logged_in_client, a["code"])
    b = _init(client)
    _claim(logged_in_client, b["code"])  # supersede
    assert client.get("/tv/" + token).status_code == 200


# ── Employee access ────────────────────────────────────────────

def test_employee_can_claim_a_code(client, test_store_id):
    """v1 grants employees /tv-display access — pairing is daily-
    operations work, not back-office."""
    _activate_addon(client, test_store_id)
    from tests.conftest import make_employee_client
    emp = make_employee_client(test_store_id)
    emp.get("/tv-display")  # ensure display
    body = _init(client)
    resp = emp.post("/tv-display/claim", data={"code": body["code"]})
    assert resp.status_code == 302
    with client.application.app_context():
        assert TVPairing.query.filter_by(
            device_token=body["device_token"]).first() is not None


# ── Alphabet sanity ────────────────────────────────────────────

def test_pair_code_alphabet_excludes_ambiguous_chars():
    """Hand-rolled the alphabet so nobody has to read O vs 0 or I vs 1
    on a Fire TV from across a counter."""
    for c in "O0I1LB8":
        assert c not in _PAIR_CODE_ALPHABET
    # 21 unambiguous uppercase letters + 6 unambiguous digits = 27.
    assert len(set(_PAIR_CODE_ALPHABET)) == 27
