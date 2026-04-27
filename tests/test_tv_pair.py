"""TV Display pair-code system — admin-side generation, public-side
redemption, single-use enforcement, expiry, and addon gating.

The pair-code flow is what lets the Fire TV / Google TV companion app
bootstrap into the long public_token without the operator typing 32
URL-safe characters on a remote. These tests pin the security-relevant
properties: codes are single-use, expire in 10 minutes, and only
redeem when the store currently has the tv_display add-on active.
"""
from datetime import datetime, timedelta

from app import (
    db, User, Store, TVDisplay, TVPairing,
    _PAIR_CODE_ALPHABET, _PAIR_CODE_LIFETIME,
)


# ── Helpers ────────────────────────────────────────────────────

def _activate_addon(client, store_id):
    """Flip tv_display on for a store via direct DB write — same
    helper pattern as test_tv_display.py uses."""
    with client.application.app_context():
        s = db.session.get(Store, store_id)
        s.plan = "basic"
        s.addons = "tv_display"
        db.session.commit()


def _ensure_display(client):
    """Land on /tv-display once so _ensure_tv_display creates the row.
    Returns the freshly created TVDisplay's id + public_token."""
    client.get("/tv-display")
    with client.application.app_context():
        d = TVDisplay.query.first()
        return d.id, d.public_token


# ── Admin: generate pair code ──────────────────────────────────

def test_pair_code_endpoint_blocked_when_addon_off(logged_in_client):
    """Generating a pair code requires the addon — same gate as the
    rest of the /tv-display surface."""
    resp = logged_in_client.post("/tv-display/pair-code")
    assert resp.status_code == 302  # redirected to /admin/subscription


def test_pair_code_endpoint_returns_six_char_code(logged_in_client, test_store_id):
    _activate_addon(logged_in_client, test_store_id)
    _ensure_display(logged_in_client)
    resp = logged_in_client.post("/tv-display/pair-code")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "code" in body
    assert "expires_at" in body
    assert "ttl_seconds" in body
    assert len(body["code"]) == 6
    # Every char must be from the safe alphabet (no O/0/I/1/L/B/8).
    assert all(c in _PAIR_CODE_ALPHABET for c in body["code"])
    # Lifetime matches the constant — guards against accidental tweaks.
    assert body["ttl_seconds"] == int(_PAIR_CODE_LIFETIME.total_seconds())


def test_generating_a_new_code_supersedes_the_old(logged_in_client, test_store_id):
    """Single-active-code-per-display: a fresh /pair-code call must
    overwrite the previous code so an operator who clicks Generate
    twice doesn't accidentally leave two valid codes floating around."""
    _activate_addon(logged_in_client, test_store_id)
    _ensure_display(logged_in_client)
    first  = logged_in_client.post("/tv-display/pair-code").get_json()["code"]
    second = logged_in_client.post("/tv-display/pair-code").get_json()["code"]
    assert first != second
    # The first code is now dead — redeeming it must fail.
    resp = logged_in_client.application.test_client().post(
        "/api/tv-pair/redeem", json={"code": first})
    assert resp.status_code == 404


def test_pair_code_persists_to_tv_display_row(logged_in_client, test_store_id):
    _activate_addon(logged_in_client, test_store_id)
    _ensure_display(logged_in_client)
    code = logged_in_client.post("/tv-display/pair-code").get_json()["code"]
    with logged_in_client.application.app_context():
        d = TVDisplay.query.first()
        assert d.pair_code == code
        assert d.pair_code_expires_at is not None
        assert d.pair_code_expires_at > datetime.utcnow()


# ── Public redeem ──────────────────────────────────────────────

def test_redeem_returns_device_url_on_success(client, logged_in_client, test_store_id):
    """Successful redeem returns a device-specific URL bound to a
    fresh TVPairing — NOT the shared public_token. The Fire TV must
    never see the shared secret."""
    _activate_addon(logged_in_client, test_store_id)
    _, public_token = _ensure_display(logged_in_client)
    code = logged_in_client.post("/tv-display/pair-code").get_json()["code"]
    resp = client.post("/api/tv-pair/redeem", json={"code": code})
    assert resp.status_code == 200
    body = resp.get_json()
    assert "device_token" in body
    assert body["display_url"].endswith("/tv/device/" + body["device_token"])
    # Defense in depth: the shared public_token must NOT appear anywhere
    # in the response payload.
    assert public_token not in str(body)
    assert "public_token" not in body
    assert body["store_name"] == "Test Store"
    assert "title" in body


