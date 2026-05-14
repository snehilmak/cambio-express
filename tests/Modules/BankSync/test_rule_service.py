"""Unit tests for the BankSync rule write-side Service (PR 31)."""
import pytest
from tests._app import db


def _seed_account(store_id, *, last4="0000"):
    from api.Modules.BankSync.Models import StripeBankAccount
    from tests._app import db
    a = StripeBankAccount(
        store_id=store_id, stripe_account_id=f"fcacc_{last4}",
        institution_name="Bank", last4=last4, enabled=True,
    )
    db.session.add(a); db.session.commit()
    return a.id


def _always_valid(slug, store_id):
    """Test stand-in for `_is_valid_bank_category` so we don't need
    the legacy category-groups plumbing in unit tests."""
    return True


def _form(**kwargs):
    """Build a simple dict the parser can read via .get()."""
    return dict(kwargs)


# ── parse_rule_form ─────────────────────────────────────────


def test_parse_rule_form_minimal_valid_input(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import parse_rule_form
    with flask_app.app_context():
        fields = parse_rule_form(
            db.session,
            _form(target_kind="bank_charge_210", sign_filter="debit"),
            test_store_id, _always_valid,
        )
    assert fields.target_kind == "bank_charge_210"
    assert fields.sign_filter == "debit"
    assert fields.priority == 100  # default
    assert fields.enabled is False  # not "on"
    assert fields.auto_post is False
    assert fields.amount_min_cents is None
    assert fields.amount_max_cents is None


def test_parse_rule_form_rejects_missing_target_kind(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        RuleValidationError, parse_rule_form,
    )
    with flask_app.app_context():
        with pytest.raises(RuleValidationError) as exc:
            parse_rule_form(
                db.session, _form(sign_filter="debit"),
                test_store_id, _always_valid,
            )
    assert "category" in str(exc.value).lower()


def test_parse_rule_form_rejects_unknown_category(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        RuleValidationError, parse_rule_form,
    )
    with flask_app.app_context():
        with pytest.raises(RuleValidationError):
            parse_rule_form(
                db.session,
                _form(target_kind="garbage", sign_filter="debit"),
                test_store_id, lambda s, sid: False,  # always invalid
            )


def test_parse_rule_form_requires_at_least_one_condition(test_store_id):
    """An empty rule (no conditions) matches everything — almost
    always a misconfiguration."""
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        RuleValidationError, parse_rule_form,
    )
    with flask_app.app_context():
        with pytest.raises(RuleValidationError) as exc:
            parse_rule_form(
                db.session, _form(target_kind="bank_charge_210"),
                test_store_id, _always_valid,
            )
    assert "condition" in str(exc.value).lower()


