# Source spreadsheets

Original Cambio Express master + monthly workbooks, used as the source of
truth for the daily-book and monthly P&L formulas.

- `master.xlsx` — empty template with every formula intact.
- `april-2026.xlsx` (or similar) — a real month's data for reference.

Drop the files here via the GitHub web UI ("Add file → Upload files" from
the `docs/spreadsheets/` folder) or by committing locally. Once they're
in, Claude reads them with `openpyxl` to mirror the formulas into the
`DailyReport` and `MonthlyFinancial` models.
