"""Announcement targeting (PR B).

Covers the store-scoped announcement feature end-to-end:

* visibility service — a targeted announcement is visible only to its
  target stores; a global one (no targeting rows) is visible to all,
  including a superadmin (store_id=None).
* controller — create persists targeting rows + echoes them; an
  unknown store id is a 422; list + toggle carry the targets; delete
  cleans up the join rows.
* /active endpoint — scopes banners to the viewer's store.
* retention purge — deleting a store drops its AnnouncementStore rows.
"""
from datetime import datetime, timedelta

from tests._app import db, db_session
from tests.conftest import login_superadmin


def _make_store(slug):
    from api.Modules.Tenancy.Models import Store
    s = Store(name=slug.title(), slug=slug, email=f"{slug}@test.com",
              plan="basic")
    db.session.add(s)
    db.session.flush()
    return s


def _add_announcement(message="hi", **kwargs):
    from api.Modules.Announcements.Models import Announcement
    a = Announcement(
        message=message,
        level=kwargs.pop("level", "info"),
        is_active=kwargs.pop("is_active", True),
        starts_at=kwargs.pop("starts_at", None),
        expires_at=kwargs.pop("expires_at", None),
    )
    db.session.add(a)
    db.session.flush()
    return a


def _target(ann_id, store_id):
    from api.Modules.Announcements.Models import AnnouncementStore
    db.session.add(
        AnnouncementStore(announcement_id=ann_id, store_id=store_id),
    )
    db.session.flush()


def _sa_headers(client):
    return {"Authorization": f"Bearer {login_superadmin(client)}"}


# ── visibility service ─────────────────────────────────────


def test_global_announcement_visible_to_every_store():
    from api.Modules.Announcements.Services import active_announcements
    with db_session():
        store_a = _make_store("vis-a")
        a = _add_announcement("global banner")
        # No AnnouncementStore rows → global.
        assert a in active_announcements(db.session, store_a.id)
        assert a in active_announcements(db.session, None)


def test_targeted_announcement_visible_only_to_target_store():
    from api.Modules.Announcements.Services import active_announcements
    with db_session():
        store_a = _make_store("vis-target")
        store_b = _make_store("vis-other")
        a = _add_announcement("just for A")
        _target(a.id, store_a.id)
        assert a in active_announcements(db.session, store_a.id)
        assert a not in active_announcements(db.session, store_b.id)


def test_targeted_announcement_hidden_from_superadmin_none_scope():
    """A store-targeted banner isn't part of the superadmin's own
    chrome (store_id=None) — they still manage it from the CRUD list."""
    from api.Modules.Announcements.Services import active_announcements
    with db_session():
        store_a = _make_store("vis-sa")
        a = _add_announcement("targeted, not global")
        _target(a.id, store_a.id)
        assert a not in active_announcements(db.session, None)


def test_multi_store_target_visible_to_each():
    from api.Modules.Announcements.Services import active_announcements
    with db_session():
        s1 = _make_store("vis-m1")
        s2 = _make_store("vis-m2")
        s3 = _make_store("vis-m3")
        a = _add_announcement("for 1 and 2")
        _target(a.id, s1.id)
        _target(a.id, s2.id)
        assert a in active_announcements(db.session, s1.id)
        assert a in active_announcements(db.session, s2.id)
        assert a not in active_announcements(db.session, s3.id)


# ── controller: create ─────────────────────────────────────


def test_create_global_when_no_targets(client):
    resp = client.post(
        "/api/v2/announcements",
        json={"message": "everyone sees this"},
        headers=_sa_headers(client),
    )
    assert resp.status_code == 201
    body = resp.json()["announcement"]
    assert body["target_store_ids"] == []
    assert body["target_store_names"] == []


def test_create_with_targets_persists_and_echoes(client, test_store_id):
    resp = client.post(
        "/api/v2/announcements",
        json={
            "message": "scoped banner",
            "target_store_ids": [test_store_id],
        },
        headers=_sa_headers(client),
    )
    assert resp.status_code == 201
    body = resp.json()["announcement"]
    assert body["target_store_ids"] == [test_store_id]
    assert len(body["target_store_names"]) == 1
    # Row actually written.
    from api.Modules.Announcements.Models import AnnouncementStore
    with db_session():
        n = (
            db.session.query(AnnouncementStore)
              .filter_by(announcement_id=body["id"])
              .count()
        )
        assert n == 1


