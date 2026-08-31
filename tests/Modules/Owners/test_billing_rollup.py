"""Owner billing rollup — Service math + HTTP contract.

  GET /api/v2/owner/billing
"""
from datetime import timedelta

from api.Core.Clock import utc_now
from tests._app import db, db_session


def _make_owner(*, username="boss-bill@x.com", password="ownerpass1!"):
    """Owner + their home store, linked into the umbrella the way
    owner signup does — the rollup reads StoreOwnerLink, so an
    unlinked home store would be invisible to it."""
    from api.Modules.Tenancy.Models import Store, StoreOwnerLink, User
    slug = username.split("@")[0]
    s = Store(name=f"{slug} Home", slug=f"{slug}-home",
              email=username, plan="basic", billing_cycle="monthly")
    db.session.add(s); db.session.commit()
    u = User(
        store_id=s.id, username=username, full_name="Boss",
        email=username, role="owner",
    )
    u.set_password(password)
    db.session.add(u); db.session.commit()
    db.session.add(StoreOwnerLink(owner_id=u.id, store_id=s.id))
    db.session.commit()
    return u.id, s.id, password


def _link_store(owner_id, *, name, slug, **kw):
    from api.Modules.Tenancy.Models import Store, StoreOwnerLink
    s = Store(name=name, slug=slug, email=f"{slug}@x.com", **kw)
    db.session.add(s); db.session.commit()
    db.session.add(StoreOwnerLink(owner_id=owner_id, store_id=s.id))
    db.session.commit()
    return s.id


def _login_owner(client, username, password):
    resp = client.post(
        "/api/v2/auth/login-cross-store",
        json={"username": username, "password": password},
    )
    return resp.get_json()["access_token"]


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


# ── Auth gating ─────────────────────────────────────────────


def test_owner_billing_requires_jwt(client):
    assert client.get("/api/v2/owner/billing").status_code == 401


