"""Tests for the ACH-batch fee vs federal_tax invariant (CLAUDE.md #9).

Fee stays with the store (revenue); federal_tax leaves with the ACH
withdrawal. So:
  - Transfer.total_collected = send_amount + fee + federal_tax
  - ACHBatch.transfers_total  = Σ (send_amount + federal_tax)   # NOT fee
  - ACHBatch.variance         = ach_amount - transfers_total
"""
from datetime import date


def _seed_store_and_transfers(transfers):
    """Seed the test store's batch_ref=BATCH-1 with the given transfers.

    Each entry is a dict with send_amount / fee / federal_tax (company /
    sender_name / send_date default sensibly).
    """
    from app import db, Store, Transfer
    store = Store.query.filter_by(slug="test-store").one()
    for t in transfers:
        db.session.add(Transfer(
            store_id=store.id,
            send_date=t.get("send_date", date(2026, 4, 1)),
            company=t.get("company", "Intermex"),
            sender_name=t.get("sender_name", "Jane Doe"),
            send_amount=t["send_amount"],
            fee=t.get("fee", 0.0),
            federal_tax=t.get("federal_tax", 0.0),
            batch_id=t.get("batch_id", "BATCH-1"),
        ))
    db.session.commit()
    return store.id


# ── Transfer.total_collected ────────────────────────────────────────────────

def test_transfer_total_collected_sums_all_three(client):
    """Customer hands over: send + fee + federal_tax."""
    from app import db, Transfer
    with client.application.app_context():
        _seed_store_and_transfers([
            {"send_amount": 500.0, "fee": 8.0, "federal_tax": 5.0},
        ])
        t = Transfer.query.one()
        assert t.total_collected == 513.0


def test_transfer_total_collected_handles_none_fields(client):
    """Legacy rows may have null fee / federal_tax — must not explode."""
    from app import db, Transfer
    with client.application.app_context():
        _seed_store_and_transfers([
            {"send_amount": 100.0, "fee": None, "federal_tax": None},
        ])
        t = Transfer.query.one()
        assert t.total_collected == 100.0


def test_transfer_total_collected_with_zero_tax(client):
    from app import Transfer
    with client.application.app_context():
        _seed_store_and_transfers([
            {"send_amount": 250.0, "fee": 10.0, "federal_tax": 0.0},
        ])
        t = Transfer.query.one()
        assert t.total_collected == 260.0


# ── ACHBatch.transfers_total ────────────────────────────────────────────────

def test_ach_transfers_total_excludes_fee(client):
    """The store keeps the fee — ACH debit is send_amount + federal_tax only."""
    from app import db, ACHBatch, Store
    with client.application.app_context():
        sid = _seed_store_and_transfers([
            {"send_amount": 500.0, "fee": 8.0, "federal_tax": 5.0},
            {"send_amount": 300.0, "fee": 6.0, "federal_tax": 3.0},
        ])
        batch = ACHBatch(
            store_id=sid, ach_date=date(2026, 4, 2), company="Intermex",
            batch_ref="BATCH-1", ach_amount=808.0,
        )
        db.session.add(batch)
        db.session.commit()
        # 500 + 300 (send) + 5 + 3 (federal_tax) = 808. Fees 8 + 6 excluded.
        assert batch.transfers_total == 808.0


def test_ach_transfers_total_scoped_to_batch_ref(client):
    """Transfers in a different batch_ref must not leak into this total."""
    from app import db, ACHBatch
    with client.application.app_context():
        sid = _seed_store_and_transfers([
            {"send_amount": 500.0, "fee": 8.0, "federal_tax": 5.0,
             "batch_id": "BATCH-1"},
            {"send_amount": 999.0, "fee": 10.0, "federal_tax": 10.0,
             "batch_id": "BATCH-OTHER"},
        ])
        batch = ACHBatch(
            store_id=sid, ach_date=date(2026, 4, 2), company="Intermex",
            batch_ref="BATCH-1", ach_amount=505.0,
        )
        db.session.add(batch); db.session.commit()
        assert batch.transfers_total == 505.0


