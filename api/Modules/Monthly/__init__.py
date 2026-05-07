"""Monthly module — Monthly P&L read-side for the SPA.

The legacy `/monthly` Jinja route renders the per-store, per-month
P&L breakdown. This module exposes the same data via
`/api/v2/monthly` so the SPA's monthly page can consume it.
Write-side (the auto-derived bank-charges + line-item totals
plus operator-editable fields) stays on Flask until subsequent
PRs migrate it.
"""