def test_redeem_creates_tvpairing_row(client, logged_in_client, test_store_id):
    """The redeem flow persists a TVPairing — it's the durable record
    of which device is bound to this display, used by /tv/device/<t>
    to authorize each render."""
    _activate_addon(logged_in_client, test_store_id)
    _ensure_display(logged_in_client)
    code = logged_in_client.post("/tv-display/pair-code").get_json()["code"]
    body = client.post("/api/tv-pair/redeem", json={"code": code}).get_json()
    with client.application.app_context():
        pairing = TVPairing.query.filter_by(device_token=body["device_token"]).first()
        assert pairing is not None
        assert pairing.revoked_at is None
        assert pairing.last_seen_at is not None


def test_redeem_accepts_optional_device_label(client, logged_in_client, test_store_id):
    _activate_addon(logged_in_client, test_store_id)
    _ensure_display(logged_in_client)
    code = logged_in_client.post("/tv-display/pair-code").get_json()["code"]
    body = client.post("/api/tv-pair/redeem", json={
        "code": code, "device_label": "Fire TV — Counter 1",
    }).get_json()
    with client.application.app_context():
        pairing = TVPairing.query.filter_by(device_token=body["device_token"]).first()
        assert pairing.device_label == "Fire TV — Counter 1"


def test_redeem_strips_spaces_and_lowercases(client, logged_in_client, test_store_id):
    """Operator types 'abc 234' on a Fire TV remote — server must
    normalize to 'ABC234' before lookup. Anything outside the safe
    alphabet is dropped."""
    _activate_addon(logged_in_client, test_store_id)
    _ensure_display(logged_in_client)
    code = logged_in_client.post("/tv-display/pair-code").get_json()["code"]
    # Inject spaces, hyphens, lowercase — all should be stripped.
    munged = code[:3].lower() + " - " + code[3:].lower()
    resp = client.post("/api/tv-pair/redeem", json={"code": munged})
    assert resp.status_code == 200
    assert resp.get_json()["device_token"]


def test_redeem_is_single_use(client, logged_in_client, test_store_id):
    """*** Operator concern: a code redeemed by one Fire TV must not
    work for a second device. *** This is the core anti-misuse rule —
    one code, one TV. After a successful redeem the code is wiped from
    the DB so a second redeem from any device returns 404."""
    _activate_addon(logged_in_client, test_store_id)
    _ensure_display(logged_in_client)
    code = logged_in_client.post("/tv-display/pair-code").get_json()["code"]
    first  = client.post("/api/tv-pair/redeem", json={"code": code})
    second = client.post("/api/tv-pair/redeem", json={"code": code})
    assert first.status_code == 200
    assert second.status_code == 404
    # Defense in depth: the column must actually be empty in the DB.
    with client.application.app_context():
        d = TVDisplay.query.first()
        assert d.pair_code == ""
        assert d.pair_code_expires_at is None


def test_redeem_revokes_prior_pairing(client, logged_in_client, test_store_id):
    """*** Operator concern: pairing a NEW Fire TV must immediately
    disable the OLD one. *** Single-active-pairing per display is the
    one-$5-sub-one-TV enforcement."""
    _activate_addon(logged_in_client, test_store_id)
    _ensure_display(logged_in_client)
    # First pairing.
    code1 = logged_in_client.post("/tv-display/pair-code").get_json()["code"]
    body1 = client.post("/api/tv-pair/redeem", json={"code": code1}).get_json()
    token1 = body1["device_token"]
    # Old TV's URL is live.
    assert client.get("/tv/device/" + token1).status_code == 200
    # Second pairing — supersedes the first.
    code2 = logged_in_client.post("/tv-display/pair-code").get_json()["code"]
    body2 = client.post("/api/tv-pair/redeem", json={"code": code2}).get_json()
    token2 = body2["device_token"]
    assert token1 != token2
    # Old TV is now revoked at the DB level.
    with client.application.app_context():
        old = TVPairing.query.filter_by(device_token=token1).first()
        new = TVPairing.query.filter_by(device_token=token2).first()
        assert old.revoked_at is not None
        assert new.revoked_at is None
    # Old TV's URL now 404s; new TV's URL works.
    assert client.get("/tv/device/" + token1).status_code == 404
    assert client.get("/tv/device/" + token2).status_code == 200


