"""Provision (or refresh) the Amazon Appstore reviewer test account.

The DineroBook TV Fire TV app gates pairing on the ``tv_display``
add-on. Amazon's reviewers don't have a paid subscription, so
without a comped account they'd hit the addon gate and fail
review with "couldn't pair." This script provisions (or refreshes)
a single sandbox store + employee user with the addon comped and
a few sample rates pre-seeded, so the reviewer:

  1. Logs in at ``/login/amazon-reviewer`` with the printed creds.
  2. Lands on /dashboard, navigates to TV Display in the sidebar.
  3. Clicks "Generate code" on /tv-display.
  4. Pairs the test Fire TV — sees a populated rate board.

Invocation::

    python -m scripts.seed_amazon_reviewer
    python -m scripts.seed_amazon_reviewer --password VeryStrong-Pass
    python -m scripts.seed_amazon_reviewer --keep-data

Idempotent: re-running rotates the password, refreshes plan +
addons, and reseeds the sample data unless ``--keep-data`` is set.

Replaces the legacy ``flask seed-amazon-reviewer`` CLI; no Flask
boot. Run on the Render shell before submitting a Fire TV app
update for review.
"""
from __future__ import annotations

import argparse
import os
import secrets
import sys
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from api.Core.Database import SessionLocal
from api.Core.Observability import init_logging, init_sentry


# Sample rate matrices for the seeded display. Two countries with
# realistic-looking data so the reviewer immediately sees a useful
# rate board instead of "No country sections yet." Numbers are
# illustrative; refreshable via re-running the command.
_REVIEWER_SAMPLE_DATA = [
    {
        "country_code": "MX",
        "country_name": "Mexico",
        "mt_companies": "Maxi, Cibao, Vigo",
        "banks": [
            {"name": "Bancomer", "rates": {"Maxi": 18.36, "Cibao": 18.07, "Vigo": 18.51}},
            {"name": "Banorte",  "rates": {"Maxi": 18.41, "Cibao": 18.12, "Vigo": 18.56}},
            {"name": "Santander", "rates": {"Maxi": 18.46, "Cibao": 18.17, "Vigo": 18.61}},
        ],
    },
    {
        "country_code": "GT",
        "country_name": "Guatemala",
        "mt_companies": "Maxi, Vigo",
        "banks": [
            {"name": "Banco Industrial", "rates": {"Maxi": 7.52, "Vigo": 7.59}},
            {"name": "Banrural",         "rates": {"Maxi": 7.50, "Vigo": 7.57}},
        ],
    },
]


_REVIEWER_SLUG = "amazon-reviewer"
_REVIEWER_USERNAME = "amazon-review@dinerobook.com"
_REVIEWER_STORE_NAME = "Amazon Reviewer Sandbox"