def test_parse_rule_form_desc_value_without_type_defaults_to_contains(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import parse_rule_form
    with flask_app.app_context():
        fields = parse_rule_form(
            db.session,
            _form(target_kind="bank_charge_210", desc_match_value="FEE"),
            test_store_id, _always_valid,
        )
    assert fields.desc_match_type == "contains"
    assert fields.desc_match_value == "FEE"


def test_parse_rule_form_rejects_desc_type_without_value(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        RuleValidationError, parse_rule_form,
    )
    with flask_app.app_context():
        with pytest.raises(RuleValidationError):
            parse_rule_form(
                db.session,
                _form(
                    target_kind="bank_charge_210",
                    desc_match_type="contains",
                ),
                test_store_id, _always_valid,
            )


def test_parse_rule_form_rejects_invalid_desc_type(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        RuleValidationError, parse_rule_form,
    )
    with flask_app.app_context():
        with pytest.raises(RuleValidationError):
            parse_rule_form(
                db.session,
                _form(
                    target_kind="bank_charge_210",
                    desc_match_type="garbage",
                    desc_match_value="x",
                ),
                test_store_id, _always_valid,
            )


def test_parse_rule_form_rejects_invalid_sign_filter(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        RuleValidationError, parse_rule_form,
    )
    with flask_app.app_context():
        with pytest.raises(RuleValidationError):
            parse_rule_form(
                db.session,
                _form(
                    target_kind="bank_charge_210", sign_filter="garbage",
                ),
                test_store_id, _always_valid,
            )


def test_parse_rule_form_amounts_dollars_to_cents(test_store_id):
    """Form posts dollar strings; Service stores absolute cents."""
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import parse_rule_form
    with flask_app.app_context():
        fields = parse_rule_form(
            db.session,
            _form(
                target_kind="bank_charge_210",
                amount_min="10.50", amount_max="20",
            ),
            test_store_id, _always_valid,
        )
    assert fields.amount_min_cents == 1050
    assert fields.amount_max_cents == 2000


def test_parse_rule_form_rejects_negative_amount(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        RuleValidationError, parse_rule_form,
    )
    with flask_app.app_context():
        with pytest.raises(RuleValidationError):
            parse_rule_form(
                db.session,
                _form(target_kind="bank_charge_210", amount_min="-5"),
                test_store_id, _always_valid,
            )


def test_parse_rule_form_rejects_min_greater_than_max(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        RuleValidationError, parse_rule_form,
    )
    with flask_app.app_context():
        with pytest.raises(RuleValidationError):
            parse_rule_form(
                db.session,
                _form(
                    target_kind="bank_charge_210",
                    amount_min="50", amount_max="10",
                ),
                test_store_id, _always_valid,
            )


def test_parse_rule_form_account_filter_must_belong_to_store(test_store_id):
    """Cross-store account_filter_id references must be rejected."""
    from api.Modules.Tenancy.Models import Store
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        RuleValidationError, parse_rule_form,
    )
    with flask_app.app_context():
        s2 = Store(name="Other", slug="other-rule-svc",
                    email="o@x.com", plan="trial")
        db.session.add(s2); db.session.commit()
        other_acct = _seed_account(s2.id, last4="1234")
        with pytest.raises(RuleValidationError) as exc:
            parse_rule_form(
                db.session,
                _form(
                    target_kind="bank_charge_210",
                    account_filter_id=str(other_acct),
                ),
                test_store_id, _always_valid,
            )
    assert "account" in str(exc.value).lower()


def test_parse_rule_form_account_filter_succeeds_in_scope(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import parse_rule_form
    with flask_app.app_context():
        a = _seed_account(test_store_id, last4="OURS")
        fields = parse_rule_form(
            db.session,
            _form(
                target_kind="bank_charge_210",
                account_filter_id=str(a),
            ),
            test_store_id, _always_valid,
        )
    assert fields.account_filter_id == a


def test_parse_rule_form_truncates_long_description(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import parse_rule_form
    with flask_app.app_context():
        fields = parse_rule_form(
            db.session,
            _form(
                target_kind="bank_charge_210", sign_filter="debit",
                description="X" * 500,
            ),
            test_store_id, _always_valid,
        )
    assert len(fields.description) == 200


# ── create / update / toggle / delete ───────────────────────


def test_create_rule_inserts_row(test_store_id):
    from api.Modules.BankSync.Models import BankRule
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        RuleFields, create_rule,
    )
    fields = RuleFields(
        enabled=True, priority=10,
        desc_match_type="contains", desc_match_value="FEE",
        sign_filter="debit",
        amount_min_cents=None, amount_max_cents=None,
        account_filter_id=None,
        target_kind="bank_charge_210", auto_post=True,
        description="",
    )
    with flask_app.app_context():
        rule = create_rule(db.session, test_store_id, fields)
        db.session.commit()
        rid = rule.id
        # Verify the row landed
        loaded = db.session.get(BankRule, rid)
    assert loaded.store_id == test_store_id
    assert loaded.target_kind == "bank_charge_210"
    assert loaded.priority == 10


def test_update_rule_updates_in_place(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        RuleFields, create_rule, update_rule,
    )
    base = RuleFields(
        enabled=True, priority=100,
        desc_match_type="", desc_match_value="",
        sign_filter="debit",
        amount_min_cents=None, amount_max_cents=None,
        account_filter_id=None,
        target_kind="bank_charge_210", auto_post=True,
        description="",
    )
    with flask_app.app_context():
        rule = create_rule(db.session, test_store_id, base)
        db.session.commit()
        rid = rule.id
        new_fields = RuleFields(
            enabled=False, priority=50,
            desc_match_type="contains", desc_match_value="UPDATED",
            sign_filter="credit",
            amount_min_cents=100, amount_max_cents=500,
            account_filter_id=None,
            target_kind="bank_charge_210", auto_post=False,
            description="updated note",
        )
        result = update_rule(db.session, rid, test_store_id, new_fields)
        db.session.commit()
        assert result.enabled is False
        assert result.priority == 50
        assert result.desc_match_value == "UPDATED"
        assert result.sign_filter == "credit"
        assert result.amount_min_cents == 100


def test_update_rule_raises_when_cross_store(test_store_id):
    from api.Modules.Tenancy.Models import Store
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        RuleFields, RuleNotFoundError, create_rule, update_rule,
    )
    fields = RuleFields(
        enabled=True, priority=100,
        desc_match_type="", desc_match_value="",
        sign_filter="debit",
        amount_min_cents=None, amount_max_cents=None,
        account_filter_id=None,
        target_kind="bank_charge_210", auto_post=True,
        description="",
    )
    with flask_app.app_context():
        s2 = Store(name="Other", slug="other-update",
                    email="o@x.com", plan="trial")
        db.session.add(s2); db.session.commit()
        rule = create_rule(db.session, s2.id, fields)
        db.session.commit()
        with pytest.raises(RuleNotFoundError):
            update_rule(db.session, rule.id, test_store_id, fields)


