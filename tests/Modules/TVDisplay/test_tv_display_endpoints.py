"""HTTP integration tests for /api/v2/tv-display/*.

Read-only endpoints: overview + per-country drill-down. Mirrors the
legacy `_tv_required()` guard — JWT must carry a store scope, the
role must be admin or employee, and the store must have the
`tv_display` add-on active.
"""


def _login_admin(client, store_id):
    resp = client.post(
        "/api/v2/auth/login",
        json={
            "username": "admin@test.com",
            "password": "testpass123!",
            "store_id": store_id,
        },
    )
    return resp.get_json()["access_token"]


def _login_superadmin(client):
    """Wraps the SPA two-step login (password → TOTP exchange)
    using the seeded superadmin's pre-enrolled TOTP secret. See
    tests/conftest.py for the secret + helper definition."""
    from tests.conftest import login_superadmin
    return login_superadmin(client)


def _enable_tv_addon(store_id):
    """Flip the tv_display add-on on for the seeded test store.
    Mirrors what the legacy /admin/subscription/addons toggle does
    — comma-separated list on Store.addons."""
    from api.Modules.Tenancy.Models import Store
    from app import app as flask_app, db
    with flask_app.app_context():
        s = db.session.get(Store, store_id)
        s.plan = "basic"
        s.addons = "tv_display"
        db.session.commit()


def _seed_country(store_id, **overrides):
    """Insert a TVDisplayCountry row for the given store. Returns
    (display_id, country_id)."""
    from api.Modules.TVDisplay.Models import TVDisplay, TVDisplayCountry
    from app import app as flask_app, db
    import secrets
    with flask_app.app_context():
        d = db.session.query(TVDisplay).filter_by(store_id=store_id).one_or_none()
        if d is None:
            d = TVDisplay(
                store_id=store_id,
                public_token=secrets.token_urlsafe(24),
            )
            db.session.add(d); db.session.flush()
        c = TVDisplayCountry(
            display_id=d.id,
            country_code=overrides.pop("country_code", "MX"),
            country_name=overrides.pop("country_name", "Mexico"),
            sort_order=overrides.pop("sort_order", 0),
            mt_companies=overrides.pop("mt_companies", "Maxi,Vigo"),
        )
        for k, v in overrides.items():
            setattr(c, k, v)
        db.session.add(c); db.session.commit()
        return d.id, c.id


def _seed_bank_with_rates(country_id, bank_name, rates):
    """Insert one TVDisplayPayoutBank + a TVDisplayRate per entry in
    `rates` (dict mt_company -> rate)."""
    from api.Modules.TVDisplay.Models import TVDisplayPayoutBank, TVDisplayRate
    from app import app as flask_app, db
    with flask_app.app_context():
        b = TVDisplayPayoutBank(
            country_id=country_id, bank_name=bank_name, sort_order=0,
        )
        db.session.add(b); db.session.flush()
        for mt_company, rate in rates.items():
            db.session.add(TVDisplayRate(
                bank_id=b.id, mt_company=mt_company, rate=float(rate),
            ))
        db.session.commit()
        return b.id


# ── overview ────────────────────────────────────────────────


def test_overview_requires_jwt(client):
    resp = client.get("/api/v2/tv-display/overview")
    assert resp.status_code == 401


