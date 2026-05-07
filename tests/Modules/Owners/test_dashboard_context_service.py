"""Unit tests for Owners.Services.dashboard_context (PR 74)."""
from datetime import date, timedelta

from app import (
    DailyReport,
    Store,
    StoreOwnerLink,
    Transfer,
    User,
)


def _make_owner_with_stores(db, *, slug="ctx-owner",
                             num_stores=2):
    """Set up an owner User + N linked stores, return them."""
    User.query.filter_by(role="owner").delete()
    Store.query.delete()
    StoreOwnerLink.query.delete()
    db.commit()
    owner = User(
        username=f"{slug}@test.com",
        password_hash="x", role="owner",
        full_name="Test Owner", email=f"{slug}@test.com",
        store_id=1,  # nominal home store
    )
    db.add(owner); db.flush()
    stores = []
    for i in range(num_stores):
        s = Store(
            name=f"{slug}-store-{i}",
            slug=f"{slug}-store-{i}",
            plan="basic",
            email=f"{slug}-store-{i}@test.com",
        )
        db.add(s); db.flush()
        db.add(StoreOwnerLink(owner_id=owner.id, store_id=s.id))
        stores.append(s)
    db.flush()
    return owner, stores


def _add_transfer(db, store_id, *, send_date, send_amount=100.0,
                   company="Intermex", status="Sent",
                   fee=2.0):
    t = Transfer(
        store_id=store_id,
        send_date=send_date,
        company=company,
        sender_name="x",
        send_amount=send_amount,
        fee=fee,
        federal_tax=0.0,
        status=status,
    )
    db.add(t); db.flush()
    return t


# ── dashboard_context ──────────────────────────────────────


def test_dashboard_context_empty_umbrella_returns_zeros():
    """Owner with no linked stores → KPIs zero, empty lists."""
    from app import app as flask_app, db
    from api.Modules.Owners.Services import owner_dashboard_context
    with flask_app.app_context():
        owner, _ = _make_owner_with_stores(
            db.session, slug="empty-umbrella", num_stores=0,
        )
        ctx = owner_dashboard_context(db.session, owner, "month")
        assert ctx["store_count"] == 0
        assert ctx["agg_transfers"] == 0
        assert ctx["agg_volume"] == 0.0
        assert ctx["company_breakdown"] == []
        assert ctx["store_comparison"] == []
        # 30-day series always has 30 entries.
        assert len(ctx["series_labels"]) == 30
        # Return-check rollups are zero-shaped.
        assert ctx["rc_period"]["pending"] == 0.0
        assert len(ctx["rc_labels"]) == 12


def test_dashboard_context_aggregates_transfers_across_umbrella():
    from app import app as flask_app, db
    from api.Modules.Owners.Services import owner_dashboard_context
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        owner, stores = _make_owner_with_stores(
            db.session, slug="agg-test", num_stores=2,
        )
        today = date.today()
        # Two transfers in store A, one in store B
        _add_transfer(db.session, stores[0].id,
                      send_date=today, send_amount=100.0)
        _add_transfer(db.session, stores[0].id,
                      send_date=today, send_amount=200.0)
        _add_transfer(db.session, stores[1].id,
                      send_date=today, send_amount=300.0)
        db.session.commit()
        ctx = owner_dashboard_context(db.session, owner, "today")
        assert ctx["agg_transfers"] == 3
        assert ctx["agg_volume"] == 600.0


def test_dashboard_context_period_today_returns_today_window():
    from app import app as flask_app, db
    from api.Modules.Owners.Services import owner_dashboard_context
    with flask_app.app_context():
        owner, _ = _make_owner_with_stores(
            db.session, slug="period-today", num_stores=1,
        )
        ctx = owner_dashboard_context(db.session, owner, "today")
        assert ctx["period_start"] == ctx["period_end"]
        assert ctx["prev_label"] == "vs yesterday"


def test_dashboard_context_company_breakdown_sorted_by_volume():
    from app import app as flask_app, db
    from api.Modules.Owners.Services import owner_dashboard_context
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        owner, stores = _make_owner_with_stores(
            db.session, slug="company-sort", num_stores=1,
        )
        today = date.today()
        # Maxi: $50, Intermex: $500 → Intermex first.
        _add_transfer(db.session, stores[0].id,
                      send_date=today, send_amount=50.0,
                      company="Maxi")
        _add_transfer(db.session, stores[0].id,
                      send_date=today, send_amount=500.0,
                      company="Intermex")
        db.session.commit()
        ctx = owner_dashboard_context(db.session, owner, "today")
        names = [c["company"] for c in ctx["company_breakdown"]]
        assert names == ["Intermex", "Maxi"]


def test_dashboard_context_excludes_canceled_and_rejected():
    """Canceled / Rejected transfers must not pollute the volume."""
    from app import app as flask_app, db
    from api.Modules.Owners.Services import owner_dashboard_context
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        owner, stores = _make_owner_with_stores(
            db.session, slug="excl-test", num_stores=1,
        )
        today = date.today()
        _add_transfer(db.session, stores[0].id,
                      send_date=today, send_amount=100.0,
                      status="Sent")
        _add_transfer(db.session, stores[0].id,
                      send_date=today, send_amount=200.0,
                      status="Canceled")
        _add_transfer(db.session, stores[0].id,
                      send_date=today, send_amount=300.0,
                      status="Rejected")
        db.session.commit()
        ctx = owner_dashboard_context(db.session, owner, "today")
        assert ctx["agg_transfers"] == 1
        assert ctx["agg_volume"] == 100.0


