"""Lottery module (P1-6): games, pack lifecycle, day-close counts.

The invariants under test:
  * pack lifecycle received → active → settled/returned only,
  * counts only on active packs, never backwards, never past the
    pack end, never above an already-recorded later count,
  * sold = closing − previous reference (previous day's count, or
    opening_ticket on the first counted day),
  * day summary flags active packs with no count (shrinkage nag),
  * cashiers (employees) can enter counts but not run lifecycle,
  * module flag bundles: lottery ON for cstore, OFF for msb_hybrid.
"""
from tests._app import db, db_session
from tests.conftest import login_admin, make_employee_client


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _admin(client, test_store_id):
    return _headers(login_admin(client, test_store_id))


def _mk_game(client, h, game_number="2417", price=5.0, per_pack=60):
    resp = client.post("/api/v2/lottery/games", headers=h, json={
        "game_number": game_number, "name": f"Test Game {game_number}",
        "ticket_price": price, "tickets_per_pack": per_pack,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["game"]


def _mk_active_pack(client, h, game_id, pack_number="0001",
                    opening=0, day="2026-08-01"):
    resp = client.post("/api/v2/lottery/packs", headers=h, json={
        "game_id": game_id, "pack_number": pack_number,
        "received_on": day,
    })
    assert resp.status_code == 201, resp.text
    pack = resp.json()["pack"]
    resp = client.post(
        f"/api/v2/lottery/packs/{pack['id']}/activate", headers=h,
        json={"activated_on": day, "opening_ticket": opening,
              "bin_number": "3"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["pack"]


# ── Games ──────────────────────────────────────────────────


def test_game_crud_roundtrip(client, test_store_id):
    h = _admin(client, test_store_id)
    game = _mk_game(client, h)
    assert game["ticket_price"] == 5.0
    listed = client.get("/api/v2/lottery/games", headers=h).json()["games"]
    assert [g["game_number"] for g in listed] == ["2417"]

    resp = client.put(
        f"/api/v2/lottery/games/{game['id']}", headers=h,
        json={"ticket_price": 10.0, "is_active": False},
    )
    assert resp.status_code == 200
    assert resp.json()["game"]["ticket_price"] == 10.0
    # Inactive games drop out of the default list.
    assert client.get(
        "/api/v2/lottery/games", headers=h,
    ).json()["games"] == []
    assert len(client.get(
        "/api/v2/lottery/games?include_inactive=1", headers=h,
    ).json()["games"]) == 1


def test_duplicate_game_number_conflicts(client, test_store_id):
    h = _admin(client, test_store_id)
    _mk_game(client, h, "111")
    resp = client.post("/api/v2/lottery/games", headers=h, json={
        "game_number": "111", "name": "Dup", "ticket_price": 1,
        "tickets_per_pack": 100,
    })
    assert resp.status_code == 409


# ── Pack lifecycle ─────────────────────────────────────────


def test_pack_lifecycle_and_guards(client, test_store_id):
    h = _admin(client, test_store_id)
    game = _mk_game(client, h)
    pack = _mk_active_pack(client, h, game["id"])
    assert pack["status"] == "active"
    assert pack["bin_number"] == "3"

    # Activating an already-active pack → 409.
    resp = client.post(
        f"/api/v2/lottery/packs/{pack['id']}/activate", headers=h,
        json={"activated_on": "2026-08-02"},
    )
    assert resp.status_code == 409

    # Settle it; settling again → 409.
    resp = client.post(
        f"/api/v2/lottery/packs/{pack['id']}/settle", headers=h,
        json={"on": "2026-08-03"},
    )
    assert resp.status_code == 200
    assert resp.json()["pack"]["status"] == "settled"
    resp = client.post(
        f"/api/v2/lottery/packs/{pack['id']}/settle", headers=h,
        json={"on": "2026-08-03"},
    )
    assert resp.status_code == 409

    # A settled pack can't be returned to the state.
    resp = client.post(
        f"/api/v2/lottery/packs/{pack['id']}/return", headers=h,
        json={"on": "2026-08-04"},
    )
    assert resp.status_code == 409


def test_status_filter_and_duplicate_pack(client, test_store_id):
    h = _admin(client, test_store_id)
    game = _mk_game(client, h)
    _mk_active_pack(client, h, game["id"], "0001")
    resp = client.post("/api/v2/lottery/packs", headers=h, json={
        "game_id": game["id"], "pack_number": "0001",
        "received_on": "2026-08-01",
    })
    assert resp.status_code == 409
    active = client.get(
        "/api/v2/lottery/packs?status=active", headers=h,
    ).json()["packs"]
    assert len(active) == 1


# ── Day counts ─────────────────────────────────────────────


def test_day_count_math_across_days(client, test_store_id):
    """Day 1: opening 0 → close 12 (12 sold). Day 2: close 30
    (18 sold). $5 tickets → $60 then $90."""
    h = _admin(client, test_store_id)
    game = _mk_game(client, h, price=5.0, per_pack=60)
    pack = _mk_active_pack(client, h, game["id"])

    day1 = client.post(
        "/api/v2/lottery/day/2026-08-02/counts", headers=h,
        json={"pack_id": pack["id"], "closing_ticket": 12},
    ).json()
    assert day1["total_sold"] == 12
    assert day1["total_value"] == 60.0
    assert day1["uncounted_active_packs"] == 0

    day2 = client.post(
        "/api/v2/lottery/day/2026-08-03/counts", headers=h,
        json={"pack_id": pack["id"], "closing_ticket": 30},
    ).json()
    assert day2["rows"][0]["sold"] == 18
    assert day2["rows"][0]["previous_reference"] == 12
    assert day2["total_value"] == 90.0

    # Re-submitting the same day upserts instead of stacking.
    again = client.post(
        "/api/v2/lottery/day/2026-08-03/counts", headers=h,
        json={"pack_id": pack["id"], "closing_ticket": 31},
    ).json()
    assert again["rows"][0]["sold"] == 19


def test_count_validation_guards(client, test_store_id):
    h = _admin(client, test_store_id)
    game = _mk_game(client, h, per_pack=60)
    pack = _mk_active_pack(client, h, game["id"], opening=10)

    # Backwards vs opening ticket → 409.
    resp = client.post(
        "/api/v2/lottery/day/2026-08-02/counts", headers=h,
        json={"pack_id": pack["id"], "closing_ticket": 5},
    )
    assert resp.status_code == 409
    # Past the end of the pack → 409.
    resp = client.post(
        "/api/v2/lottery/day/2026-08-02/counts", headers=h,
        json={"pack_id": pack["id"], "closing_ticket": 61},
    )
    assert resp.status_code == 409
    # Valid, then an EARLIER day above the later count → 409.
    assert client.post(
        "/api/v2/lottery/day/2026-08-05/counts", headers=h,
        json={"pack_id": pack["id"], "closing_ticket": 30},
    ).status_code == 200
    resp = client.post(
        "/api/v2/lottery/day/2026-08-04/counts", headers=h,
        json={"pack_id": pack["id"], "closing_ticket": 35},
    )
    assert resp.status_code == 409


def test_uncounted_active_pack_flagged(client, test_store_id):
    h = _admin(client, test_store_id)
    game = _mk_game(client, h)
    _mk_active_pack(client, h, game["id"], "0001")
    _mk_active_pack(client, h, game["id"], "0002")
    summary = client.get(
        "/api/v2/lottery/day/2026-08-02", headers=h,
    ).json()
    assert summary["uncounted_active_packs"] == 2
    assert all(r["counted"] is False for r in summary["rows"])


# ── Permissions ────────────────────────────────────────────


def test_employee_can_count_but_not_manage(client, test_store_id):
    admin_h = _admin(client, test_store_id)
    game = _mk_game(client, admin_h)
    pack = _mk_active_pack(client, admin_h, game["id"])

    emp_client, emp_jwt = make_employee_client(test_store_id)
    emp_h = _headers(emp_jwt)
    # Counts: allowed (lottery.create).
    resp = client.post(
        "/api/v2/lottery/day/2026-08-02/counts", headers=emp_h,
        json={"pack_id": pack["id"], "closing_ticket": 3},
    )
    assert resp.status_code == 200, resp.text
    # Lifecycle: denied (lottery.update is admin-only).
    resp = client.post(
        f"/api/v2/lottery/packs/{pack['id']}/settle", headers=emp_h,
        json={"on": "2026-08-02"},
    )
    assert resp.status_code == 403
    resp = client.post("/api/v2/lottery/games", headers=emp_h, json={
        "game_number": "999", "name": "Nope", "ticket_price": 1,
        "tickets_per_pack": 10,
    })
    assert resp.status_code == 403


# ── Module flag bundle ─────────────────────────────────────


def test_lottery_flag_follows_business_type(client, test_store_id):
    from api.Modules.Billing.Services.feature_flags import (
        store_feature_enabled,
    )
    from api.Modules.Tenancy.Models import Store
    with db_session():
        store = db.session.get(Store, test_store_id)
        store.business_type = "cstore"
        db.session.commit()
        assert store_feature_enabled(
            db.session, store, "module_lottery",
        ) is True
        store.business_type = "msb_hybrid"
        db.session.commit()
        assert store_feature_enabled(
            db.session, store, "module_lottery",
        ) is False


def test_session_status_carries_lottery_flag(client, test_store_id):
    from api.Modules.Tenancy.Models import Store
    with db_session():
        db.session.get(Store, test_store_id).business_type = "cstore"
        db.session.commit()
    token = login_admin(client, test_store_id)
    body = client.get(
        "/api/v2/auth/session-status", headers=_headers(token),
    ).json()
    assert "module_lottery" in body["features"]