def test_toggle_rule_flips_enabled(test_store_id):
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        RuleFields, create_rule, toggle_rule,
    )
    fields = RuleFields(
        enabled=True, priority=100,
        desc_match_type="", desc_match_value="",
        sign_filter="debit",
        amount_min_cents=None, amount_max_cents=None,
        account_filter_id=None,
        target_kind="bank_charge_210", auto_post=True,
        description="",
    )
    with flask_app.app_context():
        rule = create_rule(db.session, test_store_id, fields)
        db.session.commit()
        toggled = toggle_rule(db.session, rule.id, test_store_id)
        db.session.commit()
        assert toggled.enabled is False
        toggled = toggle_rule(db.session, rule.id, test_store_id)
        db.session.commit()
        assert toggled.enabled is True


def test_delete_rule_removes_row(test_store_id):
    from api.Modules.BankSync.Models import BankRule
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        RuleFields, create_rule, delete_rule,
    )
    fields = RuleFields(
        enabled=True, priority=100,
        desc_match_type="", desc_match_value="",
        sign_filter="debit",
        amount_min_cents=None, amount_max_cents=None,
        account_filter_id=None,
        target_kind="bank_charge_210", auto_post=True,
        description="",
    )
    with flask_app.app_context():
        rule = create_rule(db.session, test_store_id, fields)
        db.session.commit()
        rid = rule.id
        delete_rule(db.session, rid, test_store_id)
        db.session.commit()
        assert db.session.get(BankRule, rid) is None


def test_delete_rule_raises_when_cross_store(test_store_id):
    from api.Modules.Tenancy.Models import Store
    from tests._app import app as flask_app, db
    from api.Modules.BankSync.Services import (
        RuleFields, RuleNotFoundError, create_rule, delete_rule,
    )
    fields = RuleFields(
        enabled=True, priority=100,
        desc_match_type="", desc_match_value="",
        sign_filter="debit",
        amount_min_cents=None, amount_max_cents=None,
        account_filter_id=None,
        target_kind="bank_charge_210", auto_post=True,
        description="",
    )
    with flask_app.app_context():
        s2 = Store(name="Other", slug="other-del",
                    email="o@x.com", plan="trial")
        db.session.add(s2); db.session.commit()
        rule = create_rule(db.session, s2.id, fields)
        db.session.commit()
        with pytest.raises(RuleNotFoundError):
            delete_rule(db.session, rule.id, test_store_id)
