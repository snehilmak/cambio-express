"""Backfill ``Transfer.federal_tax`` on historical rows.

The ``federal_tax`` column was added to ``Transfer`` after the
table was already populated. Existing rows have ``federal_tax=0``
even when they should have a non-zero value (Money Transfer
service type, non-domestic country, store has a non-zero
``federal_tax_rate``). This affects:

* Per-transfer audit display (the audit log shows "Tax" as $0).
* Aggregated reports that read ``Σ federal_tax`` (they
  under-report the IRS remittance for pre-column rows).
* ACH batch totals (``transfers_total = Σ (send_amount +
  federal_tax)`` — under-counted by the missing tax).

This script walks every Transfer row, recomputes the canonical
federal_tax via the same ``federal_tax_for`` helper that the
create/edit routes use, and persists the result. Idempotent: a
row that already has the correct value is a no-op.

Invocation::

    python -m scripts.backfill_federal_tax              # dry-run
    python -m scripts.backfill_federal_tax --commit     # apply

Dry-run prints how many rows would change + the total dollar
delta. Pass ``--commit`` to actually write.

By default the script logs every row it touches (id + before /
after). Set ``--quiet`` to only emit the summary.

Per CLAUDE.md invariant #9 (``Transfer.fee`` vs
``Transfer.federal_tax``), the math here is the single source of
truth and must match the create/edit path. The script imports
``federal_tax_for`` directly to ensure that.
"""
from __future__ import annotations

import argparse
import logging
import sys
from typing import Iterable

from api.Core.Database import SessionLocal
from api.Modules.Tenancy.Models import Store
from api.Modules.Transfers.Models import Transfer
from api.Modules.Transfers.Services.tax import federal_tax_for


logger = logging.getLogger("backfill_federal_tax")


def _iter_transfers(session, batch_size: int = 500) -> Iterable[Transfer]:
    """Stream transfers in id-order with yield_per so we don't
    pull every row into memory at once. A medium store has ~50k
    transfers; loading them all at once works but the streaming
    version is friendlier to constrained dev / staging envs.
    """
    q = session.query(Transfer).order_by(Transfer.id.asc())
    return q.yield_per(batch_size)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Recompute Transfer.federal_tax on every row. Dry-run "
            "by default; pass --commit to persist."
        ),
    )
    parser.add_argument(
        "--commit", action="store_true",
        help="Actually write the recomputed values to the DB.",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Only emit the summary line; suppress per-row logs.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    changed = 0
    scanned = 0
    delta = 0.0
    # Cache stores in-process. Most stores have many transfers, so
    # one DB hit per store is much cheaper than one per transfer.
    store_cache: dict[int, Store | None] = {}

    with SessionLocal() as session:
        for t in _iter_transfers(session):
            scanned += 1
            sid = t.store_id
            if sid is None:
                continue
            if sid not in store_cache:
                store_cache[sid] = session.get(Store, sid)
            store = store_cache[sid]
            if store is None:
                continue
            current = float(t.federal_tax or 0.0)
            expected = federal_tax_for(
                t.send_amount, t.service_type or "", store, t.country,
            )
            if abs(current - expected) < 0.005:
                continue  # already correct; idempotent
            row_delta = expected - current
            delta += row_delta
            changed += 1
            logger.info(
                "transfer id=%s store=%s service=%r country=%r "
                "send=%.2f federal_tax %s -> %s (Δ%+.2f)",
                t.id, sid, t.service_type or "", t.country or "",
                t.send_amount or 0,
                f"{current:.2f}", f"{expected:.2f}", row_delta,
            )
            if args.commit:
                t.federal_tax = expected
        if args.commit:
            session.commit()

    action = "WROTE" if args.commit else "would change"
    logger.warning(
        "%s %d / %d transfers; net Δ=%+.2f",
        action, changed, scanned, delta,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
