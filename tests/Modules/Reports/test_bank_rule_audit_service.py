"""Unit tests for Reports.Services.bank_rule_audit (PR 95)."""
from datetime import date, datetime

from api.Modules.BankSync.Models import BankRule, BankTransaction, StripeBankAccount
from api.Modules.Tenancy.Models import Store


_TXN_COUNTER = 0
_ACCT_COUNTER = 0


def _add_store(db, *, slug="bra-store"):
    s = Store(name=slug, slug=slug, plan="basic",
              email=f"{slug}@example.com")
    db.add(s); db.flush()
    return s


def _add_account(db, store_id, *, last4="1234"):
    global _ACCT_COUNTER
    _ACCT_COUNTER += 1
    a = StripeBankAccount(
        store_id=store_id,
        stripe_account_id=f"fca_test_{_ACCT_COUNTER}",
        last4=last4,
    )
    db.add(a); db.flush()
    return a


def _add_rule(db, store_id, *, target_kind="bank_charge_210",
              desc_match_type="contains",
              desc_match_value="REMOTE DEPOSIT FEE",
              description="auto-fee"):
    r = BankRule(
        store_id=store_id,
        enabled=True,
        target_kind=target_kind,
        desc_match_type=desc_match_type,
        desc_match_value=desc_match_value,
        description=description,
    )
    db.add(r); db.flush()
    return r


def _add_txn(db, store_id, account_id, *, posted_at,
             amount_cents=10000, matched_rule_id=None,
             category_slug=""):
    global _TXN_COUNTER
    _TXN_COUNTER += 1
    t = BankTransaction(
        store_id=store_id,
        stripe_bank_account_id=account_id,
        stripe_transaction_id=f"txn_test_{_TXN_COUNTER}",
        amount_cents=amount_cents,
        posted_at=posted_at,
        status="posted",
        category_slug=category_slug,
        matched_rule_id=matched_rule_id,
    )
    db.add(t); db.flush()
    return t


# ── shape ────────────────────────────────────────────────