def test_create_rejects_unknown_store_id(client):
    resp = client.post(
        "/api/v2/announcements",
        json={"message": "bad target", "target_store_ids": [9_999_999]},
        headers=_sa_headers(client),
    )
    assert resp.status_code == 422


def test_create_dedupes_repeated_store_ids(client, test_store_id):
    resp = client.post(
        "/api/v2/announcements",
        json={
            "message": "dupe target",
            "target_store_ids": [test_store_id, test_store_id],
        },
        headers=_sa_headers(client),
    )
    assert resp.status_code == 201
    body = resp.json()["announcement"]
    assert body["target_store_ids"] == [test_store_id]


# ── controller: list / delete ──────────────────────────────


def test_list_carries_targets(client, test_store_id):
    with db_session():
        a = _add_announcement("listed")
        _target(a.id, test_store_id)
        db.session.commit()
        ann_id = a.id
    resp = client.get("/api/v2/announcements", headers=_sa_headers(client))
    assert resp.status_code == 200
    row = next(r for r in resp.json()["rows"] if r["id"] == ann_id)
    assert row["target_store_ids"] == [test_store_id]


def test_delete_clears_targeting_rows(client, test_store_id):
    from api.Modules.Announcements.Models import AnnouncementStore
    with db_session():
        a = _add_announcement("to be deleted")
        _target(a.id, test_store_id)
        db.session.commit()
        ann_id = a.id
    resp = client.delete(
        f"/api/v2/announcements/{ann_id}", headers=_sa_headers(client),
    )
    assert resp.status_code == 204
    with db_session():
        assert (
            db.session.query(AnnouncementStore)
              .filter_by(announcement_id=ann_id)
              .count()
        ) == 0


# ── /active endpoint scoping ───────────────────────────────


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


def test_active_excludes_banner_targeted_at_other_store(client, test_store_id):
    token = _login_admin(client, test_store_id)
    with db_session():
        other = _make_store("active-other")
        a = _add_announcement("only for the other store")
        _target(a.id, other.id)
        db.session.commit()
        ann_id = a.id
    resp = client.get(
        "/api/v2/announcements/active",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.json()["rows"]]
    assert ann_id not in ids


def test_active_includes_banner_targeted_at_my_store(client, test_store_id):
    token = _login_admin(client, test_store_id)
    with db_session():
        a = _add_announcement("for my store")
        _target(a.id, test_store_id)
        db.session.commit()
        ann_id = a.id
    resp = client.get(
        "/api/v2/announcements/active",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.json()["rows"]]
    assert ann_id in ids


# ── retention purge ────────────────────────────────────────


def test_purge_removes_announcement_store_rows():
    """Deleting a store must drop its AnnouncementStore rows
    (invariant #4) — the announcement itself survives."""
    from api.Modules.Announcements.Models import Announcement, AnnouncementStore
    from api.Modules.Billing.Services import purge_expired_stores
    from api.Modules.Tenancy.Models import Store
    with db_session():
        s = Store(
            name="Purge-Target", slug="purge-target-ann",
            plan="inactive", email="purge-ann@test.com",
            data_retention_until=datetime.utcnow() - timedelta(days=1),
        )
        db.session.add(s)
        db.session.flush()
        a = _add_announcement("survives the purge")
        _target(a.id, s.id)
        db.session.commit()
        sid, ann_id = s.id, a.id

        purged = purge_expired_stores(db.session)
        assert purged >= 1
        assert db.session.get(Store, sid) is None
        # Targeting rows for the dead store are gone …
        assert (
            db.session.query(AnnouncementStore)
              .filter_by(store_id=sid)
              .count()
        ) == 0
        # … but the announcement row itself survives (it's global-ish
        # now — no remaining targets).
        assert db.session.get(Announcement, ann_id) is not None
