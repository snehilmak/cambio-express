"""Built-in (platform-managed) bank rules + slug predicates.

Two related pieces of "what does a bank-transaction's
category_slug mean?" logic:

  - `BUILTIN_BANK_RULES` + `match_builtin_bank_rule(txn, account)`
    Platform-defined rules that fire after the operator's own
    `BankRule` rows. Match by description substring + optional
    last4 of the originating account; produce a target slug
    (or the per-account sentinel that resolves to
    `bank_charge_<last4>`).
  - `is_bank_charge_slug(slug)`
    Single source of truth for "is this slug part of the
    bank-charges family?" — used by the P&L feed and the
    breakdown helper.

Per CLAUDE.md "Bank-charge automation": built-ins NEVER auto-post
to the daily book (`post_to_daily=False` at the call site).
Adding a new built-in rule = appending a 3-tuple here.
"""
from typing import Iterable


# Description substring + optional account last4 + target slug.
# `bank_charge_per_account` is a sentinel resolved by
# `match_builtin_bank_rule` to `bank_charge_<last4>` so the
# operator sees which account each charge hit.
BUILTIN_BANK_RULES: list[tuple[str, str, str]] = [
    # Nizari Progressive Federal Credit Union.
    # Most fees can hit any of the operator's accounts; one (RDC fee)
    # is MSB-account-only (last4 "0230"). Targets use the sentinel
    # `bank_charge_per_account` so:
    #   - Nizari (2 accounts) splits per-account in the UI.
    #   - A bank with 1 account just gets one bank_charge_<last4> slug,
    #     no artificial split.
    # All resulting slugs roll up to the consolidated
    # `bank_charges_total` P&L line via the prefix-match in
    # `bank_charges_for_month`.
    ("REMOTE DEPOSIT FEE",  "0230", "bank_charge_per_account"),
    ("BELOW AVG BAL FEE",   "",     "bank_charge_per_account"),
    ("CHECK DEPOSIT FEE",   "",     "bank_charge_per_account"),
    ("MSB MONTHLY FEE",     "",     "bank_charge_per_account"),
    ("MONTHLY SERVICE FEE", "",     "bank_charge_per_account"),
    ("MSB W/D FEE",         "",     "bank_charge_per_account"),
]


# Sentinel target — see _resolve_per_account_slug below.
_PER_ACCOUNT_SENTINEL = "bank_charge_per_account"


def _resolve_per_account_slug(last4: str) -> str | None:
    """Resolve the `bank_charge_per_account` sentinel to a real
    `bank_charge_<last4>` slug. Strips leading zeros from last4
    to match the historic 210/230 convention (last4 "0210" →
    slug "bank_charge_210"). Returns None when last4 is empty —
    the legacy generic `bank_charge` slug is retired, so we'd
    rather not fire than tag with a phantom slug.
    """
    if not last4:
        return None
    stripped = last4.lstrip("0") or last4
    return f"bank_charge_{stripped}"


def match_builtin_bank_rule(txn, account) -> str | None:
    """Return the target slug from `BUILTIN_BANK_RULES` that matches
    `txn`, or None if nothing matches.

    Match logic:
      - Description substring is case-insensitive.
      - `want_last4` is optional. When set, the rule only fires
        if the account's last4 matches.
      - Target `bank_charge_per_account` sentinel resolves to the
        per-account slug.
    """
    desc = (txn.description or "").upper()
    last4 = (account.last4 or "") if account else ""
    for substring, want_last4, target in BUILTIN_BANK_RULES:
        if substring not in desc:
            continue
        if want_last4 and last4 != want_last4:
            continue
        if target == _PER_ACCOUNT_SENTINEL:
            return _resolve_per_account_slug(last4)
        return target
    return None


def is_bank_charge_slug(slug: str | None) -> bool:
    """True for any bank-charge category slug — generic or
    per-account (`bank_charge_210`, `bank_charge_230`, or any
    future `bank_charge_<last4>`).

    Single source of truth for "is this a bank-charge slug" used
    by the P&L feed and the breakdown helper.
    """
    if not slug:
        return False
    return slug == "bank_charge" or slug.startswith("bank_charge_")


def builtin_substrings() -> set[str]:
    """Return the set of description substrings used by built-in
    rules. Useful for the rule-conflict UI (warning the operator
    that their custom rule overlaps a built-in)."""
    return {sub for sub, _, _ in BUILTIN_BANK_RULES}