def test_redeem_404s_on_unknown_code(client):
    resp = client.post("/api/tv-pair/redeem", json={"code": "ZZZZZZ"})
    assert resp.status_code == 404


def test_redeem_404s_on_garbage_input(client):
    """Empty body, missing field, wrong length, non-string — all 404."""
    assert client.post("/api/tv-pair/redeem").status_code == 404
    assert client.post("/api/tv-pair/redeem", json={}).status_code == 404
    assert client.post("/api/tv-pair/redeem", json={"code": ""}).status_code == 404
    assert client.post("/api/tv-pair/redeem", json={"code": "AB"}).status_code == 404
    assert client.post("/api/tv-pair/redeem", json={"code": "TOO LONG XYZ"}).status_code == 404


def test_redeem_404s_after_expiry(client, logged_in_client, test_store_id):
    """Manually rewind expires_at past now and confirm the code is
    treated as dead. Avoids actually sleeping 10 minutes."""
    _activate_addon(logged_in_client, test_store_id)
    _ensure_display(logged_in_client)
    code = logged_in_client.post("/tv-display/pair-code").get_json()["code"]
    with logged_in_client.application.app_context():
        d = TVDisplay.query.first()
        d.pair_code_expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()
    resp = client.post("/api/tv-pair/redeem", json={"code": code})
    assert resp.status_code == 404


def test_redeem_404s_after_addon_revoked(client, logged_in_client, test_store_id):
    """A live, unexpired code must STILL fail to redeem if the store's
    addon was switched off between code generation and redemption.
    Stripe is the gatekeeper — the Fire TV app cannot bypass billing
    by holding onto an old pair code."""
    _activate_addon(logged_in_client, test_store_id)
    _ensure_display(logged_in_client)
    code = logged_in_client.post("/tv-display/pair-code").get_json()["code"]
    # Yank the addon.
    with logged_in_client.application.app_context():
        s = db.session.get(Store, test_store_id)
        s.addons = ""; db.session.commit()
    resp = client.post("/api/tv-pair/redeem", json={"code": code})
    assert resp.status_code == 404


def test_failure_responses_are_indistinguishable(client, logged_in_client, test_store_id):
    """All failure modes return identical 404 + {"error":"not_found"}.
    Brute-force probes can't tell "wrong code" from "expired" from
    "addon off" — eliminates the oracle."""
    # Wrong code.
    a = client.post("/api/tv-pair/redeem", json={"code": "ZZZZZZ"})
    # Expired.
    _activate_addon(logged_in_client, test_store_id)
    _ensure_display(logged_in_client)
    code = logged_in_client.post("/tv-display/pair-code").get_json()["code"]
    with logged_in_client.application.app_context():
        d = TVDisplay.query.first()
        d.pair_code_expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()
    b = client.post("/api/tv-pair/redeem", json={"code": code})
    # Addon off (regenerate, then revoke).
    code2 = logged_in_client.post("/tv-display/pair-code").get_json()["code"]
    with logged_in_client.application.app_context():
        s = db.session.get(Store, test_store_id)
        s.addons = ""; db.session.commit()
    c = client.post("/api/tv-pair/redeem", json={"code": code2})

    assert a.status_code == b.status_code == c.status_code == 404
    assert a.get_json() == b.get_json() == c.get_json()


# ── Employee access ────────────────────────────────────────────

def test_employee_can_generate_pair_code(client, test_store_id):
    """Pairing is daily-operations work, not back-office — same as the
    rest of /tv-display, employees can hit the generate endpoint."""
    _activate_addon(client, test_store_id)
    from tests.conftest import make_employee_client
    emp = make_employee_client(test_store_id)
    resp = emp.post("/tv-display/pair-code")
    assert resp.status_code == 200
    assert "code" in resp.get_json()


# ── Device URL (the per-Fire-TV bound URL) ─────────────────────

def _populate_one_country(client, store_id):
    """Quick helper — create a Mexico section with a Bancomer row so
    the rendered TV board has actual content to assert on."""
    _activate_addon(client, store_id)
    client.get("/tv-display")  # ensure display exists
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


def _redeem(client, code):
    return client.post("/api/tv-pair/redeem", json={"code": code}).get_json()


