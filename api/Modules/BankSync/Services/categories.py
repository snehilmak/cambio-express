"""Bank category / slug helpers.

Operator-facing display + validation for the slugs that bank
transactions can be tagged with. Three concerns live here:

  - `BANK_CATEGORIES_NON_POSTING`: static dict of slugs that
    DON'T post to the daily book. Internal transfers, MT ACH
    debits, ignore-me tags. Static `bank_charge_210 / _230`
    entries are kept ONLY so the Nizari-store dropdown still
    surfaces them; future banks get their slugs added
    dynamically by `bank_category_groups`.

  - `bank_category_label(slug)` — operator-friendly display name.
    Folds dynamic `bank_charge_<last4>` slugs into a uniform
    "Bank charge — ••<last4>" rendering.

  - `bank_category_groups(db, store_id)` — grouped dropdown
    options: daily-book kinds vs non-posting tags. Augments the
    "Other" group with per-account `bank_charge_<last4>` entries
    for every connected account so single-account or non-Nizari
    banks see a relevant option.

  - `is_valid_bank_category(db, slug, store_id)` — predicate for
    server-side validation when an operator tags a transaction
    or saves a `BankRule`.

  - `is_daily_book_kind(slug)` — true iff `slug` is in the
    DailyBook line-item registry.
"""
from sqlalchemy.orm import Session

from api.Modules.BankSync.Services.builtin_rules import is_bank_charge_slug
from api.Modules.DailyBook.Services import LINE_ITEM_KINDS


# Static slugs that don't post to the daily book.
# Static `bank_charge_210 / _230` entries are kept ONLY so the
# Nizari-store dropdown still surfaces them; future banks get
# their slugs added dynamically by `bank_category_groups` via the
# store's connected accounts.
BANK_CATEGORIES_NON_POSTING: dict[str, str] = {
    "internal_transfer":  "Internal transfer",
    "mt_ach_intermex":    "MT ACH — Intermex",
    "mt_ach_maxi":        "MT ACH — Maxi",
    "mt_ach_barri":       "MT ACH — Barri",
    "bank_charge_210":    "Bank charge — ••0210",
    "bank_charge_230":    "Bank charge — ••0230 (MSB)",
    "ignore":             "Ignore (don't reconcile)",
}


def is_daily_book_kind(slug: str | None) -> bool:
    """True iff `slug` is a registered DailyBook line-item kind.

    Pure read of the LINE_ITEM_KINDS registry — no DB.
    """
    if not slug:
        return False
    return slug in LINE_ITEM_KINDS


def bank_category_label(slug: str | None) -> str:
    """Operator-friendly label for a category slug.

    Lookup priority:
      1. `BANK_CATEGORIES_NON_POSTING` static dict.
      2. Dynamic `bank_charge_<last4>` slug → "Bank charge —
         ••<last4>" (so the UI doesn't show the raw slug).
      3. DailyBook line-item kind → titlecase of singular label.
      4. Fall through to the slug itself.

    Empty / None slug returns "Uncategorized".
    """
    if not slug:
        return "Uncategorized"
    if slug in BANK_CATEGORIES_NON_POSTING:
        return BANK_CATEGORIES_NON_POSTING[slug]
    # Dynamic per-account bank-charge slug — render uniformly.
    if slug.startswith("bank_charge_"):
        suffix = slug[len("bank_charge_"):]
        if suffix:
            return f"Bank charge — ••{suffix}"
    if slug in LINE_ITEM_KINDS:
        return LINE_ITEM_KINDS[slug][1].title()
    return slug


def bank_category_groups(
    db: Session, store_id: int | None = None,
) -> list[tuple[str, list[tuple[str, str]]]]:
    """Grouped `(group_label, [(slug, label), ...])` tuples for
    dropdowns.

    The two groups stay separate in the UI so operators don't
    confuse auto-posting kinds with non-posting tags.

    When `store_id` is given, the "Other" group is augmented with
    a per-account `bank_charge_<last4>` entry for every connected
    account that isn't already in the static dict — so
    single-account or non-Nizari banks see a relevant bank-charge
    option.
    """
    daily = [
        (slug, meta[1].title())
        for slug, meta in LINE_ITEM_KINDS.items()
    ]
    other = dict(BANK_CATEGORIES_NON_POSTING)  # copy so we can extend
    if store_id is not None:
        from app import StripeBankAccount
        accounts = (
            db.query(StripeBankAccount)
              .filter_by(store_id=store_id)
              .all()
        )
        for a in accounts:
            if not a.last4:
                continue
            stripped = a.last4.lstrip("0") or a.last4
            slug = f"bank_charge_{stripped}"
            if slug not in other:
                other[slug] = f"Bank charge — ••{a.last4}"
    return [
        ("Daily-book line items", daily),
        ("Other (no daily-book impact)", list(other.items())),
    ]


def is_valid_bank_category(
    db: Session, slug: str | None, store_id: int,
) -> bool:
    """True iff `slug` is an acceptable target for a manual
    bank-transaction tag or a `BankRule`.

    Accepts every slug surfaced in `bank_category_groups(store_id)`,
    including dynamic `bank_charge_<last4>` for the store's
    connected accounts.
    """
    if not slug:
        return False
    if slug in LINE_ITEM_KINDS or slug in BANK_CATEGORIES_NON_POSTING:
        return True
    # Dynamic per-account bank-charge: validate against the store's
    # connected account set.
    if slug.startswith("bank_charge_"):
        last4 = slug[len("bank_charge_"):]
        if not last4:
            return False
        from app import StripeBankAccount
        accounts = (
            db.query(StripeBankAccount)
              .filter_by(store_id=store_id)
              .all()
        )
        for a in accounts:
            if not a.last4:
                continue
            stripped = a.last4.lstrip("0") or a.last4
            if last4 == stripped or last4 == a.last4:
                return True
    return False