def test_ach_transfers_total_scoped_to_store(client):
    """Other stores' transfers — even sharing batch_ref — must not leak in."""
    from app import db, ACHBatch, Store, Transfer
    with client.application.app_context():
        sid = _seed_store_and_transfers([
            {"send_amount": 200.0, "fee": 4.0, "federal_tax": 2.0},
        ])
        # Add a bystander store with a transfer in the same batch_ref.
        other = Store(name="Other", slug="other-store", email="o@o.com",
                      plan="basic")
        db.session.add(other); db.session.flush()
        db.session.add(Transfer(
            store_id=other.id, send_date=date(2026, 4, 1),
            company="Intermex", sender_name="Bystander",
            send_amount=9999.0, fee=0.0, federal_tax=99.0,
            batch_id="BATCH-1",
        ))
        batch = ACHBatch(
            store_id=sid, ach_date=date(2026, 4, 2), company="Intermex",
            batch_ref="BATCH-1", ach_amount=202.0,
        )
        db.session.add(batch); db.session.commit()
        assert batch.transfers_total == 202.0


def test_ach_transfers_total_empty_batch_is_zero(client):
    """Batch with no matching transfers returns 0.0, not None."""
    from app import db, ACHBatch, Store
    with client.application.app_context():
        store = Store.query.filter_by(slug="test-store").one()
        batch = ACHBatch(
            store_id=store.id, ach_date=date(2026, 4, 2), company="Intermex",
            batch_ref="EMPTY-BATCH", ach_amount=0.0,
        )
        db.session.add(batch); db.session.commit()
        assert batch.transfers_total == 0.0


# ── ACHBatch.variance ───────────────────────────────────────────────────────

def test_ach_variance_zero_when_batch_balances(client):
    from app import db, ACHBatch
    with client.application.app_context():
        sid = _seed_store_and_transfers([
            {"send_amount": 500.0, "fee": 8.0, "federal_tax": 5.0},
        ])
        batch = ACHBatch(
            store_id=sid, ach_date=date(2026, 4, 2), company="Intermex",
            batch_ref="BATCH-1", ach_amount=505.0,
        )
        db.session.add(batch); db.session.commit()
        assert batch.variance == 0.0


def test_ach_variance_positive_when_bank_overpaid(client):
    """ach_amount > transfers_total => positive variance (bank moved too much)."""
    from app import db, ACHBatch
    with client.application.app_context():
        sid = _seed_store_and_transfers([
            {"send_amount": 500.0, "fee": 8.0, "federal_tax": 5.0},
        ])
        batch = ACHBatch(
            store_id=sid, ach_date=date(2026, 4, 2), company="Intermex",
            batch_ref="BATCH-1", ach_amount=510.25,
        )
        db.session.add(batch); db.session.commit()
        assert batch.variance == 5.25


def test_ach_variance_negative_when_bank_underpaid(client):
    from app import db, ACHBatch
    with client.application.app_context():
        sid = _seed_store_and_transfers([
            {"send_amount": 500.0, "fee": 8.0, "federal_tax": 5.0},
        ])
        batch = ACHBatch(
            store_id=sid, ach_date=date(2026, 4, 2), company="Intermex",
            batch_ref="BATCH-1", ach_amount=500.00,
        )
        db.session.add(batch); db.session.commit()
        assert batch.variance == -5.0


def test_ach_variance_rounded_to_cents(client):
    """Variance rounds to 2 decimals — no float jitter in the UI."""
    from app import db, ACHBatch
    with client.application.app_context():
        sid = _seed_store_and_transfers([
            {"send_amount": 100.10, "fee": 0.0, "federal_tax": 0.05},
        ])
        batch = ACHBatch(
            store_id=sid, ach_date=date(2026, 4, 2), company="Intermex",
            batch_ref="BATCH-1", ach_amount=100.17,
        )
        db.session.add(batch); db.session.commit()
        # 100.17 - 100.15 = 0.02 (after rounding). Guard against e.g. 0.019999.
        assert batch.variance == 0.02


# ── Transfer count & consistency ────────────────────────────────────────────

def test_ach_transfer_count_matches_batch_ref(client):
    from app import db, ACHBatch
    with client.application.app_context():
        sid = _seed_store_and_transfers([
            {"send_amount": 100.0}, {"send_amount": 200.0},
            {"send_amount": 300.0},
            {"send_amount": 400.0, "batch_id": "BATCH-OTHER"},
        ])
        batch = ACHBatch(
            store_id=sid, ach_date=date(2026, 4, 2), company="Intermex",
            batch_ref="BATCH-1", ach_amount=600.0,
        )
        db.session.add(batch); db.session.commit()
        assert batch.transfer_count == 3