def test_dashboard_context_30day_series_always_30_entries():
    from app import app as flask_app, db
    from api.Modules.Owners.Services import owner_dashboard_context
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        owner, stores = _make_owner_with_stores(
            db.session, slug="30day", num_stores=1,
        )
        # Just a single transfer; series should still be 30 bars.
        today = date.today()
        _add_transfer(db.session, stores[0].id,
                      send_date=today, send_amount=42.0)
        db.session.commit()
        ctx = owner_dashboard_context(db.session, owner, "today")
        assert len(ctx["series_labels"]) == 30
        assert len(ctx["series_volume"]) == 30
        assert len(ctx["series_count"]) == 30
        # Last entry is today.
        assert ctx["series_labels"][-1] == today.isoformat()


# ── locations_payload ─────────────────────────────────────


def test_locations_payload_empty_umbrella_returns_zero_total():
    from app import app as flask_app, db
    from api.Modules.Owners.Services import owner_locations_payload
    with flask_app.app_context():
        owner, _ = _make_owner_with_stores(
            db.session, slug="loc-empty", num_stores=0,
        )
        rows, total = owner_locations_payload(
            db.session, owner, "month", None,
        )
        assert rows == []
        assert total == 0


def test_locations_payload_returns_one_row_per_store():
    from app import app as flask_app, db
    from api.Modules.Owners.Services import owner_locations_payload
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        owner, stores = _make_owner_with_stores(
            db.session, slug="loc-three", num_stores=3,
        )
        rows, total = owner_locations_payload(
            db.session, owner, "month", None,
        )
        assert len(rows) == 3
        assert total == 3
        # Stores sorted by name.
        names = [r["store"].name for r in rows]
        assert names == sorted(names)


def test_locations_payload_filters_by_query():
    """Substring match on store name, case-insensitive."""
    from app import app as flask_app, db
    from api.Modules.Owners.Services import owner_locations_payload
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        owner, stores = _make_owner_with_stores(
            db.session, slug="loc-search", num_stores=3,
        )
        # Search for "store-1" → only matches store at index 1.
        rows, total = owner_locations_payload(
            db.session, owner, "month", "store-1",
        )
        # total still includes ALL stores in umbrella (3),
        # so the template can distinguish "no umbrella" from
        # "no search results".
        assert total == 3
        assert len(rows) == 1
        assert "store-1" in rows[0]["store"].name


def test_locations_payload_includes_transfer_stats():
    from app import app as flask_app, db
    from api.Modules.Owners.Services import owner_locations_payload
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        owner, stores = _make_owner_with_stores(
            db.session, slug="loc-stats", num_stores=1,
        )
        today = date.today()
        _add_transfer(db.session, stores[0].id,
                      send_date=today, send_amount=100.0)
        _add_transfer(db.session, stores[0].id,
                      send_date=today, send_amount=200.0)
        db.session.commit()
        rows, _ = owner_locations_payload(
            db.session, owner, "today", None,
        )
        assert len(rows) == 1
        row = rows[0]
        assert row["transfer_count"] == 2
        assert row["volume"] == 300.0


def test_locations_payload_companies_sorted_by_volume():
    """Per-store companies chips sorted by volume desc."""
    from app import app as flask_app, db
    from api.Modules.Owners.Services import owner_locations_payload
    with flask_app.app_context():
        Transfer.query.delete()
        db.session.commit()
        owner, stores = _make_owner_with_stores(
            db.session, slug="loc-co-sort", num_stores=1,
        )
        today = date.today()
        _add_transfer(db.session, stores[0].id,
                      send_date=today, send_amount=50.0,
                      company="Maxi")
        _add_transfer(db.session, stores[0].id,
                      send_date=today, send_amount=500.0,
                      company="Intermex")
        db.session.commit()
        rows, _ = owner_locations_payload(
            db.session, owner, "today", None,
        )
        companies = rows[0]["companies"]
        assert [c["company"] for c in companies] == ["Intermex", "Maxi"]


# ── legacy Flask wrappers ─────────────────────────────────


def test_legacy_dashboard_context_delegates():
    from app import app as flask_app, db
    from app import _owner_dashboard_context as legacy
    with flask_app.app_context():
        owner, _ = _make_owner_with_stores(
            db.session, slug="legacy-ctx", num_stores=0,
        )
        ctx = legacy(owner, "month")
        assert "agg_transfers" in ctx
        assert ctx["store_count"] == 0


def test_legacy_locations_payload_delegates():
    from app import app as flask_app, db
    from app import _owner_locations_payload as legacy
    with flask_app.app_context():
        owner, _ = _make_owner_with_stores(
            db.session, slug="legacy-loc", num_stores=0,
        )
        rows, total = legacy(owner, "month", None)
        assert rows == []
        assert total == 0
