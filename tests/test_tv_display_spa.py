"""TV-display country editor SPA migration contract.

The /tv-display/countries/<id> Flask route accepts both GET and
POST. The GET 301s to /app/tv-display/countries/:countryId; the
POST handler stays live and serves the legacy form-submit
contract (banks add/delete, rate-matrix upsert) — the SPA renders
the editor and submits the form natively. No Jinja template is
retired in this PR yet: tv_display_country.html stops being
rendered (the GET branch redirects), but the file remains in the
repo until the public kiosk migration ships and we can land the
delete in one go.
"""


def _admin_session_login(client, store_id):
    from app import User, Store, db
    with client.application.app_context():
        u = User.query.filter_by(store_id=store_id, role="admin").first()
        uid = u.id
        s = db.session.get(Store, store_id)
        s.plan = "pro"
        s.billing_cycle = "monthly"
        # TV display addon must be active for the @_tv_required gate
        # to allow the route through. Add-ons live in a CSV column.
        existing = (s.addons or "").split(",")
        existing = [k.strip() for k in existing if k.strip()]
        if "tv_display" not in existing:
            existing.append("tv_display")
        s.addons = ",".join(existing)
        db.session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "admin"
        sess["store_id"] = store_id


def _seed_country(client, store_id):
    from app import (TVDisplay, TVDisplayCountry, db,
                     _ensure_tv_display)
    with client.application.app_context():
        from app import Store
        s = db.session.get(Store, store_id)
        display = _ensure_tv_display(s)
        c = TVDisplayCountry(
            display_id=display.id, country_name="Mexico",
            country_code="MX", mt_companies="intermex,maxi,barri",
            sort_order=10,
        )
        db.session.add(c); db.session.commit()
        return c.id


def test_country_editor_get_redirects_to_spa(client, test_store_id):
    _admin_session_login(client, test_store_id)
    cid = _seed_country(client, test_store_id)
    resp = client.get(
        f"/tv-display/countries/{cid}", follow_redirects=False,
    )
    assert resp.status_code == 301
    assert resp.headers["Location"] == f"/app/tv-display/countries/{cid}"


def test_country_editor_post_still_mutates(client, test_store_id):
    """The POST handler stays on Flask — the SPA submits the form
    natively. Verify a basic name change still round-trips."""
    from app import TVDisplayCountry, db
    _admin_session_login(client, test_store_id)
    cid = _seed_country(client, test_store_id)
    resp = client.post(
        f"/tv-display/countries/{cid}",
        data={
            "country_name": "México",
            "country_code": "MX",
            "mt_companies": "intermex,maxi",
        },
        follow_redirects=False,
    )
    # Redirects back to /tv-display (which 301s to /app/tv-display).
    assert resp.status_code in (301, 302, 303)
    with client.application.app_context():
        c = db.session.get(TVDisplayCountry, cid)
        assert c.country_name == "México"
        assert c.mt_companies == "intermex,maxi"