def test_overview_404_for_superadmin(client):
    """Superadmin JWT carries no store scope — TV display is a per-
    store feature, so the endpoint 404s rather than falling through."""
    token = _login_superadmin(client)
    resp = client.get(
        "/api/v2/tv-display/overview",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_overview_409_when_addon_inactive(client, test_store_id):
    """Store without the tv_display add-on → 409 (mirrors the legacy
    'turn it on from your subscription page' redirect)."""
    token = _login_admin(client, test_store_id)
    resp = client.get(
        "/api/v2/tv-display/overview",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


def test_overview_envelope_when_no_countries(client, test_store_id):
    _enable_tv_addon(test_store_id)
    token = _login_admin(client, test_store_id)
    resp = client.get(
        "/api/v2/tv-display/overview",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body.keys()) == {
        "display_id", "title", "subtitle", "orientation", "theme",
        "public_token", "public_url", "last_updated_at",
        "countries", "active_pairing",
    }
    assert body["countries"] == []
    assert body["active_pairing"] is None
    assert body["public_url"].startswith("/tv/")
    # Defaults from the model
    assert body["title"] == "Cheapest Money Transfer"
    assert body["theme"] == "light"


def test_overview_orders_countries_by_sort_then_id(client, test_store_id):
    _enable_tv_addon(test_store_id)
    _seed_country(test_store_id, country_name="Guatemala", sort_order=2)
    _seed_country(test_store_id, country_name="Mexico", sort_order=1)
    token = _login_admin(client, test_store_id)
    body = client.get(
        "/api/v2/tv-display/overview",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    names = [c["country_name"] for c in body["countries"]]
    assert names == ["Mexico", "Guatemala"]


def test_overview_country_stats_counts_banks_and_rates(client, test_store_id):
    _enable_tv_addon(test_store_id)
    _, country_id = _seed_country(test_store_id, mt_companies="Maxi,Vigo")
    _seed_bank_with_rates(
        country_id, "Bancomer", {"Maxi": 18.50, "Vigo": 18.20},
    )
    _seed_bank_with_rates(
        country_id, "Banorte", {"Maxi": 18.40},
    )
    token = _login_admin(client, test_store_id)
    body = client.get(
        "/api/v2/tv-display/overview",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert len(body["countries"]) == 1
    row = body["countries"][0]
    assert row["bank_count"] == 2
    assert row["rate_count"] == 3
    assert row["mt_companies"] == "Maxi,Vigo"


def test_overview_active_pairing_surfaces_newest_unrevoked(client, test_store_id):
    """Most-recent unrevoked TVPairing should populate active_pairing."""
    from api.Modules.TVDisplay.Models import TVPairing
    from app import app as flask_app, db
    from datetime import datetime, timedelta
    _enable_tv_addon(test_store_id)
    display_id, _ = _seed_country(test_store_id)
    with flask_app.app_context():
        # Old revoked pairing that should be ignored.
        db.session.add(TVPairing(
            display_id=display_id, device_token="aaaa",
            device_label="Old Counter",
            paired_at=datetime.utcnow() - timedelta(days=3),
            revoked_at=datetime.utcnow() - timedelta(days=1),
        ))
        # Active newer pairing — this is what the SPA shows.
        db.session.add(TVPairing(
            display_id=display_id, device_token="bbbb",
            device_label="Counter 1",
            paired_at=datetime.utcnow() - timedelta(hours=2),
        ))
        db.session.commit()
    token = _login_admin(client, test_store_id)
    body = client.get(
        "/api/v2/tv-display/overview",
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    assert body["active_pairing"] is not None
    assert body["active_pairing"]["device_label"] == "Counter 1"


# ── country detail ──────────────────────────────────────────


def test_country_detail_requires_jwt(client):
    resp = client.get("/api/v2/tv-display/countries/1")
    assert resp.status_code == 401


def test_country_detail_404_when_country_belongs_elsewhere(client, test_store_id):
    """Cross-store ID → 404 (opaque tenancy)."""
    from api.Modules.TVDisplay.Models import TVDisplay, TVDisplayCountry
    from api.Modules.Tenancy.Models import Store
    from app import app as flask_app, db
    import secrets
    _enable_tv_addon(test_store_id)
    # Seed a SECOND store + country, so we have a country_id that
    # isn't owned by the principal's display.
    with flask_app.app_context():
        other = Store(
            name="Other Store", slug="other-store",
            email="other@test.com", plan="basic", addons="tv_display",
        )
        db.session.add(other); db.session.flush()
        d = TVDisplay(
            store_id=other.id, public_token=secrets.token_urlsafe(24),
        )
        db.session.add(d); db.session.flush()
        c = TVDisplayCountry(
            display_id=d.id, country_code="GT",
            country_name="Guatemala", sort_order=0, mt_companies="",
        )
        db.session.add(c); db.session.commit()
        foreign_country_id = c.id
    token = _login_admin(client, test_store_id)
    resp = client.get(
        f"/api/v2/tv-display/countries/{foreign_country_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_country_detail_returns_banks_with_sparse_rate_matrix(
    client, test_store_id,
):
    """Banks come back ordered, each with a rates map keyed by
    mt_company. Missing cells are simply absent (renderer prints
    "—")."""
    _enable_tv_addon(test_store_id)
    _, country_id = _seed_country(
        test_store_id, country_name="Mexico", mt_companies="Maxi,Vigo",
    )
    _seed_bank_with_rates(
        country_id, "Bancomer", {"Maxi": 18.50, "Vigo": 18.20},
    )
    _seed_bank_with_rates(
        country_id, "Banorte", {"Maxi": 18.40},  # sparse
    )
    token = _login_admin(client, test_store_id)
    resp = client.get(
        f"/api/v2/tv-display/countries/{country_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["country_name"] == "Mexico"
    assert body["mt_companies"] == ["Maxi", "Vigo"]
    assert len(body["banks"]) == 2
    by_name = {b["bank_name"]: b for b in body["banks"]}
    assert by_name["Bancomer"]["rates"] == {"Maxi": 18.50, "Vigo": 18.20}
    assert by_name["Banorte"]["rates"] == {"Maxi": 18.40}


def test_country_detail_employee_role_allowed(client, test_store_id):
    """Employees can edit rates on the legacy page, so the read
    endpoint must let them in too."""
    from tests.conftest import make_employee_client
    _enable_tv_addon(test_store_id)
    _, country_id = _seed_country(test_store_id)
    _emp_client, token = make_employee_client(test_store_id)
    resp = client.get(
        f"/api/v2/tv-display/countries/{country_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


# ── write-side: settings ─────────────────────────────────────


def test_settings_requires_jwt(client):
    resp = client.post("/api/v2/tv-display/settings", json={})
    assert resp.status_code == 401


def test_settings_409_when_addon_inactive(client, test_store_id):
    """Mirrors the overview-side gate. Saves are blocked at the same
    layer so a curl client without the SPA can't mutate config on a
    store whose subscription doesn't include the add-on."""
    token = _login_admin(client, test_store_id)
    resp = client.post(
        "/api/v2/tv-display/settings",
        json={"title": "Hi", "subtitle": "", "orientation": "auto", "theme": "light"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


def test_settings_persists_full_payload(client, test_store_id):
    _enable_tv_addon(test_store_id)
    token = _login_admin(client, test_store_id)
    resp = client.post(
        "/api/v2/tv-display/settings",
        json={"title": "Hello", "subtitle": "World",
              "orientation": "portrait", "theme": "dark"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204
    from api.Modules.TVDisplay.Models import TVDisplay
    from app import app as flask_app
    with flask_app.app_context():
        d = TVDisplay.query.first()
        assert d.title == "Hello"
        assert d.subtitle == "World"
        assert d.orientation == "portrait"
        assert d.theme == "dark"


def test_settings_invalid_orientation_falls_back(client, test_store_id):
    """Same forgiving behaviour as the legacy form: garbage
    orientation/theme silently snaps to the safe default rather than
    422-ing the whole save (preserves operator UX from v1)."""
    _enable_tv_addon(test_store_id)
    token = _login_admin(client, test_store_id)
    client.post(
        "/api/v2/tv-display/settings",
        json={"title": "X", "subtitle": "",
              "orientation": "diagonal", "theme": "neon"},
        headers={"Authorization": f"Bearer {token}"},
    )
    from api.Modules.TVDisplay.Models import TVDisplay
    from app import app as flask_app
    with flask_app.app_context():
        d = TVDisplay.query.first()
        assert d.orientation == "auto"
        assert d.theme == "light"


# ── write-side: regenerate-token ─────────────────────────────


def test_regenerate_token_rotates_value(client, test_store_id):
    _enable_tv_addon(test_store_id)
    token = _login_admin(client, test_store_id)
    headers = {"Authorization": f"Bearer {token}"}
    overview = client.get("/api/v2/tv-display/overview", headers=headers).get_json()
    old = overview["public_token"]
    resp = client.post(
        "/api/v2/tv-display/regenerate-token", json={}, headers=headers,
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["public_token"] != old
    assert body["public_url"] == f"/tv/{body['public_token']}"


# ── write-side: claim ────────────────────────────────────────


def test_claim_400_when_no_pending_code(client, test_store_id):
    _enable_tv_addon(test_store_id)
    token = _login_admin(client, test_store_id)
    resp = client.post(
        "/api/v2/tv-display/claim",
        json={"code": "ABCDEF"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_claim_400_when_code_too_short(client, test_store_id):
    _enable_tv_addon(test_store_id)
    token = _login_admin(client, test_store_id)
    resp = client.post(
        "/api/v2/tv-display/claim",
        json={"code": "AB"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


def test_claim_pairs_fire_tv_with_valid_code(client, test_store_id):
    """End-to-end: Fire TV initiates pairing → admin claims via JSON.
    Result: a TVPairing row whose device_token equals the pending row's,
    and the pending row is marked claimed."""
    from api.Modules.TVDisplay.Models import TVPairing, TVPendingPair
    from app import app as flask_app, db
    _enable_tv_addon(test_store_id)
    init = client.post("/api/tv-pair/init", json={"device_label": "Counter"})
    assert init.status_code == 200
    payload = init.get_json()
    code = payload["code"]
    device_token = payload["device_token"]
    token = _login_admin(client, test_store_id)
    resp = client.post(
        "/api/v2/tv-display/claim",
        json={"code": code},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204
    with flask_app.app_context():
        pending = db.session.query(TVPendingPair).filter_by(code=code).one()
        assert pending.claimed_at is not None
        pairing = (
            db.session.query(TVPairing)
              .filter(TVPairing.device_token == device_token)
              .one()
        )
        assert pairing.revoked_at is None


# ── write-side: revoke pairing ───────────────────────────────


def test_revoke_pairing_404_for_other_store(client, test_store_id):
    """Pairings on a sibling store's display must 404, not 403 — opaque
    tenancy. Mirrors the overview's 404-everything posture."""
    from api.Modules.TVDisplay.Models import TVDisplay, TVPairing
    from api.Modules.Tenancy.Models import Store
    from app import app as flask_app, db
    from datetime import datetime
    import secrets
    _enable_tv_addon(test_store_id)
    with flask_app.app_context():
        sibling = Store(name="Other", slug="other", email="o@e.com",
                        plan="basic", addons="tv_display")
        db.session.add(sibling); db.session.flush()
        d = TVDisplay(store_id=sibling.id,
                      public_token=secrets.token_urlsafe(24))
        db.session.add(d); db.session.flush()
        p = TVPairing(display_id=d.id, device_token="t",
                      device_label="x", paired_at=datetime.utcnow(),
                      last_seen_at=datetime.utcnow())
        db.session.add(p); db.session.commit()
        sibling_pairing_id = p.id
    token = _login_admin(client, test_store_id)
    resp = client.post(
        f"/api/v2/tv-display/pairings/{sibling_pairing_id}/revoke",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_revoke_pairing_marks_revoked_at(client, test_store_id):
    from api.Modules.TVDisplay.Models import TVDisplay, TVPairing
    from app import app as flask_app, db
    from datetime import datetime
    import secrets
    _enable_tv_addon(test_store_id)
    with flask_app.app_context():
        d = TVDisplay(store_id=test_store_id,
                      public_token=secrets.token_urlsafe(24))
        db.session.add(d); db.session.flush()
        p = TVPairing(display_id=d.id, device_token="ttt",
                      device_label="Counter",
                      paired_at=datetime.utcnow(),
                      last_seen_at=datetime.utcnow())
        db.session.add(p); db.session.commit()
        pairing_id = p.id
    token = _login_admin(client, test_store_id)
    resp = client.post(
        f"/api/v2/tv-display/pairings/{pairing_id}/revoke",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204
    with flask_app.app_context():
        p = db.session.get(TVPairing, pairing_id)
        assert p.revoked_at is not None


# ── write-side: country create + delete ──────────────────────


def test_create_country_uppercases_code_and_returns_201(client, test_store_id):
    _enable_tv_addon(test_store_id)
    token = _login_admin(client, test_store_id)
    resp = client.post(
        "/api/v2/tv-display/countries",
        json={"country_name": "Guatemala", "country_code": "gt",
              "mt_companies": "Maxi, Vigo"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["country_code"] == "GT"
    assert body["country_name"] == "Guatemala"
    from api.Modules.TVDisplay.Models import TVDisplayCountry
    from app import app as flask_app
    with flask_app.app_context():
        c = TVDisplayCountry.query.filter_by(country_name="Guatemala").one()
        assert c.country_code == "GT"


def test_create_country_rejects_blank_name(client, test_store_id):
    _enable_tv_addon(test_store_id)
    token = _login_admin(client, test_store_id)
    resp = client.post(
        "/api/v2/tv-display/countries",
        json={"country_name": "   ", "country_code": "MX",
              "mt_companies": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    # 422 from the explicit validator (after strip()) — distinguishes
    # the post-trim empty case from raw-empty payloads (which Pydantic
    # itself catches via min_length=1).
    assert resp.status_code == 422


def test_delete_country_cascades_banks_and_rates(client, test_store_id):
    _enable_tv_addon(test_store_id)
    _, country_id = _seed_country(test_store_id, mt_companies="Maxi,Vigo")
    _seed_bank_with_rates(country_id, "Bancomer", {"Maxi": 18.5})
    token = _login_admin(client, test_store_id)
    resp = client.delete(
        f"/api/v2/tv-display/countries/{country_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204
    from api.Modules.TVDisplay.Models import TVDisplayCountry, TVDisplayPayoutBank, TVDisplayRate
    from app import app as flask_app
    with flask_app.app_context():
        assert TVDisplayCountry.query.filter_by(id=country_id).first() is None
        assert TVDisplayPayoutBank.query.filter_by(country_id=country_id).count() == 0
        assert TVDisplayRate.query.count() == 0


def test_delete_country_404_for_other_store(client, test_store_id):
    _enable_tv_addon(test_store_id)
    from api.Modules.TVDisplay.Models import TVDisplay, TVDisplayCountry
    from api.Modules.Tenancy.Models import Store
    from app import app as flask_app, db
    import secrets
    with flask_app.app_context():
        sibling = Store(name="Sibling", slug="sib", email="s@e.com",
                        plan="basic", addons="tv_display")
        db.session.add(sibling); db.session.flush()
        d = TVDisplay(store_id=sibling.id,
                      public_token=secrets.token_urlsafe(24))
        db.session.add(d); db.session.flush()
        c = TVDisplayCountry(display_id=d.id, country_name="Honduras",
                              country_code="HN", sort_order=0,
                              mt_companies="")
        db.session.add(c); db.session.commit()
        sibling_country_id = c.id
    token = _login_admin(client, test_store_id)
    resp = client.delete(
        f"/api/v2/tv-display/countries/{sibling_country_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
