"""Data-retention purge.

`purge_expired_stores(db)` hard-deletes any store whose
`data_retention_until` has elapsed. Per CLAUDE.md invariant #4:
on `customer.subscription.deleted` the cancellation Service sets
`data_retention_until = now + 180 days`; this CLI walks every
store past that window and cascades deletes through every
per-store table.

Order matters because the production DB is Postgres with FK
constraints (SQLite in dev / tests is permissive but we keep
the order so behavior is identical between environments).

The walk has three sections:
  1. User-scoped auth rows (Passkey wipe, EmailEvent.user_id null)
     — has to happen before the User rows themselves so the FK
     doesn't orphan on Postgres.
  2. TV Display chain — 4-level FK chain (display → country →
     bank → rate, plus pairings) only the top of which is
     store-keyed; walked explicitly because FK cascade isn't
     declared on the parent.
  3. The generic `_STORE_OWNED_MODELS` registry — every other
     per-store model with a single `store_id` (or override) FK.

Adding a new per-store model means appending to that registry
plus the FK-override map if the column isn't literally
`store_id`.
"""
from datetime import datetime

from sqlalchemy.orm import Session


# Per-store models, in purge order. Kept as a list of class-name
# strings (not class references) so this module can be imported
# without forcing every domain Models package to load — useful for
# test introspection, schema audits, and back-compat with the
# legacy ``app._STORE_OWNED_MODELS`` re-export. The actual purge
# walk uses ``_store_owned_models()`` below which resolves these
# names to class refs.
#
# Order matters: a class must purge before any class that FKs to
# it. Add new per-store models here when introducing them.
STORE_OWNED_MODELS: list[str] = [
    "TransferAudit", "OperatorAuditLog",
    "Transfer", "ACHBatch", "DailyReport", "DailyDrop", "CheckDeposit",
    "DailyLineItem", "MoneyTransferSummary", "ReturnCheck",
    "MonthlyFinancial", "BankRule", "BankTransaction",
    "StripeBankAccount", "StoreOwnerLink",
    # TimeClockEntry must purge before StoreEmployee (FK to it).
    "TimeClockEntry",
    "StoreEmployee", "Customer",
    "ReferralCode", "ReferralRedemption",
    "TVDisplay",
    "User",
]

# Model name → FK column when not literally "store_id".
STORE_FK_OVERRIDES: dict[str, str] = {
    "ReferralCode":       "owner_store_id",
    "ReferralRedemption": "referee_store_id",
}


def _store_owned_models() -> list[tuple[type, str]]:
    """Returns (model_class, fk_column_name) pairs in purge order.

    Built lazily on first call so the Models imports don't fire at
    module-import time — keeps cheap imports of this module (e.g.
    type hints, test introspection of ``STORE_OWNED_MODELS``)
    Flask-free.
    """
    from api.Modules.Audit.Models import OperatorAuditLog, TransferAudit
    from api.Modules.BankSync.Models import (
        BankRule, BankTransaction, StripeBankAccount,
    )
    from api.Modules.Batches.Models import ACHBatch
    from api.Modules.Billing.Models import ReferralCode, ReferralRedemption
    from api.Modules.Customers.Models import Customer
    from api.Modules.DailyBook.Models import (
        CheckDeposit, DailyDrop, DailyLineItem, DailyReport,
        MoneyTransferSummary,
    )
    from api.Modules.Monthly.Models import MonthlyFinancial
    from api.Modules.ReturnChecks.Models import ReturnCheck
    from api.Modules.Tenancy.Models import (
        StoreEmployee, StoreOwnerLink, User,
    )
    from api.Modules.TimeClock.Models import TimeClockEntry
    from api.Modules.Transfers.Models import Transfer
    from api.Modules.TVDisplay.Models import TVDisplay

    return [
        # TransferAudit must purge before Transfer (FK to transfer.id),
        # and StoreEmployee before any row that FKs to it.
        (TransferAudit, "store_id"),
        (OperatorAuditLog, "store_id"),
        (Transfer, "store_id"),
        (ACHBatch, "store_id"),
        (DailyReport, "store_id"),
        (DailyDrop, "store_id"),
        (CheckDeposit, "store_id"),
        (DailyLineItem, "store_id"),
        (MoneyTransferSummary, "store_id"),
        (ReturnCheck, "store_id"),
        # BankTransaction + BankRule must purge before StripeBankAccount
        # — both FK to it.
        (MonthlyFinancial, "store_id"),
        (BankRule, "store_id"),
        (BankTransaction, "store_id"),
        (StripeBankAccount, "store_id"),
        (StoreOwnerLink, "store_id"),
        # TimeClockEntry FKs to StoreEmployee, so it must
        # purge before the roster table empties.
        (TimeClockEntry, "store_id"),
        (StoreEmployee, "store_id"),
        (Customer, "store_id"),
        # Referral tables key on a different column.
        (ReferralCode, "owner_store_id"),
        (ReferralRedemption, "referee_store_id"),
        # TVDisplay (store-keyed) — children handled by the explicit
        # chain in the purge function. Listing it here covers the
        # parent row itself.
        (TVDisplay, "store_id"),
        (User, "store_id"),
    ]