def test_returns_rows_and_totals_tuple():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_rule_audit
    with flask_app.app_context():
        BankTransaction.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="bra-shape")
        rows, totals = bank_rule_audit(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert isinstance(rows, list)
        assert set(totals) == {"count", "amount", "rules"}


def test_row_shape():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_rule_audit
    with flask_app.app_context():
        BankTransaction.query.delete()
        BankRule.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="bra-row")
        a = _add_account(db.session, s.id)
        r = _add_rule(db.session, s.id)
        _add_txn(db.session, s.id, a.id,
                 posted_at=datetime(2026, 5, 5),
                 amount_cents=-10000,
                 matched_rule_id=r.id)
        rows, _ = bank_rule_audit(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert set(rows[0]) == {
            "rule_id", "label", "target", "match",
            "count", "amount",
        }


# ── filtering ─────────────────────────────────────────────


def test_only_counts_matched_rule_id_not_null():
    """Manual categorisations (matched_rule_id IS NULL) are not
    counted — those weren't a rule firing."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_rule_audit
    with flask_app.app_context():
        BankTransaction.query.delete()
        BankRule.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="bra-manual")
        a = _add_account(db.session, s.id)
        r = _add_rule(db.session, s.id)
        # Auto-applied row (matched_rule_id set).
        _add_txn(db.session, s.id, a.id,
                 posted_at=datetime(2026, 5, 5),
                 amount_cents=-1000,
                 matched_rule_id=r.id)
        # Manual override row (matched_rule_id NULL).
        _add_txn(db.session, s.id, a.id,
                 posted_at=datetime(2026, 5, 5),
                 amount_cents=-9999,
                 matched_rule_id=None,
                 category_slug="bank_charge_210")
        _, totals = bank_rule_audit(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert totals["count"] == 1
        assert totals["amount"] == 10.0
        assert totals["rules"] == 1


# ── grouping ─────────────────────────────────────────────


def test_groups_by_matched_rule_id():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_rule_audit
    with flask_app.app_context():
        BankTransaction.query.delete()
        BankRule.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="bra-group")
        a = _add_account(db.session, s.id)
        r1 = _add_rule(db.session, s.id, description="rule-1")
        r2 = _add_rule(db.session, s.id, description="rule-2")
        _add_txn(db.session, s.id, a.id,
                 posted_at=datetime(2026, 5, 5),
                 amount_cents=-1000,
                 matched_rule_id=r1.id)
        _add_txn(db.session, s.id, a.id,
                 posted_at=datetime(2026, 5, 6),
                 amount_cents=-2000,
                 matched_rule_id=r1.id)
        _add_txn(db.session, s.id, a.id,
                 posted_at=datetime(2026, 5, 7),
                 amount_cents=-500,
                 matched_rule_id=r2.id)
        rows, totals = bank_rule_audit(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        by_rid = {r["rule_id"]: r for r in rows}
        assert by_rid[r1.id]["count"] == 2
        assert by_rid[r1.id]["amount"] == 30.0
        assert by_rid[r2.id]["count"] == 1
        assert totals["count"] == 3
        assert totals["amount"] == 35.0
        assert totals["rules"] == 2


# ── rule resolution ─────────────────────────────────────


def test_label_uses_rule_id_when_rule_exists():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_rule_audit
    with flask_app.app_context():
        BankTransaction.query.delete()
        BankRule.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="bra-label")
        a = _add_account(db.session, s.id)
        r = _add_rule(db.session, s.id)
        _add_txn(db.session, s.id, a.id,
                 posted_at=datetime(2026, 5, 5),
                 matched_rule_id=r.id)
        rows, _ = bank_rule_audit(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert rows[0]["label"] == f"Rule #{r.id}"


def test_deleted_rule_renders_with_deleted_marker():
    """If the BankRule was deleted after the sync, the row still
    surfaces with `Rule #<id> (deleted)` so the audit is honest
    about what was applied even if the rule is gone."""
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_rule_audit
    with flask_app.app_context():
        BankTransaction.query.delete()
        BankRule.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="bra-deleted")
        a = _add_account(db.session, s.id)
        # Insert a transaction with a rule reference, but no rule row.
        _add_txn(db.session, s.id, a.id,
                 posted_at=datetime(2026, 5, 5),
                 matched_rule_id=99999)
        rows, _ = bank_rule_audit(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert rows[0]["label"] == "Rule #99999 (deleted)"
        assert rows[0]["target"] == ""
        assert rows[0]["match"] == ""


def test_match_summary_combines_type_and_value():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_rule_audit
    with flask_app.app_context():
        BankTransaction.query.delete()
        BankRule.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="bra-match")
        a = _add_account(db.session, s.id)
        r = _add_rule(db.session, s.id,
                      desc_match_type="starts_with",
                      desc_match_value="WIRE FEE")
        _add_txn(db.session, s.id, a.id,
                 posted_at=datetime(2026, 5, 5),
                 matched_rule_id=r.id)
        rows, _ = bank_rule_audit(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert rows[0]["match"] == 'starts_with: "WIRE FEE"'


# ── ordering ─────────────────────────────────────────────


def test_rows_sorted_by_count_descending():
    from app import app as flask_app, db
    from api.Modules.Reports.Services import bank_rule_audit
    with flask_app.app_context():
        BankTransaction.query.delete()
        BankRule.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="bra-sort")
        a = _add_account(db.session, s.id)
        r_few  = _add_rule(db.session, s.id, description="few")
        r_many = _add_rule(db.session, s.id, description="many")
        _add_txn(db.session, s.id, a.id,
                 posted_at=datetime(2026, 5, 1),
                 matched_rule_id=r_few.id)
        for i in range(5):
            _add_txn(db.session, s.id, a.id,
                     posted_at=datetime(2026, 5, 2 + i),
                     matched_rule_id=r_many.id)
        rows, _ = bank_rule_audit(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert rows[0]["rule_id"] == r_many.id
        assert rows[1]["rule_id"] == r_few.id


# ── legacy wrapper ───────────────────────────────────────


def test_legacy_wrapper_delegates():
    from app import app as flask_app, db
    from app import _bank_rule_audit_data
    from api.Modules.Reports.Services import bank_rule_audit
    with flask_app.app_context():
        BankTransaction.query.delete()
        BankRule.query.delete()
        db.session.commit()
        s = _add_store(db.session, slug="bra-legacy")
        a = _add_account(db.session, s.id)
        r = _add_rule(db.session, s.id)
        _add_txn(db.session, s.id, a.id,
                 posted_at=datetime(2026, 5, 5),
                 amount_cents=4242,
                 matched_rule_id=r.id)
        legacy_rows, legacy_totals = _bank_rule_audit_data(
            [s.id], date(2026, 5, 1), date(2026, 5, 31),
        )
        svc_rows, svc_totals = bank_rule_audit(
            db.session, [s.id],
            date(2026, 5, 1), date(2026, 5, 31),
        )
        assert legacy_rows == svc_rows
        assert legacy_totals == svc_totals
