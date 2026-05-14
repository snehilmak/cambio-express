"""Unit tests for BankSync.Services.categories (PR 69)."""
from api.Modules.BankSync.Models import StripeBankAccount
from tests._app import db, db_session


# ── bank_category_label ────────────────────────────────────


def test_label_returns_uncategorized_for_empty():
    from api.Modules.BankSync.Services import bank_category_label
    assert bank_category_label("") == "Uncategorized"
    assert bank_category_label(None) == "Uncategorized"


def test_label_uses_static_non_posting_dict():
    from api.Modules.BankSync.Services import (
        BANK_CATEGORIES_NON_POSTING, bank_category_label,
    )
    assert bank_category_label("internal_transfer") == \
        BANK_CATEGORIES_NON_POSTING["internal_transfer"]
    assert bank_category_label("ignore") == \
        "Ignore (don't reconcile)"


def test_label_renders_dynamic_bank_charge_per_account():
    """bank_charge_<last4> not in the static dict → uniform
    'Bank charge — ••<last4>' label."""
    from api.Modules.BankSync.Services import bank_category_label
    assert bank_category_label("bank_charge_9999") == \
        "Bank charge — ••9999"


def test_label_for_daily_book_kind_titlecases_singular():
    """DailyBook kinds get the singular label titlecased."""
    from api.Modules.BankSync.Services import bank_category_label
    # cash_expense → "Cash Expense" (titlecased)
    assert bank_category_label("cash_expense") == "Cash Expense"
    # check_deposit → "Check Deposit"
    assert bank_category_label("check_deposit") == "Check Deposit"


def test_label_falls_through_to_raw_slug():
    """Unknown slug → return the slug itself (so debugging is
    easy if a stale slug ever leaks into the UI)."""
    from api.Modules.BankSync.Services import bank_category_label
    assert bank_category_label("totally_made_up") == "totally_made_up"


# ── is_daily_book_kind ─────────────────────────────────────


def test_is_daily_book_kind_true_for_registered():
    from api.Modules.BankSync.Services import is_daily_book_kind
    assert is_daily_book_kind("cash_expense") is True
    assert is_daily_book_kind("drop") is True


def test_is_daily_book_kind_false_for_non_posting_tag():
    from api.Modules.BankSync.Services import is_daily_book_kind
    assert is_daily_book_kind("internal_transfer") is False
    assert is_daily_book_kind("ignore") is False


def test_is_daily_book_kind_false_for_blank_or_none():
    from api.Modules.BankSync.Services import is_daily_book_kind
    assert is_daily_book_kind("") is False
    assert is_daily_book_kind(None) is False


# ── is_valid_bank_category ─────────────────────────────────


def test_is_valid_accepts_daily_book_kind():
    from tests._app import db
    from api.Modules.BankSync.Services import is_valid_bank_category
    with db_session():
        assert is_valid_bank_category(
            db.session, "cash_expense", store_id=1,
        ) is True


def test_is_valid_accepts_static_non_posting():
    from tests._app import db
    from api.Modules.BankSync.Services import is_valid_bank_category
    with db_session():
        assert is_valid_bank_category(
            db.session, "internal_transfer", store_id=1,
        ) is True
        assert is_valid_bank_category(
            db.session, "ignore", store_id=1,
        ) is True


def test_is_valid_rejects_blank():
    from tests._app import db
    from api.Modules.BankSync.Services import is_valid_bank_category
    with db_session():
        assert is_valid_bank_category(
            db.session, "", store_id=1,
        ) is False
        assert is_valid_bank_category(
            db.session, None, store_id=1,
        ) is False


def test_is_valid_rejects_unknown_slug():
    from tests._app import db
    from api.Modules.BankSync.Services import is_valid_bank_category
    with db_session():
        assert is_valid_bank_category(
            db.session, "made_up_slug", store_id=1,
        ) is False


