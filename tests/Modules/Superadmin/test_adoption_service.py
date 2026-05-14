"""Unit tests for SA adoption services (PR 100):
bank_sync_adoption, tv_display_adoption, owner_adoption,
passkey_adoption.
"""
from datetime import date, datetime

from api.Modules.Auth.Models import Passkey
from api.Modules.BankSync.Models import StripeBankAccount
from api.Modules.Tenancy.Models import Store, StoreOwnerLink, User
from tests._app import db, db_session


_USER_COUNTER = 0
_ACCT_COUNTER = 0


def _add_store(db, *, slug, plan="basic", addons="",
               created_at=None):
    s = Store(name=slug, slug=slug, plan=plan, addons=addons,
              email=f"{slug}@example.com",
              created_at=created_at or datetime.utcnow())
    db.add(s); db.flush()
    return s


def _add_user(db, *, role="admin", store_id=None,
              full_name="X", username=None, email=""):
    global _USER_COUNTER
    _USER_COUNTER += 1
    u = User(
        store_id=store_id,
        username=username or f"sa-adopt-{_USER_COUNTER}",
        full_name=full_name,
        password_hash="hash",
        role=role,
        email=email,
    )
    db.add(u); db.flush()
    return u


def _add_account(db, store_id, *, last4="1234"):
    global _ACCT_COUNTER
    _ACCT_COUNTER += 1
    a = StripeBankAccount(
        store_id=store_id,
        stripe_account_id=f"fca_adopt_{_ACCT_COUNTER}",
        last4=last4,
    )
    db.add(a); db.flush()
    return a


def _add_passkey(db, user_id, *, credential_id_bytes):
    p = Passkey(
        user_id=user_id,
        credential_id=credential_id_bytes,
        public_key=b"\x00" * 64,
    )
    db.add(p); db.flush()
    return p


# ── bank_sync_adoption ──────────────────────────────────