def _expired_stores(db: Session, now: datetime):
    """Stores that crossed their retention deadline."""
    from api.Modules.Tenancy.Models import Store
    return (
        db.query(Store)
          .filter(
              Store.plan == "inactive",
              Store.data_retention_until.isnot(None),
              Store.data_retention_until <= now,
          )
          .all()
    )


def _purge_user_scoped_rows(db: Session, store_id: int) -> None:
    """Wipe Passkey rows + null EmailEvent.user_id for users in
    this store before the User rows themselves are deleted by
    the generic loop."""
    from api.Modules.Auth.Models import Passkey
    from api.Modules.Tenancy.Models import User
    from api.Modules.Webhooks.Models import EmailEvent
    user_ids = [
        uid for (uid,) in
        db.query(User.id).filter_by(store_id=store_id).all()
    ]
    if not user_ids:
        return
    (
        db.query(Passkey)
          .filter(Passkey.user_id.in_(user_ids))
          .delete(synchronize_session=False)
    )
    # EmailEvent.user_id is a nullable FK; null it so the event
    # history (useful for post-purge forensics) doesn't block the
    # User delete.
    (
        db.query(EmailEvent)
          .filter(EmailEvent.user_id.in_(user_ids))
          .update({"user_id": None}, synchronize_session=False)
    )


def _purge_tv_display_chain(db: Session, store_id: int) -> None:
    """Walk the TV display chain top-down so FK constraints don't
    reject the deletes on Postgres.

    Chain:
        TVDisplay (store-keyed)
          ↳ TVDisplayCountry      (display_id)
          ↳ TVDisplayPayoutBank   (country_id)
          ↳ TVDisplayRate         (bank_id)
          ↳ TVPairing             (display_id)
          ↳ TVPendingPair         (claimed_pairing_id → TVPairing)

    The TVDisplay row itself is wiped by the generic loop in
    `STORE_OWNED_MODELS`.
    """
    from api.Modules.TVDisplay.Models import (
        TVDisplay,
        TVDisplayCountry,
        TVDisplayPayoutBank,
        TVDisplayRate,
        TVPairing,
        TVPendingPair,
    )
    display_ids = [
        d for (d,) in
        db.query(TVDisplay.id).filter_by(store_id=store_id).all()
    ]
    if not display_ids:
        return
    # TVPendingPair references TVPairing.id; wipe matching pending
    # rows first.
    doomed_pairing_ids = [
        p for (p,) in
        db.query(TVPairing.id)
          .filter(TVPairing.display_id.in_(display_ids))
          .all()
    ]
    if doomed_pairing_ids:
        (
            db.query(TVPendingPair)
              .filter(
                  TVPendingPair.claimed_pairing_id.in_(
                      doomed_pairing_ids,
                  )
              )
              .delete(synchronize_session=False)
        )
    (
        db.query(TVPairing)
          .filter(TVPairing.display_id.in_(display_ids))
          .delete(synchronize_session=False)
    )
    country_ids = [
        c for (c,) in
        db.query(TVDisplayCountry.id)
          .filter(TVDisplayCountry.display_id.in_(display_ids))
          .all()
    ]
    if country_ids:
        bank_ids = [
            b for (b,) in
            db.query(TVDisplayPayoutBank.id)
              .filter(TVDisplayPayoutBank.country_id.in_(country_ids))
              .all()
        ]
        if bank_ids:
            (
                db.query(TVDisplayRate)
                  .filter(TVDisplayRate.bank_id.in_(bank_ids))
                  .delete(synchronize_session=False)
            )
        (
            db.query(TVDisplayPayoutBank)
              .filter(TVDisplayPayoutBank.country_id.in_(country_ids))
              .delete(synchronize_session=False)
        )
    (
        db.query(TVDisplayCountry)
          .filter(TVDisplayCountry.display_id.in_(display_ids))
          .delete(synchronize_session=False)
    )


def _purge_store_owned_rows(db: Session, store_id: int) -> None:
    """Loop the static ``STORE_OWNED_MODELS`` registry, wiping every
    row owned by this store. The registry holds (model, fk_column)
    pairs so the purge walk doesn't depend on a getattr indirection
    through ``app.py``."""
    for model, fk in _store_owned_models():
        (
            db.query(model)
              .filter_by(**{fk: store_id})
              .delete(synchronize_session=False)
        )


def purge_expired_stores(db: Session) -> int:
    """Hard-delete inactive stores whose retention window has
    elapsed. Returns the count purged.

    Commits when at least one store was purged. The whole walk is
    transactional — a partial-purge crash rolls back, the cron
    job retries on the next run.
    """
    from api.Modules.Tenancy.Models import Store
    now = datetime.utcnow()
    expired = _expired_stores(db, now)
    purged = 0
    for store in expired:
        _purge_user_scoped_rows(db, store.id)
        _purge_tv_display_chain(db, store.id)
        _purge_store_owned_rows(db, store.id)
        db.delete(store)
        purged += 1
    if purged:
        db.commit()
    return purged
