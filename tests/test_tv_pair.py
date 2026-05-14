"""TV pair-code system — TV-initiated flow.

The Fire TV companion app calls POST /api/tv-pair/init on launch and
displays the returned 6-char code. The operator types that code into
the React /app/tv-display, which POSTs to /api/v2/tv-display/claim.
The Fire TV polls GET /api/tv-pair/status to discover the claim and
load its per-device URL.

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

from api.Modules.TVDisplay.Models import TVDisplay, TVPairing, TVPendingPair
from api.Modules.TVDisplay.Services.pair_code import (
    PAIR_CODE_ALPHABET as _PAIR_CODE_ALPHABET,
    PAIR_CODE_LIFETIME as _PAIR_CODE_LIFETIME,
)
from api.Modules.Tenancy.Models import Store, User
from tests._app import db


# ── Helpers ────────────────────────────────────────────────────

def _activate_addon(client, store_id):
    with client.application.app_context():
        s = db.session.get(Store, store_id)
        s.plan = "basic"
        s.addons = "tv_display"
        db.session.commit()


def _admin_jwt(client, store_id, *, username="admin@test.com",
               password="testpass123!"):
    """Mint a Bearer JWT for an admin/employee via the SPA login. The
    /api/v2/tv-display/* write endpoints all require this dependency."""
    return client.post(
        "/api/v2/auth/login",
        json={"username": username, "password": password,
              "store_id": store_id},
    ).get_json()["access_token"]


def _ensure_display(client, store_id, jwt):
    """Land on the overview endpoint once so _ensure_display creates
    the TVDisplay row. Mirrors the legacy `_ensure_tv_display` lazy-
    create that the deleted /tv-display GET used to do."""
    client.get(
        "/api/v2/tv-display/overview",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    with client.application.app_context():
        return db.session.query(TVDisplay).filter_by(store_id=store_id).first()


def _init(client, **payload):
    """POST /api/tv-pair/init. Returns the parsed JSON body."""
    return client.post("/api/tv-pair/init", json=payload).get_json()


def _claim(client, code, jwt):
    """Admin-side claim via the new JSON endpoint. Returns the response.
    Caller passes a JWT minted from the same store the TV display
    belongs to."""
    return client.post(
        "/api/v2/tv-display/claim",
        json={"code": code},
        headers={"Authorization": f"Bearer {jwt}"},
    )


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
        pending = db.session.query(TVPendingPair).filter_by(code=body["code"]).first()
        assert pending is not None
        assert pending.device_token == body["device_token"]
        assert pending.claimed_at is None
        assert pending.expires_at > datetime.utcnow()


def test_init_accepts_optional_device_label(client):
    body = _init(client, device_label="Fire TV — Stick 4K Max")
    with client.application.app_context():
        pending = db.session.query(TVPendingPair).filter_by(code=body["code"]).first()
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
        p = db.session.query(TVPendingPair).filter_by(code=body["code"]).first()
        p.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()
    resp = client.get("/api/tv-pair/status",
                       query_string={"token": body["device_token"]})
    assert resp.get_json()["status"] == "expired"


def test_status_claimed_after_admin_claims_the_code(client, test_store_id):
    """End-to-end happy path: TV initiates, admin claims, TV's poll
    flips to "claimed" and gets a /tv/device/<token> URL."""
    _activate_addon(client, test_store_id)
    jwt = _admin_jwt(client, test_store_id)
    _ensure_display(client, test_store_id, jwt)
    body = _init(client)
    resp = _claim(client, body["code"], jwt)
    assert resp.status_code == 204
    poll = client.get("/api/tv-pair/status",
                       query_string={"token": body["device_token"]}).get_json()
    assert poll["status"] == "claimed"
    assert poll["display_url"].endswith("/tv/device/" + body["device_token"])
    assert poll["store_name"] == "Test Store"
    assert "title" in poll


# ── /api/v2/tv-display/claim (admin side, JSON) ───────────────

def test_claim_blocked_when_addon_off(client, test_store_id):
    """Claim requires the addon — the JSON endpoint returns 409 (the
    same code the legacy form-POST flagged via flash + redirect)."""
    body = _init(client)
    jwt = _admin_jwt(client, test_store_id)
    resp = client.post(
        "/api/v2/tv-display/claim",
        json={"code": body["code"]},
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert resp.status_code == 409
    with client.application.app_context():
        p = db.session.query(TVPendingPair).filter_by(code=body["code"]).first()
        assert p.claimed_at is None


def test_claim_creates_tvpairing_reusing_device_token(client, test_store_id):
    """The device_token from the pending row is COPIED into the new
    TVPairing — the Fire TV stores its token once at /init time and
    never sees a rotation."""
    _activate_addon(client, test_store_id)
    jwt = _admin_jwt(client, test_store_id)
    _ensure_display(client, test_store_id, jwt)
    body = _init(client)
    _claim(client, body["code"], jwt)
    with client.application.app_context():
        pairing = db.session.query(TVPairing).filter_by(
            device_token=body["device_token"]).first()
        assert pairing is not None
        assert pairing.revoked_at is None
        pending = db.session.query(TVPendingPair).filter_by(code=body["code"]).first()
        assert pending.claimed_at is not None
        assert pending.claimed_pairing_id == pairing.id


def test_claim_strips_whitespace_and_lowercase(client, test_store_id):
    """Operator pastes 'abc - 234' from a Fire TV that renders the
    code with spacing — server normalizes the same way the client
    JS does."""
    _activate_addon(client, test_store_id)
    jwt = _admin_jwt(client, test_store_id)
    _ensure_display(client, test_store_id, jwt)
    body = _init(client)
    munged = body["code"][:3].lower() + " - " + body["code"][3:].lower()
    resp = _claim(client, munged, jwt)
    assert resp.status_code == 204
    with client.application.app_context():
        assert db.session.query(TVPairing).filter_by(
            device_token=body["device_token"]).first() is not None


def test_claim_is_single_use(client, test_store_id):
    """*** Anti-misuse rule: a code claimed once cannot be claimed
    again. *** Even by the same admin. The pending row stays around
    for audit but its claimed_at is non-NULL forever after."""
    _activate_addon(client, test_store_id)
    jwt = _admin_jwt(client, test_store_id)
    _ensure_display(client, test_store_id, jwt)
    body = _init(client)
    first = _claim(client, body["code"], jwt)
    second = _claim(client, body["code"], jwt)
    assert first.status_code == 204
    assert second.status_code == 400
    assert b"Code not found or expired" in second.data


def test_claim_400_for_unknown_code(client, test_store_id):
    """All failure modes return the same opaque 400 so brute-force
    probes can't tell unknown vs expired vs already-claimed apart."""
    _activate_addon(client, test_store_id)
    jwt = _admin_jwt(client, test_store_id)
    _ensure_display(client, test_store_id, jwt)
    resp = client.post(
        "/api/v2/tv-display/claim",
        json={"code": "ZZZZZZ"},
        headers={"Authorization": f"Bearer {jwt}"},
    )
    assert resp.status_code == 400
    assert b"Code not found or expired" in resp.data


def test_claim_rejects_short_code(client, test_store_id):
    _activate_addon(client, test_store_id)
    jwt = _admin_jwt(client, test_store_id)
    _ensure_display(client, test_store_id, jwt)
    resp = client.post(
        "/api/v2/tv-display/claim",
        json={"code": "AB"},
        headers={"Authorization": f"Bearer {jwt}"},
    )
    # Same opaque 400 as unknown — short codes can't be enumerated
    # any more than wrong-but-legal-length ones.
    assert resp.status_code == 400


def test_claim_revokes_prior_pairing(client, test_store_id):
    """*** Operator concern: pairing a NEW Fire TV must immediately
    disable the OLD one. *** Single-active-pairing per display
    enforces "one $5 sub = one Fire TV at a time."""
    _activate_addon(client, test_store_id)
    jwt = _admin_jwt(client, test_store_id)
    _ensure_display(client, test_store_id, jwt)
    a = _init(client)
    _claim(client, a["code"], jwt)
    assert client.get("/tv/device/" + a["device_token"]).status_code == 200
    b = _init(client)
    _claim(client, b["code"], jwt)
    with client.application.app_context():
        old = db.session.query(TVPairing).filter_by(device_token=a["device_token"]).first()
        new = db.session.query(TVPairing).filter_by(device_token=b["device_token"]).first()
        assert old.revoked_at is not None
        assert new.revoked_at is None
    assert client.get("/tv/device/" + a["device_token"]).status_code == 404
    assert client.get("/tv/device/" + b["device_token"]).status_code == 200
    poll = client.get("/api/tv-pair/status",
                       query_string={"token": a["device_token"]}).get_json()
    assert poll["status"] == "expired"


def test_claim_400_when_pending_already_claimed(client, test_store_id):
    """Two admins racing to claim the same code (e.g. shared
    superadmin shoulder-surfing): only one wins, the other gets the
    same vague 400."""
    _activate_addon(client, test_store_id)
    jwt = _admin_jwt(client, test_store_id)
    _ensure_display(client, test_store_id, jwt)
    body = _init(client)
    _claim(client, body["code"], jwt)
    resp = _claim(client, body["code"], jwt)
    assert resp.status_code == 400
    assert b"Code not found or expired" in resp.data


# ── /tv/device/<device_token> render path ──────────────────────

def _populate_one_country(client, store_id, jwt):
    """Set up a country with one bank for the public-render tests.
    Country header via JSON; the bank gets added directly through
    SQLAlchemy because the legacy `/tv-display/countries/<id>`
    Flask form-POST handler was retired in chunk 3 and no
    `/api/v2/tv-display/payout-banks` endpoint exists yet (it lands
    in the Later phase of the architecture cleanup)."""
    _activate_addon(client, store_id)
    create = client.post(
        "/api/v2/tv-display/countries",
        json={"country_name": "Mexico", "country_code": "MX",
              "mt_companies": "Maxi, Vigo"},
        headers={"Authorization": f"Bearer {jwt}"},
    )
    country_id = create.get_json()["id"]
    from api.Modules.TVDisplay.Models import TVDisplayPayoutBank
    from tests._app import app as flask_app, db
    with flask_app.app_context():
        db.session.add(TVDisplayPayoutBank(
            country_id=country_id, bank_name="Bancomer", sort_order=0,
        ))
        db.session.commit()


def test_device_url_renders_full_board(client, test_store_id):
    jwt = _admin_jwt(client, test_store_id)
    _populate_one_country(client, test_store_id, jwt)
    body = _init(client)
    _claim(client, body["code"], jwt)
    resp = client.get("/tv/device/" + body["device_token"])
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Mexico" in html
    assert "Bancomer" in html
    assert "design-tokens.css" in html


def test_device_url_404s_after_being_superseded(client, test_store_id):
    _activate_addon(client, test_store_id)
    jwt = _admin_jwt(client, test_store_id)
    _ensure_display(client, test_store_id, jwt)
    a = _init(client)
    _claim(client, a["code"], jwt)
    b = _init(client)
    _claim(client, b["code"], jwt)
    assert client.get("/tv/device/" + a["device_token"]).status_code == 404


def test_device_url_404s_when_addon_revoked(client, test_store_id):
    _activate_addon(client, test_store_id)
    jwt = _admin_jwt(client, test_store_id)
    _ensure_display(client, test_store_id, jwt)
    body = _init(client)
    _claim(client, body["code"], jwt)
    with client.application.app_context():
        s = db.session.get(Store, test_store_id)
        s.addons = ""; db.session.commit()
    assert client.get("/tv/device/" + body["device_token"]).status_code == 404


def test_device_url_bumps_last_seen_at(client, test_store_id):
    _activate_addon(client, test_store_id)
    jwt = _admin_jwt(client, test_store_id)
    _ensure_display(client, test_store_id, jwt)
    body = _init(client)
    _claim(client, body["code"], jwt)
    with client.application.app_context():
        db.session.query(TVPairing).filter_by(
            device_token=body["device_token"]
        ).update({"last_seen_at": datetime.utcnow() - timedelta(minutes=5)})
        db.session.commit()
    client.get("/tv/device/" + body["device_token"])
    with client.application.app_context():
        after = db.session.query(TVPairing).filter_by(
            device_token=body["device_token"]).first().last_seen_at
        assert after > (datetime.utcnow() - timedelta(minutes=1))


def test_legacy_public_url_still_works_for_tablets(client, test_store_id):
    """The user explicitly asked to keep /tv/<public_token> working
    for operators running tablets/Chromecasts. Verify the inverted
    pair flow doesn't break that path."""
    jwt = _admin_jwt(client, test_store_id)
    _populate_one_country(client, test_store_id, jwt)
    with client.application.app_context():
        token = db.session.query(TVDisplay).first().public_token
    assert client.get("/tv/" + token).status_code == 200
    a = _init(client)
    _claim(client, a["code"], jwt)
    b = _init(client)
    _claim(client, b["code"], jwt)  # supersede
    assert client.get("/tv/" + token).status_code == 200


# ── Employee access ────────────────────────────────────────────

def test_employee_can_claim_a_code(client, test_store_id):
    """v1 grants employees TV-display access — pairing is daily-
    operations work, not back-office. Employee mints their own JWT
    via /api/v2/auth/login."""
    _activate_addon(client, test_store_id)
    from tests.conftest import make_employee_client
    _emp_client, emp_jwt = make_employee_client(test_store_id)
    _ensure_display(client, test_store_id, emp_jwt)
    body = _init(client)
    resp = _claim(client, body["code"], emp_jwt)
    assert resp.status_code == 204
    with client.application.app_context():
        assert db.session.query(TVPairing).filter_by(
            device_token=body["device_token"]).first() is not None


# ── Alphabet sanity ────────────────────────────────────────────

def test_pair_code_alphabet_excludes_ambiguous_chars():
    """Hand-rolled the alphabet so nobody has to read O vs 0 or I vs 1
    on a Fire TV from across a counter."""
    for c in "O0I1LB8":
        assert c not in _PAIR_CODE_ALPHABET
    # 21 unambiguous uppercase letters + 6 unambiguous digits = 27.
    assert len(set(_PAIR_CODE_ALPHABET)) == 27
