"""Shared helpers for the legacy TV-display test files.

The TV-display admin landing's write actions (settings, regenerate-
token, claim, country create/delete) moved to JSON endpoints under
/api/v2/tv-display/* in C-5a. The country *editor*
(/tv-display/countries/<id> POST) and the public kiosk (/tv/<token>)
remain on Flask until C-5b/c.

These helpers paper over the migration so existing tests that need to
seed a country (or a country + bank + rates) don't have to re-litigate
the form-vs-JSON contract themselves.
"""
from __future__ import annotations
from tests._app import db


def admin_jwt(client, store_id: int, *, username: str = "admin@test.com",
              password: str = "testpass123!") -> str:
    """Mint a Bearer JWT for the seeded admin via the SPA login. The
    /api/v2/tv-display/* write endpoints all require this dependency."""
    return client.post(
        "/api/v2/auth/login",
        json={"username": username, "password": password,
              "store_id": store_id},
    ).get_json()["access_token"]


def ensure_display(client, store_id: int, jwt: str | None = None) -> int:
    """Land on the overview endpoint once so _ensure_display creates
    the TVDisplay row. Mirrors the legacy `_ensure_tv_display` lazy-
    create the deleted /tv-display GET used to do."""
    if jwt is None:
        jwt = admin_jwt(client, store_id)
    client.get(
        "/api/v2/tv-display/overview",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    from api.Modules.TVDisplay.Models import TVDisplay
    from tests._app import app as flask_app, db
    with flask_app.app_context():
        return db.session.query(TVDisplay).filter_by(
            store_id=store_id).one().id


def create_country(client, store_id: int, *, country_name: str,
                    country_code: str = "", mt_companies: str = "",
                    jwt: str | None = None) -> int:
    """Create a country header via the new JSON endpoint and return
    its id. Pairs with `ensure_display` for tests that previously did
    the two-step `GET /tv-display` + `POST /tv-display/countries/new`
    Flask flow."""
    if jwt is None:
        jwt = admin_jwt(client, store_id)
    resp = client.post(
        "/api/v2/tv-display/countries",
        json={"country_name": country_name,
              "country_code": country_code,
              "mt_companies": mt_companies},
        headers={"Authorization": f"Bearer {jwt}"},
    )
    return resp.get_json()["id"]
