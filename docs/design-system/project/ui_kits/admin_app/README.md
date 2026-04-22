# Admin App UI Kit — DineroBook

In-product recreation: navy fixed sidebar + sticky topbar + scrollable content with dashboard, transfers, and daily report views. Based on `templates/base.html`, `dashboard_admin.html`, `transfers.html`, `_transfers_table.html`, and `daily_report.html`.

Components:
- `Sidebar.jsx` — 240px navy sidebar with brand block, user block, grouped nav (Workspace / Books / Finance / Account), footer sign-out
- `Topbar.jsx` — 58px sticky white bar with page title + right-side date and theme toggle
- `TrialBanner.jsx` — yellow/red banner state machine for trial countdown
- `StatCards.jsx` — the 4-6 KPI cards with gradient accents
- `TransfersTable.jsx` — transfers list with filters, status badges, and pagination
- `DailyReport.jsx` — the section-box form for daily cash + sales
- `Dashboard.jsx` — composes stat cards + company-by-month grid + recent transfers + ACH batches

`index.html` wires it together as a clickable prototype — sidebar switches pages.