def test_owner_billing_rejects_store_admin(client, test_store_id):
    """A store admin sees their own store's subscription page, not
    the umbrella rollup."""
    token = _login_admin(client, test_store_id)
    resp = client.get(
        "/api/v2/owner/billing",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── Service math ────────────────────────────────────────────


def test_rollup_is_empty_for_an_owner_with_no_stores():
    """A brand-new owner account is a legitimate state, not an
    error."""
    from api.Modules.Owners.Services import owner_billing_rollup
    with db_session():
        rows, totals = owner_billing_rollup(db.session, [])
        assert rows == []
        assert totals["stores"] == 0
        assert totals["monthly_cost"] == 0.0
        assert totals["attention_count"] == 0


def test_rollup_normalises_yearly_plans_to_a_monthly_figure():
    """Stores on different cadences have to be summable — a $450/yr
    Pro store contributes $37.50/mo, not $450."""
    from api.Modules.Owners.Services import owner_billing_rollup
    with db_session():
        owner_id, home_id, _ = _make_owner(username="boss-yr@x.com")
        yearly_id = _link_store(
            owner_id, name="Yearly Pro", slug="yr-pro",
            plan="pro", billing_cycle="yearly",
        )
        rows, totals = owner_billing_rollup(
            db.session, [home_id, yearly_id],
        )
        by_id = {r["store_id"]: r for r in rows}
        assert by_id[yearly_id]["monthly_cost"] == round(450 / 12, 2)
        assert by_id[yearly_id]["plan_label"] == "Pro (yearly)"
        assert by_id[yearly_id]["plan_price_label"] == "$450 / year"
        # Home store is Basic monthly at $35.
        assert by_id[home_id]["monthly_cost"] == 35.0
        assert totals["monthly_cost"] == round(35 + 450 / 12, 2)
        assert totals["paid_stores"] == 2


def test_rollup_counts_plan_states_separately():
    from api.Modules.Owners.Services import owner_billing_rollup
    with db_session():
        owner_id, home_id, _ = _make_owner(username="boss-mix@x.com")
        trial_id = _link_store(
            owner_id, name="Trialer", slug="mix-trial", plan="trial",
            trial_ends_at=utc_now() + timedelta(days=30),
        )
        dead_id = _link_store(
            owner_id, name="Lapsed", slug="mix-dead", plan="inactive",
        )
        _, totals = owner_billing_rollup(
            db.session, [home_id, trial_id, dead_id],
        )
        assert totals["stores"] == 3
        assert totals["paid_stores"] == 1
        assert totals["trial_stores"] == 1
        assert totals["inactive_stores"] == 1
        # Only the paid store costs anything.
        assert totals["monthly_cost"] == 35.0


def test_rollup_flags_and_sorts_stores_needing_attention():
    """Stores the owner has to act on float to the top, worst first;
    healthy stores keep alphabetical order."""
    from api.Modules.Owners.Services import owner_billing_rollup
    with db_session():
        owner_id, home_id, _ = _make_owner(username="boss-att@x.com")
        ending_id = _link_store(
            owner_id, name="Zed Ending", slug="att-ending", plan="trial",
            trial_ends_at=utc_now() + timedelta(days=2),
        )
        purging_id = _link_store(
            owner_id, name="Purging", slug="att-purge", plan="inactive",
            # +1h of slack: data_retention_days_left truncates the
            # remainder, so an exact 10-day deadline reads back as 9.
            data_retention_until=utc_now() + timedelta(days=10, hours=1),
        )
        rows, totals = owner_billing_rollup(
            db.session, [home_id, ending_id, purging_id],
        )
        # Retention outranks everything — it's the only irreversible
        # state — then the ending trial, then the healthy store.
        assert [r["store_id"] for r in rows] == [
            purging_id, ending_id, home_id,
        ]
        assert rows[0]["attention"] == "retention"
        assert rows[0]["retention_days_left"] == 10
        assert rows[1]["attention"] == "trial_ending"
        assert rows[2]["attention"] == ""
        assert totals["attention_count"] == 2


def test_rollup_includes_addon_cost_separately_from_plan():
    """Add-ons bill monthly regardless of the plan's cadence, so they
    are reported as their own line rather than folded into the plan
    price."""
    from api.Modules.Billing.Services import ADDONS_CATALOG
    from api.Modules.Owners.Services import owner_billing_rollup
    from api.Modules.Tenancy.Models import Store
    key, addon = next(iter(ADDONS_CATALOG.items()))
    with db_session():
        _owner_id, home_id, _ = _make_owner(username="boss-add@x.com")
        store = db.session.get(Store, home_id)
        store.addons = key
        db.session.commit()
        rows, totals = owner_billing_rollup(db.session, [home_id])
        expected = round(int(addon.get("price_cents", 0)) / 100, 2)
        assert rows[0]["addon_count"] == 1
        assert rows[0]["addon_monthly_cost"] == expected
        # Plan price is unchanged by the add-on.
        assert rows[0]["monthly_cost"] == 35.0
        assert totals["addon_monthly_cost"] == expected


# ── HTTP contract ───────────────────────────────────────────


def test_owner_billing_returns_every_umbrella_store(client):
    with db_session():
        owner_id, home_id, pw = _make_owner(username="boss-http@x.com")
        other_id = _link_store(
            owner_id, name="Second Site", slug="http-second",
            plan="pro", billing_cycle="monthly",
        )
    token = _login_owner(client, "boss-http@x.com", pw)
    resp = client.get(
        "/api/v2/owner/billing",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    ids = {r["store_id"] for r in body["rows"]}
    assert {home_id, other_id} <= ids
    assert body["totals"]["stores"] == len(body["rows"])
    # $35 Basic + $45 Pro.
    assert body["totals"]["monthly_cost"] == 80.0


def test_owner_billing_excludes_unlinked_stores(client):
    """A store outside the umbrella never appears, even though the
    owner is authenticated."""
    from api.Modules.Tenancy.Models import Store
    with db_session():
        _, _, pw = _make_owner(username="boss-iso@x.com")
        stranger = Store(
            name="Not Mine", slug="iso-stranger",
            email="iso@x.com", plan="pro",
        )
        db.session.add(stranger); db.session.commit()
        stranger_id = stranger.id
    token = _login_owner(client, "boss-iso@x.com", pw)
    resp = client.get(
        "/api/v2/owner/billing",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    ids = {r["store_id"] for r in resp.get_json()["rows"]}
    assert stranger_id not in ids