def test_device_url_renders_full_board(client, logged_in_client, test_store_id):
    """The per-device URL renders the same board the legacy public
    URL does — same template, same data."""
    _populate_one_country(logged_in_client, test_store_id)
    code = logged_in_client.post("/tv-display/pair-code").get_json()["code"]
    body = _redeem(client, code)
    resp = client.get("/tv/device/" + body["device_token"])
    assert resp.status_code == 200
    html = resp.data.decode()
    assert "Mexico" in html
    assert "Bancomer" in html
    assert "Maxi" in html and "Vigo" in html
    # Brand design tokens still flow through (regression-guard so a
    # future refactor can't accidentally break the dark+neon look).
    assert "design-tokens.css" in html
    assert "--db-neon" in html


def test_device_url_404s_on_unknown_token(client):
    assert client.get("/tv/device/totally-bogus-token").status_code == 404


def test_device_url_404s_after_being_superseded(client, logged_in_client, test_store_id):
    """Pairing a second TV must immediately retire the first TV's URL
    — that's the one-Fire-TV-per-sub enforcement at render time."""
    _activate_addon(logged_in_client, test_store_id)
    _ensure_display(logged_in_client)
    code1 = logged_in_client.post("/tv-display/pair-code").get_json()["code"]
    body1 = _redeem(client, code1)
    code2 = logged_in_client.post("/tv-display/pair-code").get_json()["code"]
    _redeem(client, code2)
    assert client.get("/tv/device/" + body1["device_token"]).status_code == 404


def test_device_url_404s_when_addon_revoked(client, logged_in_client, test_store_id):
    """Even an actively-paired Fire TV stops working the moment the
    store's tv_display addon is switched off."""
    _activate_addon(logged_in_client, test_store_id)
    _ensure_display(logged_in_client)
    code = logged_in_client.post("/tv-display/pair-code").get_json()["code"]
    body = _redeem(client, code)
    # Yank the addon.
    with logged_in_client.application.app_context():
        s = db.session.get(Store, test_store_id)
        s.addons = ""; db.session.commit()
    assert client.get("/tv/device/" + body["device_token"]).status_code == 404


def test_device_url_bumps_last_seen_at(client, logged_in_client, test_store_id):
    """Every successful render touches last_seen_at so the upcoming
    admin UI can show 'Fire TV last seen 2 min ago'. Compares the
    timestamp before and after a fetch."""
    _activate_addon(logged_in_client, test_store_id)
    _ensure_display(logged_in_client)
    code = logged_in_client.post("/tv-display/pair-code").get_json()["code"]
    body = _redeem(client, code)
    with client.application.app_context():
        before = TVPairing.query.filter_by(
            device_token=body["device_token"]).first().last_seen_at
        # Force a wider gap than the redeem→fetch sub-millisecond delta
        # so the comparison is unambiguous on fast machines.
        TVPairing.query.filter_by(device_token=body["device_token"]).update(
            {"last_seen_at": datetime.utcnow() - timedelta(minutes=5)})
        db.session.commit()
    client.get("/tv/device/" + body["device_token"])
    with client.application.app_context():
        after = TVPairing.query.filter_by(
            device_token=body["device_token"]).first().last_seen_at
        assert after > (datetime.utcnow() - timedelta(minutes=1))


def test_legacy_public_url_still_works_for_tablets(client, logged_in_client, test_store_id):
    """Tablets / Chromecasts use /tv/<public_token> directly without
    pairing — the operator may not have a Fire TV setup. That flow
    must keep working independently of any pair-code state."""
    _populate_one_country(logged_in_client, test_store_id)
    with client.application.app_context():
        token = TVDisplay.query.first().public_token
    resp = client.get("/tv/" + token)
    assert resp.status_code == 200
    assert "Mexico" in resp.data.decode()
    # Even if a Fire TV has paired and been revoked, the legacy URL
    # is not affected.
    code = logged_in_client.post("/tv-display/pair-code").get_json()["code"]
    _redeem(client, code)
    code2 = logged_in_client.post("/tv-display/pair-code").get_json()["code"]
    _redeem(client, code2)  # supersede
    assert client.get("/tv/" + token).status_code == 200


# ── Alphabet sanity ────────────────────────────────────────────

def test_pair_code_alphabet_excludes_ambiguous_chars():
    """Hand-rolled the alphabet so nobody has to read O vs 0 or I vs 1
    on a Fire TV from across a counter."""
    for c in "O0I1LB8":
        assert c not in _PAIR_CODE_ALPHABET
    # 21 unambiguous uppercase letters + 6 unambiguous digits = 27.
    # Codes are 6 chars long, so the keyspace is 27**6 ≈ 387M.
    assert len(set(_PAIR_CODE_ALPHABET)) == 27
