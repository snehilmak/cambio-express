"""P0-3 slice 1: Transfer + ACHBatch money stored as integer cents.

The dollar-named attributes are @property views over *_cents
BigInteger columns — Python callers keep speaking dollars, the
database stores exact cents, and derived math (total_collected,
transfers_total, variance) is integral.
"""
from tests._app import db, db_session


def _mk_transfer(store_id, **money):
    from api.Modules.Transfers.Models import Transfer
    t = Transfer(
        store_id=store_id, company="Intermex", sender_name="Ana",
        send_date=__import__("datetime").date(2026, 8, 1),
        **money,
    )
    db.session.add(t)
    db.session.flush()
    return t


def test_dollar_kwargs_store_exact_cents(client, test_store_id):
    with db_session():
        t = _mk_transfer(
            test_store_id,
            send_amount=100.10, fee=5.55, federal_tax=1.00,
            commission=0.35,
        )
        assert t.send_amount_cents == 10010
        assert t.fee_cents == 555
        assert t.federal_tax_cents == 100
        assert t.commission_cents == 35
        # Dollar views read back exactly.
        assert t.send_amount == 100.10
        assert t.total_collected_cents == 10665
        assert t.total_collected == 106.65


def test_float_artifact_sums_are_exact(client, test_store_id):
    """The bug class this migration kills: 0.1 + 0.2 style drift."""
    with db_session():
        t = _mk_transfer(
            test_store_id,
            send_amount=0.10, fee=0.20, federal_tax=0.0,
        )
        # Float would give 0.30000000000000004; cents give 30.
        assert t.total_collected_cents == 30
        assert t.total_collected == 0.30


def test_batch_variance_is_exact(client, test_store_id):
    from api.Modules.Batches.Models import ACHBatch
    import datetime
    with db_session():
        t = _mk_transfer(
            test_store_id,
            send_amount=100.00, fee=5.00, federal_tax=1.00,
        )
        t.batch_id = "B-CENTS1"
        b = ACHBatch(
            store_id=test_store_id,
            ach_date=datetime.date(2026, 8, 2),
            company="Intermex", batch_ref="B-CENTS1",
            ach_amount=101.10,
        )
        db.session.add(b)
        db.session.flush()
        # ACH debits send + tax (fee stays with the store).
        assert b.transfers_total_cents == 10100
        assert b.ach_amount_cents == 10110
        assert b.variance_cents == 10
        assert b.variance == 0.10


def test_setter_rounds_half_up(client, test_store_id):
    with db_session():
        t = _mk_transfer(test_store_id, send_amount="2.675")
        assert t.send_amount_cents == 268