def test_bank_sync_adoption_groups_by_plan():
    from tests._app import db
    from api.Modules.Superadmin.Services import bank_sync_adoption
    with db_session():
        db.session.query(StripeBankAccount).delete()
        db.session.query(Store).delete()
        db.session.commit()
        s_basic_conn = _add_store(db.session, slug="bsa-basic-c",
                                   plan="basic")
        _add_account(db.session, s_basic_conn.id)
        _add_store(db.session, slug="bsa-basic-nc", plan="basic")
        _add_store(db.session, slug="bsa-pro-nc", plan="pro")
        rows, totals = bank_sync_adoption(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        by_plan = {r["plan"]: r for r in rows}
        # Basic: 1 of 2 connected → 50%.
        assert by_plan["Basic"]["connected"] == 1
        assert by_plan["Basic"]["total"] == 2
        assert by_plan["Basic"]["rate_pct"] == 50.0
        # Pro: 0 of 1 connected → 0%.
        assert by_plan["Pro"]["rate_pct"] == 0.0
        # Total: 1 of 3 connected.
        assert totals["connected"] == 1
        assert totals["total"] == 3


def test_bank_sync_adoption_zero_total_no_divzero():
    from tests._app import db
    from api.Modules.Superadmin.Services import bank_sync_adoption
    with db_session():
        db.session.query(StripeBankAccount).delete()
        db.session.query(Store).delete()
        db.session.commit()
        rows, totals = bank_sync_adoption(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert rows == []
        assert totals["rate_pct"] == 0.0


# ── tv_display_adoption ─────────────────────────────────


def test_tv_display_adoption_filters_by_addons():
    """Only stores whose `addons` contains 'tv_display' surface."""
    from tests._app import db
    from api.Modules.Superadmin.Services import tv_display_adoption
    with db_session():
        db.session.query(Store).delete()
        db.session.commit()
        _add_store(db.session, slug="tvda-on", plan="basic",
                   addons="tv_display,referrals")
        _add_store(db.session, slug="tvda-off", plan="basic",
                   addons="referrals")
        _add_store(db.session, slug="tvda-blank", plan="basic",
                   addons="")
        rows, totals = tv_display_adoption(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert len(rows) == 1
        assert rows[0]["slug"] == "tvda-on"
        assert totals["count"] == 1
        assert totals["total_stores"] == 3


def test_tv_display_adoption_sorted_by_name():
    from tests._app import db
    from api.Modules.Superadmin.Services import tv_display_adoption
    with db_session():
        db.session.query(Store).delete()
        db.session.commit()
        _add_store(db.session, slug="tvda-z", plan="basic",
                   addons="tv_display")
        _add_store(db.session, slug="tvda-a", plan="basic",
                   addons="tv_display")
        rows, _ = tv_display_adoption(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert [r["slug"] for r in rows] == ["tvda-a", "tvda-z"]


# ── owner_adoption ─────────────────────────────────────


def test_owner_adoption_includes_only_multi_store_owners():
    """Owners with exactly 1 linked store are excluded — the
    report's purpose is to surface umbrella owners."""
    from tests._app import db
    from api.Modules.Superadmin.Services import owner_adoption
    with db_session():
        db.session.query(StoreOwnerLink).delete()
        db.session.query(Store).delete()
        db.session.commit()
        s1 = _add_store(db.session, slug="oa-1", plan="basic")
        s2 = _add_store(db.session, slug="oa-2", plan="basic")
        s3 = _add_store(db.session, slug="oa-3", plan="basic")
        owner_multi  = _add_user(db.session, role="owner",
                                 full_name="Multi Owner")
        owner_single = _add_user(db.session, role="owner",
                                 full_name="Single Owner")
        for s in (s1, s2):
            db.session.add(StoreOwnerLink(
                owner_id=owner_multi.id, store_id=s.id))
        db.session.add(StoreOwnerLink(
            owner_id=owner_single.id, store_id=s3.id))
        db.session.flush()
        rows, totals = owner_adoption(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert len(rows) == 1
        assert rows[0]["owner"] == "Multi Owner"
        assert rows[0]["stores"] == 2
        assert totals["owners"] == 1


def test_owner_adoption_empty_when_no_multi_store_owners():
    from tests._app import db
    from api.Modules.Superadmin.Services import owner_adoption
    with db_session():
        db.session.query(StoreOwnerLink).delete()
        db.session.commit()
        rows, totals = owner_adoption(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert rows == []
        assert totals == {"count": 0, "owners": 0}


# ── passkey_adoption ────────────────────────────────────


def test_passkey_adoption_returns_role_breakdown_and_rate():
    from tests._app import db
    from api.Modules.Superadmin.Services import passkey_adoption
    with db_session():
        db.session.query(Passkey).delete()
        db.session.commit()
        u_admin = _add_user(db.session, role="admin")
        u_emp   = _add_user(db.session, role="employee")
        _add_user(db.session, role="employee")  # no passkey
        _add_passkey(db.session, u_admin.id,
                     credential_id_bytes=b"cred-admin")
        _add_passkey(db.session, u_emp.id,
                     credential_id_bytes=b"cred-emp")
        rows, totals = passkey_adoption(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        by_role = {r["role"]: r["count"] for r in rows}
        assert by_role.get("Admin")    == 1
        assert by_role.get("Employee") == 1
        assert totals["users_with_passkey"] == 2
        assert totals["rate_pct"] > 0


def test_passkey_adoption_zero_users_returns_empty_rows():
    from tests._app import db
    from api.Modules.Superadmin.Services import passkey_adoption
    with db_session():
        db.session.query(Passkey).delete()
        db.session.commit()
        rows, totals = passkey_adoption(
            db.session, date(2026, 5, 1), date(2026, 5, 31),
        )
        assert rows == []
        assert totals["users_with_passkey"] == 0


# ── legacy wrappers ──────────────────────────────────────








