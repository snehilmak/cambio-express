"""Service-layer unit tests for ``Customers.Services.merge``.

The HTTP integration tests in ``test_customers_controllers.py``
cover the auth gating + audit-log writes. This file exercises
the Service in isolation so the FK re-pointing logic is pinned
without the controller's transactional wrapper.
"""
from datetime import date

import pytest

from api.Modules.Customers.Models import Customer
from api.Modules.Customers.Services import (
    CustomerNotFoundError,
    SameCustomerError,
    merge_customers,
)
from api.Modules.Tenancy.Models import Store, StoreEmployee
from api.Modules.Transfers.Models import Transfer
from tests._app import db, db_session


def _add_store(slug: str) -> int:
    s = Store(
        name=slug, slug=slug, email=f"{slug}@x.com", plan="basic",
    )
    db.session.add(s); db.session.commit()
    return s.id


def _add_customer(
    store_id: int, full_name: str, *, phone_number: str = "",
) -> int:
    c = Customer(
        store_id=store_id,
        full_name=full_name,
        phone_country="+1",
        phone_number=phone_number,
    )
    db.session.add(c); db.session.commit()
    return c.id


def _add_transfer(store_id: int, customer_id: int) -> int:
    emp = (
        db.session.query(StoreEmployee)
          .filter_by(store_id=store_id).first()
    )
    if emp is None:
        emp = StoreEmployee(
            store_id=store_id, name="cashier", is_active=True,
        )
        db.session.add(emp); db.session.flush()
    t = Transfer(
        store_id=store_id,
        send_date=date.today(),
        company="Intermex",
        service_type="Money Transfer",
        sender_name="Sender",
        sender_phone="5550000000",
        sender_phone_country="+1",
        sender_address="",
        send_amount=100.0,
        fee=5.0,
        federal_tax=0.0,
        country="Mexico",
        recipient_name="Recipient",
        recipient_phone="",
        confirm_number="",
        status="Sent",
        employee_id=emp.id,
        customer_id=customer_id,
    )
    db.session.add(t); db.session.commit()
    return t.id


def test_merge_repoints_every_transfer_from_loser_to_winner():
    """N transfers pinned to the loser → N transfers on the winner
    after merge, plus whatever the winner already had."""
    with db_session():
        sid = _add_store("merge-svc-basic")
        w = _add_customer(sid, "Winner", phone_number="5550000001")
        l = _add_customer(sid, "Loser", phone_number="5550000002")
        _add_transfer(sid, w)
        _add_transfer(sid, l)
        _add_transfer(sid, l)
        _add_transfer(sid, l)

        result = merge_customers(
            db.session,
            winner_id=w,
            loser_id=l,
            store_ids=[sid],
        )
        db.session.commit()

        assert result.winner_id == w
        assert result.loser_id == l
        assert result.transfers_repointed == 3

        # All four transfers now point at the winner.
        winner_count = (
            db.session.query(Transfer)
              .filter_by(customer_id=w).count()
        )
        assert winner_count == 4
        # Loser row is gone.
        assert db.session.get(Customer, l) is None


def test_merge_returns_zero_when_loser_has_no_transfers():
    """Edge case: the loser was a fresh duplicate row with no
    history. ``transfers_repointed = 0`` is fine — the merge
    still proceeds because the duplicate row itself is the
    problem we're solving."""
    with db_session():
        sid = _add_store("merge-svc-zero")
        w = _add_customer(sid, "Winner", phone_number="5550100001")
        l = _add_customer(sid, "Loser", phone_number="5550100002")

        result = merge_customers(
            db.session,
            winner_id=w,
            loser_id=l,
            store_ids=[sid],
        )
        db.session.commit()

        assert result.transfers_repointed == 0
        assert db.session.get(Customer, l) is None
        assert db.session.get(Customer, w) is not None


def test_merge_raises_on_same_customer():
    """``winner_id == loser_id`` is a no-op the caller should
    surface as a 400 — the Service raises ``SameCustomerError``."""
    with db_session():
        sid = _add_store("merge-svc-same")
        cid = _add_customer(sid, "Self", phone_number="5550200001")
        with pytest.raises(SameCustomerError):
            merge_customers(
                db.session,
                winner_id=cid,
                loser_id=cid,
                store_ids=[sid],
            )


def test_merge_raises_on_unknown_winner():
    with db_session():
        sid = _add_store("merge-svc-unknown-w")
        l = _add_customer(sid, "Loser", phone_number="5550300001")
        with pytest.raises(CustomerNotFoundError):
            merge_customers(
                db.session,
                winner_id=9999999,
                loser_id=l,
                store_ids=[sid],
            )


def test_merge_raises_on_unknown_loser():
    with db_session():
        sid = _add_store("merge-svc-unknown-l")
        w = _add_customer(sid, "Winner", phone_number="5550400001")
        with pytest.raises(CustomerNotFoundError):
            merge_customers(
                db.session,
                winner_id=w,
                loser_id=9999999,
                store_ids=[sid],
            )


def test_merge_rejects_customer_outside_store_ids():
    """The caller passes their owner-umbrella ``store_ids``; a
    customer at a store not in that list is unreachable."""
    with db_session():
        my_store = _add_store("merge-svc-mine")
        unrelated = _add_store("merge-svc-other")
        w = _add_customer(my_store, "Winner", phone_number="5550500001")
        l = _add_customer(unrelated, "Outsider", phone_number="5550500002")

        with pytest.raises(CustomerNotFoundError):
            merge_customers(
                db.session,
                winner_id=w,
                loser_id=l,
                store_ids=[my_store],  # NOT including ``unrelated``
            )


def test_merge_repoints_across_sibling_stores_in_umbrella():
    """When the umbrella includes two stores, a customer at
    Store A can absorb a customer at Store B and inherit B's
    transfers. The Service trusts ``store_ids`` to define the
    umbrella — owner-link resolution happens upstream."""
    with db_session():
        store_a = _add_store("merge-svc-sib-a")
        store_b = _add_store("merge-svc-sib-b")
        w = _add_customer(store_a, "Winner", phone_number="5550600001")
        l = _add_customer(store_b, "Loser",  phone_number="5550600002")
        _add_transfer(store_b, l)
        _add_transfer(store_b, l)

        result = merge_customers(
            db.session,
            winner_id=w,
            loser_id=l,
            store_ids=[store_a, store_b],
        )
        db.session.commit()

        assert result.transfers_repointed == 2
        # The transfers are still on Store B (we don't migrate
        # tenancy — just the customer FK), but they now point at
        # the Store-A winner.
        rows = (
            db.session.query(Transfer)
              .filter_by(customer_id=w)
              .all()
        )
        assert {t.store_id for t in rows} == {store_b}