def _ensure_schema() -> None:
    """Mirror of ``scripts/purge_expired_stores._ensure_schema``."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    from api.Core.Database.session import _get_engine

    engine = _get_engine()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", str(engine.url))
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        table_names = set(inspect(connection).get_table_names())
        has_alembic = "alembic_version" in table_names
        has_app_tables = bool(table_names - {"alembic_version"})
        if not has_alembic and has_app_tables:
            command.stamp(cfg, "head")
        else:
            command.upgrade(cfg, "head")


def _ensure_tv_display(session: Session, store):
    """Get-or-create the store's ``TVDisplay`` row + initial token.

    Mirrors ``app.py``'s ``_ensure_tv_display`` but takes a session
    parameter so the standalone script doesn't depend on the Flask
    request-scoped ``db.session``.
    """
    from api.Modules.TVDisplay.Models import TVDisplay
    d = session.query(TVDisplay).filter_by(store_id=store.id).first()
    if d is None:
        d = TVDisplay(
            store_id=store.id,
            public_token=secrets.token_urlsafe(24),
        )
        session.add(d)
        session.commit()
    return d


def run(
    session: Session,
    *,
    password: str | None = None,
    keep_data: bool = False,
) -> dict:
    """Seed (or refresh) the reviewer account. Returns a dict with the
    print-ready credentials + counts."""
    from api.Modules.Tenancy.Models import Store, User
    from api.Modules.TVDisplay.Models import (
        TVDisplayCountry, TVDisplayPayoutBank, TVDisplayRate,
    )

    # 1. Find or create the store.
    store = session.query(Store).filter_by(slug=_REVIEWER_SLUG).first()
    created_store = False
    if store is None:
        store = Store(
            name=_REVIEWER_STORE_NAME, slug=_REVIEWER_SLUG,
            email=_REVIEWER_USERNAME,
            plan="basic",
            trial_ends_at=datetime.utcnow() + timedelta(days=3650),
            grace_ends_at=datetime.utcnow() + timedelta(days=3650),
            is_active=True,
        )
        session.add(store)
        session.flush()
        created_store = True

    # Force-comp the plan + addon every run — superadmin may have
    # toggled them off, or a previous run may have set partial state.
    store.plan = "basic"
    store.addons = "tv_display"
    store.is_active = True

    # 2. Find or create the employee user.
    user = session.query(User).filter_by(
        store_id=store.id, username=_REVIEWER_USERNAME).first()
    created_user = False
    if user is None:
        user = User(
            store_id=store.id, username=_REVIEWER_USERNAME,
            full_name="Amazon Appstore Reviewer",
            role="employee",
            is_active=True,
        )
        session.add(user)
        created_user = True
    else:
        # Force role + active in case a prior run / superadmin left
        # the row in a weird state.
        user.role = "employee"
        user.is_active = True

    # 3. Set password — operator-supplied or freshly random.
    if password is None:
        password = secrets.token_urlsafe(12)
    elif len(password) < 12:
        raise ValueError("--password must be at least 12 chars.")
    user.set_password(password)

    session.commit()

    # 4. Ensure the TVDisplay row exists.
    display = _ensure_tv_display(session, store)

    # 5. Seed sample rate data unless the operator opted out OR data
    #    already exists.
    has_existing_data = (
        session.query(TVDisplayCountry).filter_by(
            display_id=display.id).first()
    ) is not None
    seeded_counts = {"countries": 0, "banks": 0, "rates": 0}
    if not (keep_data and has_existing_data):
        # Wipe in chain order so FKs don't reject the deletes.
        # ``synchronize_session='fetch'`` so SQLAlchemy properly
        # removes the deleted rows from the session identity map —
        # otherwise re-inserts on the same PKs (SQLite reuses freed
        # auto-increment PKs aggressively) trip a collision warning.
        existing_countries = session.query(TVDisplayCountry).filter_by(
            display_id=display.id).all()
        for c in existing_countries:
            existing_banks = session.query(TVDisplayPayoutBank).filter_by(
                country_id=c.id).all()
            for b in existing_banks:
                session.query(TVDisplayRate).filter_by(bank_id=b.id).delete(
                    synchronize_session="fetch")
            session.query(TVDisplayPayoutBank).filter_by(
                country_id=c.id).delete(synchronize_session="fetch")
        session.query(TVDisplayCountry).filter_by(
            display_id=display.id).delete(synchronize_session="fetch")
        session.commit()

        for sort_idx, country in enumerate(_REVIEWER_SAMPLE_DATA, start=1):
            c = TVDisplayCountry(
                display_id=display.id,
                country_code=country["country_code"],
                country_name=country["country_name"],
                mt_companies=country["mt_companies"],
                sort_order=sort_idx * 10,
            )
            session.add(c)
            session.flush()
            seeded_counts["countries"] += 1
            for bank_idx, bank in enumerate(country["banks"], start=1):
                b = TVDisplayPayoutBank(
                    country_id=c.id, bank_name=bank["name"],
                    sort_order=bank_idx * 10,
                )
                session.add(b)
                session.flush()
                seeded_counts["banks"] += 1
                for company, rate in bank["rates"].items():
                    session.add(TVDisplayRate(
                        bank_id=b.id, mt_company=company, rate=rate))
                    seeded_counts["rates"] += 1
        display.last_updated_at = datetime.utcnow()
        session.commit()

    return {
        "password": password,
        "created_store": created_store,
        "created_user": created_user,
        "seeded_counts": seeded_counts,
        "data_untouched": keep_data and has_existing_data,
    }


def _print_summary(result: dict) -> None:
    base_url = os.environ.get("BASE_URL", "https://dinerobook.com").rstrip("/")
    login_url = f"{base_url}/login/{_REVIEWER_SLUG}"
    print("")
    print("Amazon Reviewer account ready")
    print("")
    print(f"   Login URL:   {login_url}")
    print(f"   Username:    {_REVIEWER_USERNAME}")
    print(f"   Password:    {result['password']}")
    print("   Role:        employee  (cannot reach superadmin / billing)")
    print(f"   Store:       {_REVIEWER_STORE_NAME}  (slug: {_REVIEWER_SLUG})")
    print("   Plan:        basic  (comped — no Stripe billing)")
    print("   Add-ons:     tv_display")
    c = result["seeded_counts"]
    if result["data_untouched"]:
        print("   Sample data: untouched (--keep-data was set)")
    else:
        print(
            f"   Sample data: {c['countries']} countries, "
            f"{c['banks']} banks, {c['rates']} rate cells"
        )
    print("")
    print("   Submit these to Amazon as the test credentials. The")
    print("   reviewer signs in, navigates to TV Display in the")
    print("   sidebar, clicks 'Generate code', and pairs the test")
    print("   Fire TV. The board will show the seeded sample rates.")
    print("")
    if result["created_store"]:
        print("   (Store was created on this run.)")
    if result["created_user"]:
        print("   (User was created on this run.)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed the Amazon Appstore reviewer test account.",
    )
    parser.add_argument(
        "--password", default=None,
        help="Override the auto-generated password (>= 12 chars). "
             "Omit to generate a fresh URL-safe random.",
    )
    parser.add_argument(
        "--keep-data", action="store_true",
        help="Don't reseed sample countries/banks/rates if any already "
             "exist — useful for in-place password rotation.",
    )
    args = parser.parse_args(argv)

    init_logging()
    init_sentry()
    _ensure_schema()

    with SessionLocal() as session:
        try:
            result = run(
                session, password=args.password, keep_data=args.keep_data,
            )
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2

    _print_summary(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