def test_is_valid_accepts_dynamic_bank_charge_for_connected_account():
    """bank_charge_<last4> validates against the store's
    connected `StripeBankAccount` rows."""
    from api.Modules.Tenancy.Models import Store
    from tests._app import db
    from api.Modules.BankSync.Services import is_valid_bank_category
    with db_session():
        db.session.query(StripeBankAccount).delete()
        db.session.commit()
        s = Store(name="bc-store", slug="bc-store",
                  plan="basic", email="bc@example.com")
        db.session.add(s); db.session.flush()
        db.session.add(StripeBankAccount(
            store_id=s.id,
            stripe_account_id="fcacct_x",
            last4="0210",
        ))
        db.session.flush()
        # Stripped form
        assert is_valid_bank_category(
            db.session, "bank_charge_210", store_id=s.id,
        ) is True
        # Original form (with leading zero)
        assert is_valid_bank_category(
            db.session, "bank_charge_0210", store_id=s.id,
        ) is True
        # Different account → invalid
        assert is_valid_bank_category(
            db.session, "bank_charge_9999", store_id=s.id,
        ) is False


def test_is_valid_rejects_bank_charge_with_empty_suffix():
    """`bank_charge_` with no suffix is junk."""
    from tests._app import db
    from api.Modules.BankSync.Services import is_valid_bank_category
    with db_session():
        assert is_valid_bank_category(
            db.session, "bank_charge_", store_id=1,
        ) is False


# ── bank_category_groups ───────────────────────────────────


def test_groups_returns_two_top_level_groups():
    from tests._app import db
    from api.Modules.BankSync.Services import bank_category_groups
    with db_session():
        result = bank_category_groups(db.session)
        assert len(result) == 2
        labels = [g[0] for g in result]
        assert labels == [
            "Daily-book line items",
            "Other (no daily-book impact)",
        ]


def test_groups_includes_static_non_posting_tags():
    from tests._app import db
    from api.Modules.BankSync.Services import bank_category_groups
    with db_session():
        result = bank_category_groups(db.session)
        other_slugs = {slug for slug, _ in result[1][1]}
        assert "internal_transfer" in other_slugs
        assert "ignore" in other_slugs


def test_groups_augments_other_with_per_account_bank_charges():
    """Connected accounts get dynamic bank_charge_<last4> entries
    in the Other group."""
    from api.Modules.Tenancy.Models import Store
    from tests._app import db
    from api.Modules.BankSync.Services import bank_category_groups
    with db_session():
        db.session.query(StripeBankAccount).delete()
        db.session.commit()
        s = Store(name="grp-store", slug="grp-store",
                  plan="basic", email="grp@example.com")
        db.session.add(s); db.session.flush()
        # An account whose stripped slug isn't in the static dict.
        db.session.add(StripeBankAccount(
            store_id=s.id,
            stripe_account_id="fcacct_y",
            last4="9999",
        ))
        db.session.flush()
        result = bank_category_groups(db.session, store_id=s.id)
        other_slugs = {slug for slug, _ in result[1][1]}
        assert "bank_charge_9999" in other_slugs


def test_groups_does_not_duplicate_static_slugs():
    """If an account's last4 maps to a slug already in the static
    dict (210/230), don't double-add it."""
    from api.Modules.Tenancy.Models import Store
    from tests._app import db
    from api.Modules.BankSync.Services import bank_category_groups
    with db_session():
        db.session.query(StripeBankAccount).delete()
        db.session.commit()
        s = Store(name="dup-store", slug="dup-store",
                  plan="basic", email="dup@example.com")
        db.session.add(s); db.session.flush()
        db.session.add(StripeBankAccount(
            store_id=s.id,
            stripe_account_id="fcacct_z",
            last4="0210",
        ))
        db.session.flush()
        result = bank_category_groups(db.session, store_id=s.id)
        other_slugs = [slug for slug, _ in result[1][1]]
        assert other_slugs.count("bank_charge_210") == 1


# ── legacy Flask wrappers ──────────────────────────────────










