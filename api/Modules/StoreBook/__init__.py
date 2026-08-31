"""StoreBook — the Store Daily Book.

One sheet per store per business day for c-store / gas-station
operators, the counterpart to the MSB Daily Book. Replaces the
per-register "Day close" page as the daily workflow: register and
drawer detail becomes a section OF the day rather than a separate
destination (owner directive 2026-08-31).

The page is three columns that must balance:

    Sales           what the store took in
    Tenders         how it was paid, and what went back out
    Deposit & Balance   what was banked, and the closing position

``over_short`` is the whole point of the sheet: tenders minus
sales. Everything else exists to make that number explainable.

Values arriving from the POS keep their original alongside the
operator's edit (``StoreDailyEntryOriginal``), so correcting a
figure never destroys what the register actually reported.
"""
