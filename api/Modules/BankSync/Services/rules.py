"""BankRule write-side service: parse, create, update, toggle, delete.

The legacy `/bank/rules/*` Flask routes now delegate to these. The
parse_rule_form helper takes a `is_valid_category` callable so the
Flask app can pass its `_is_valid_bank_category(slug, store_id)` —
that function depends on per-store category groups + non-posting
slugs which still live in `app.py`. When that logic migrates, we
drop the callable.

Every write helper raises `RuleNotFoundError` for cross-tenant or
missing IDs (instead of 404) so the Service stays HTTP-agnostic.
Validation failures surface as `RuleValidationError` carrying a
human-readable message (the same string the legacy form flashed).
"""
from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from api.Modules.BankSync.Models import BankRule
from api.Modules.BankSync.Repositories import (
    find_account_in_store,
    get_rule_by_id,
)


_VALID_DESC_MATCH_TYPES = ("contains", "starts_with", "equals", "regex")
_VALID_SIGN_FILTERS = ("credit", "debit")
_DESCRIPTION_MAX_LEN = 200


@dataclass
class RuleFields:
    """Validated, ready-to-apply attribute updates for a BankRule.
    The Service produces this; the create/update helpers consume it.

    `enabled`/`auto_post` default-True is intentional: a freshly
    saved rule should fire by default. The legacy form posted
    explicit `on` checkboxes — the parser sets the bool field, here
    it's already coerced.
    """
    enabled: bool
    priority: int
    desc_match_type: str
    desc_match_value: str
    sign_filter: str
    amount_min_cents: int | None
    amount_max_cents: int | None
    account_filter_id: int | None
    target_kind: str
    auto_post: bool
    description: str

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "priority": self.priority,
            "desc_match_type": self.desc_match_type,
            "desc_match_value": self.desc_match_value,
            "sign_filter": self.sign_filter,
            "amount_min_cents": self.amount_min_cents,
            "amount_max_cents": self.amount_max_cents,
            "account_filter_id": self.account_filter_id,
            "target_kind": self.target_kind,
            "auto_post": self.auto_post,
            "description": self.description,
        }


class RuleValidationError(ValueError):
    """User-facing validation failure. The message is safe to render
    to the operator (same strings the legacy `/bank/rules` form
    flashed)."""


class RuleNotFoundError(LookupError):
    """The rule doesn't exist or belongs to a different store. Same
    error type for both so callers can't enumerate "exists but is
    cross-tenant" via the response."""


def _parse_dollars(form: dict, label: str) -> int | None:
    raw = (form.get(label) or "").strip()
    if not raw:
        return None
    try:
        cents = int(round(float(raw) * 100))
    except ValueError:
        raise RuleValidationError(f"Invalid amount in {label}.")
    if cents < 0:
        raise RuleValidationError("Amounts must be non-negative.")
    return cents


def parse_rule_form(
    db: Session, form: dict, store_id: int,
    is_valid_category: Callable[[str, int], bool],
) -> RuleFields:
    """Parse + validate the form payload posted to /bank/rules/new
    or /bank/rules/<id>/edit. Returns ready-to-apply RuleFields.
    Raises RuleValidationError with the same human-readable message
    the legacy form flashed.

    `form` is anything dict-like with a `.get(key)` that returns the
    raw string (or None). Flask's request.form, FastAPI's parsed
    form, and a plain dict in tests all satisfy this.
    """
    desc_match_type = (form.get("desc_match_type") or "").strip()
    desc_match_value = (form.get("desc_match_value") or "").strip()
    sign_filter = (form.get("sign_filter") or "").strip()
    target_kind = (form.get("target_kind") or "").strip()

    if not target_kind:
        raise RuleValidationError(
            "Pick a category to apply when this rule matches.",
        )
    if not is_valid_category(target_kind, store_id):
        raise RuleValidationError("Unknown category.")

    # Description match — both fields must be set together, or both empty.
    if desc_match_type and not desc_match_value:
        raise RuleValidationError(
            "Enter a description value to match against.",
        )
    if desc_match_value and not desc_match_type:
        desc_match_type = "contains"
    if desc_match_type and desc_match_type not in _VALID_DESC_MATCH_TYPES:
        raise RuleValidationError("Unknown description match type.")

    if sign_filter and sign_filter not in _VALID_SIGN_FILTERS:
        raise RuleValidationError("Sign filter must be credit or debit.")

    amount_min_cents = _parse_dollars(form, "amount_min")
    amount_max_cents = _parse_dollars(form, "amount_max")
    if (
        amount_min_cents is not None
        and amount_max_cents is not None
        and amount_min_cents > amount_max_cents
    ):
        raise RuleValidationError("Min amount can't be greater than max.")

    # Account filter — must belong to the store (rejecting cross-store
    # account refs is the security property).
    account_filter_id: int | None = None
    raw_acct = (form.get("account_filter_id") or "").strip()
    if raw_acct:
        try:
            acct_id = int(raw_acct)
        except ValueError:
            raise RuleValidationError("Invalid account filter.")
        if find_account_in_store(db, acct_id, store_id) is None:
            raise RuleValidationError(
                "Account filter does not belong to this store.",
            )
        account_filter_id = acct_id

    # At least one condition must be set — an empty rule matches every
    # transaction and is almost always a misconfiguration.
    if (
        not desc_match_type and not sign_filter
        and amount_min_cents is None and amount_max_cents is None
        and account_filter_id is None
    ):
        raise RuleValidationError(
            "Set at least one condition (description, sign, amount, "
            "or account).",
        )

    try:
        priority = int(form.get("priority") or 100)
    except ValueError:
        priority = 100

    return RuleFields(
        enabled=form.get("enabled") == "on",
        priority=priority,
        desc_match_type=desc_match_type,
        desc_match_value=desc_match_value,
        sign_filter=sign_filter,
        amount_min_cents=amount_min_cents,
        amount_max_cents=amount_max_cents,
        account_filter_id=account_filter_id,
        target_kind=target_kind,
        auto_post=form.get("auto_post") == "on",
        description=(form.get("description") or "").strip()[:_DESCRIPTION_MAX_LEN],
    )


def create_rule(
    db: Session, store_id: int, fields: RuleFields,
) -> BankRule:
    rule = BankRule(store_id=store_id, **fields.to_dict())
    db.add(rule)
    db.flush()
    return rule


def update_rule(
    db: Session, rule_id: int, store_id: int, fields: RuleFields,
) -> BankRule:
    rule = get_rule_by_id(db, rule_id, store_id)
    if rule is None:
        raise RuleNotFoundError(f"BankRule id={rule_id}")
    for k, v in fields.to_dict().items():
        setattr(rule, k, v)
    db.flush()
    return rule


def toggle_rule(
    db: Session, rule_id: int, store_id: int,
) -> BankRule:
    rule = get_rule_by_id(db, rule_id, store_id)
    if rule is None:
        raise RuleNotFoundError(f"BankRule id={rule_id}")
    rule.enabled = not rule.enabled
    db.flush()
    return rule


def delete_rule(
    db: Session, rule_id: int, store_id: int,
) -> None:
    rule = get_rule_by_id(db, rule_id, store_id)
    if rule is None:
        raise RuleNotFoundError(f"BankRule id={rule_id}")
    db.delete(rule)
    db.flush()
