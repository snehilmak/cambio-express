"""Customer merge — combine two duplicate Customer rows.

Operators frequently log the same person twice ("Maria Lopez" vs
"Maria López", typo'd phone numbers, different addresses). The
merge endpoint lets an admin pick a winner + loser, re-points
every Transfer pointing at the loser to the winner, then deletes
the loser row. Atomic transaction — either both halves succeed
or neither lands.

Eligibility:
  * Both customers must exist.
  * Both customers must be inside the caller's owner umbrella
    (cashier at Store B can't merge customers belonging to a
    different umbrella).
  * winner_id != loser_id.

Side effects, in order:
  1. Update ``Transfer.customer_id`` from loser → winner for
     every matching row across the umbrella.
  2. Delete the loser ``Customer`` row.
  3. Stamp an ``OperatorAuditLog`` entry on the caller's store
     so the merge is visible on the admin audit log.

No commit — the caller owns the transaction so the controller
can roll back atomically on any error.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from api.Modules.Customers.Models import Customer
from api.Modules.Transfers.Models import Transfer


class CustomerMergeError(ValueError):
    """Base class for merge-eligibility failures. The Controller
    translates each subclass into a specific HTTP status."""


class SameCustomerError(CustomerMergeError):
    """winner_id == loser_id — there's no merge to do."""


class CustomerNotFoundError(CustomerMergeError):
    """Either customer ID doesn't exist OR doesn't live in the
    caller's owner umbrella. Same error so cross-umbrella probing
    can't tell "this id exists somewhere" from "no such id". """


@dataclass
class CustomerMergeResult:
    """Tally returned to the caller for audit / response shaping."""
    winner_id:          int
    loser_id:           int
    transfers_repointed: int


def merge_customers(
    db: Session,
    *,
    winner_id: int,
    loser_id:  int,
    store_ids: list[int],
) -> CustomerMergeResult:
    """Repoint every Transfer from ``loser_id`` to ``winner_id``,
    then delete the loser. Both customers must be inside
    ``store_ids`` (the caller's owner umbrella).

    Caller is responsible for committing the surrounding
    transaction AND for emitting the ``OperatorAuditLog`` entry
    via ``record_operator_action`` — both are kept outside this
    Service so the controller controls the transaction shape.
    """
    if winner_id == loser_id:
        raise SameCustomerError(
            "Cannot merge a customer into itself."
        )

    winner = (
        db.query(Customer)
          .filter(
              Customer.id == winner_id,
              Customer.store_id.in_(store_ids),
          )
          .one_or_none()
    )
    if winner is None:
        raise CustomerNotFoundError(
            f"Customer id={winner_id} not found in this umbrella."
        )
    loser = (
        db.query(Customer)
          .filter(
              Customer.id == loser_id,
              Customer.store_id.in_(store_ids),
          )
          .one_or_none()
    )
    if loser is None:
        raise CustomerNotFoundError(
            f"Customer id={loser_id} not found in this umbrella."
        )

    # Re-point every Transfer that mentions the loser. Bulk update
    # via the ORM with ``synchronize_session=False`` because we're
    # not reading the affected rows back into the session — the
    # next request fetches fresh state.
    repointed = (
        db.query(Transfer)
          .filter(Transfer.customer_id == loser_id)
          .update(
              {Transfer.customer_id: winner_id},
              synchronize_session=False,
          )
    )

    db.delete(loser)
    db.flush()
    return CustomerMergeResult(
        winner_id=int(winner.id),
        loser_id=loser_id,
        transfers_repointed=int(repointed or 0),
    )
