"""ReportImport — ingest remittance-company daily settlement reports.

Money-service businesses receive a next-day "close of day" report from
each company (Intermex, Maxi, Barri, …) listing every transaction that
settled. Instead of re-keying those into the money-transfer log by
hand, this module parses the report and (in later PRs) stages the rows
for operator review, then commits them as ``Transfer`` records — which
in turn auto-populate the daily book's money-transfer breakdown.

Design notes:
- **Deterministic first.** These reports are text-based PDFs, so we
  parse them with a plain text extractor + regex — no OCR, no vision
  model, no per-call cost. A vision fallback for photographed/scanned
  reports is future work.
- **Parse ≠ commit.** Parsing is pure and side-effect-free. Nothing
  touches the ledger until an operator reviews + approves the staged
  rows (later PR). Money accuracy + auditability require the human in
  the loop.

Company parsers live under ``Services/`` — one per company, since the
report layouts differ. ``intermex.py`` is the first.
"""
