"""The cancelled-transfer exclusion list must use the spelling the
app actually writes.

``OWNER_TRANSFER_EXCLUDED`` is the single filter that keeps
cancelled transfers out of owner dashboards, superadmin BI, the
tax pack, daily-summary emails, customer segments, employee
activity and the cancelled-transfers report — about twenty call
sites. It shipped as ``["Canceled", "Rejected"]`` with one L,
while the SPA writes ``"Cancelled"`` with two (see
frontend/src/routes/EditTransfer.tsx and
api/Modules/Transfers/INVARIANTS.md, which documents "Cancelled"
as the value reports filter on).

The result was silent and one-directional: every rollup counted
cancelled transfers as real volume, and the report whose whole
subject is cancelled transfers matched only the rejected ones.

These tests pin the spelling to what is written, so a future
tidy-up cannot quietly reintroduce the mismatch.
"""
from api.Modules.Owners.Services import OWNER_TRANSFER_EXCLUDED

# The values the app writes. EditTransfer.tsx offers exactly
# these four; "Sent"/"Pending"/"Returned" are not exclusions.
SPA_CANCEL_STATUS = "Cancelled"


def test_exclusion_list_catches_the_status_the_app_writes():
    assert SPA_CANCEL_STATUS in OWNER_TRANSFER_EXCLUDED, (
        "the exclusion list must contain the exact string the "
        "transfer form saves, or cancelled transfers count as volume"
    )


def test_rejected_is_still_excluded():
    assert "Rejected" in OWNER_TRANSFER_EXCLUDED


def test_legacy_single_l_spelling_is_kept():
    """Rows written before the spelling was reconciled may carry
    the one-L form; dropping it would resurrect the bug for them."""
    assert "Canceled" in OWNER_TRANSFER_EXCLUDED


def test_a_cancelled_transfer_is_actually_filtered_out():
    """The behavioural version — the constant is only worth
    anything if a real query using it drops the row."""
    from datetime import date

    from api.Modules.Reports.Models import Transfer
    from tests._app import db, db_session
    from api.Modules.Tenancy.Models import Store

    with db_session():
        store = Store(
            name="Excl", slug="excl-spelling-store",
            email="excl@x.com", plan="basic",
        )
        db.session.add(store)
        db.session.commit()
        for status, amount in (
            ("Sent", 100.0),
            ("Cancelled", 500.0),
            ("Rejected", 900.0),
        ):
            db.session.add(Transfer(
                store_id=store.id, send_date=date(2025, 12, 8),
                sender_name="Jane", company="Intermex",
                service_type="Money Transfer",
                send_amount=amount, fee=5.0, status=status,
            ))
        db.session.commit()

        kept = (
            db.session.query(Transfer)
            .filter(
                Transfer.store_id == store.id,
                Transfer.status.notin_(OWNER_TRANSFER_EXCLUDED),
            )
            .all()
        )
        assert [t.status for t in kept] == ["Sent"], (
            "only the live transfer should survive the filter"
        )
        assert sum(float(t.send_amount) for t in kept) == 100.0
