# DailyBook — Invariants

> **Read this before editing anything in `api/Modules/DailyBook/`,
> `frontend/src/routes/EditDailyBook.tsx`, or `frontend/src/api/dailybook.ts`.**
>
> The daily book is the per-store, per-day money-flow ledger.
> Real US dollars depend on it being correct. Casual edits to "fix"
> something here can silently drift the monthly P&L, the over/short
> calculation, the bank-deposit envelope, or the federal-tax
> withholding without any visible UI signal.
>
> Every rule below is enforced by tests in
> `tests/Modules/DailyBook/`. Breaking one of these invariants will
> break a test. If you find yourself needing to break a rule, the
> change deserves its own design discussion + a separate PR — don't
> sneak it in as a "small fix".


## What the daily book is

One row in `daily_report` per `(store_id, report_date)` capturing
every dollar that moved through the store that day. The
`DailyReport.over_short` field is what the operator literally cares
about — "did the cash drawer reconcile?" Everything else in this
module exists to compute it correctly.

The store closes the day by **locking** the report (`locked_at` set
to a timestamp + `locked_by` set to the admin's user id). Once
locked, the row is immutable until an admin unlocks it.


## Data model

Five tables, three of them line-item-shaped:

| Table | What it holds |
|---|---|
| `daily_report` | The per-day P&L stub. One row per `(store, date)`. |
| `daily_line_item` | Generic time + amount + note rows keyed by `kind`. Backs every list-shaped section of the book (drops, deposits, cash purchases, etc.). |
| `daily_drop` | Legacy bespoke table for outside-cash drops. **Preserved for historical data; new writes go through `daily_line_item` with `kind='drop'`.** Don't add new code that reads from this table — see `Services/kinds.py` line 40-44. |
| `check_deposit` | Same story as `daily_drop` — legacy, preserved for history, new writes go through `daily_line_item` with `kind='check_deposit'`. |
| `mt_summary` | Per-(store, date, company) money-transfer roll-up: amount, fees, commission, federal_tax. Source of truth for `DailyReport.money_transfer`. |

The `DailyReport` row has ~25 dollar columns. They fall into THREE
categories, and **the category determines whether you can write to
the field directly**.


## The three field categories — DO NOT MIX THEM UP

### Category 1: Operator-editable

The cashier types these directly into the form. Writable via
`PUT /api/v2/daily/{store_id}/{report_date}`. The canonical list
lives in `api/Modules/DailyBook/Services/reports.py` ::
`EDITABLE_REPORT_FIELDS` and must be kept in sync with the
frontend's `EDITABLE_KEYS` in `EditDailyBook.tsx`.

```
taxable_sales, non_taxable, sales_tax,
bill_payment_charge, phone_recargas, boost_mobile,
money_order, check_cashing_fees, return_check_hold_fees,
forward_balance, from_bank, rebates_commissions,
cash_deposit, safe_balance, payroll_expense,
over_short
```

Plus `notes` (text, separate parameter).

**`forward_balance` is conditionally operator-editable.** It is in
`EDITABLE_REPORT_FIELDS` (so the schema accepts it), but it only
honours the operator's value on the store's **first logged day**.
From the second logged day on it is **auto-carried** — see
"Forward-balance carry" below.

### Category 2: Line-item-derived

These columns are the **sum of `daily_line_item` rows** with the
matching `kind`. The mapping is canonical in
`api/Modules/DailyBook/Services/kinds.py` :: `LINE_ITEM_KINDS`:

| `DailyReport` field | `daily_line_item.kind` | Operator action |
|---|---|---|
| `return_check_paid_back` | `return_payback` | Record a customer paying back a bounced check |
| `cash_purchases` | `cash_purchase` | Petty-cash purchase out of the drawer |
| `cash_expense` | `cash_expense` | Cash paid for an expense (utility bill, etc.) |
| `check_purchases` | `check_purchase` | Wrote a check for a purchase |
| `check_expense` | `check_expense` | Wrote a check for an expense |
| `other_cash_in` | `other_cash_in` | Catch-all ad-hoc receipt |
| `other_cash_out` | `other_cash_out` | Catch-all ad-hoc payout |
| `outside_cash_drops` | `drop` | Cashier dropped excess cash to the safe / ATM |
| `checks_deposit` | `check_deposit` | Trip to the bank with checks |

**These fields are NOT writable via the daily-report PUT.** They get
recomputed by `_recompute_line_items_total` on every line-item
add / delete / edit. If you try to PUT them, the schema's
`extra="forbid"` rejects with HTTP 422 — and that 422 is INTENTIONAL.

### Category 3: Cross-table-derived

Only one field today:

| Field | Source | Endpoint |
|---|---|---|
| `money_transfer` | Sum of `mt_summary` rows for `(store, date)` | `PUT /api/v2/daily/{store}/{date}/mt-breakdown` |

`money_transfer` is treated like Category 2 by the daily PUT — it's
NOT in the writable schema. Try to PUT it and you'll 422. This
was a real bug in `EditDailyBook.tsx` (had `money_transfer` in
`EDITABLE_KEYS`, save broke with 422); see test
`test_put_rejects_extra_fields`.


## The 422 trap — explicit DO-NOT-WRITE list

Any code that constructs the daily-report PUT body MUST NOT include
these fields, or the request 422s:

- `money_transfer` (Category 3 — mt-breakdown endpoint)
- `return_check_paid_back` (Category 2 — return_payback kind)
- `cash_purchases` (Category 2 — cash_purchase kind)
- `cash_expense` (Category 2 — cash_expense kind)
- `check_purchases` (Category 2 — check_purchase kind)
- `check_expense` (Category 2 — check_expense kind)
- `other_cash_in` (Category 2 — other_cash_in kind)
- `other_cash_out` (Category 2 — other_cash_out kind)
- `outside_cash_drops` (Category 2 — drop kind)
- `checks_deposit` (Category 2 — check_deposit kind)

Plus the database-managed fields (id, store_id, report_date,
locked_at, locked_by, updated_at) and the computed properties
(total_receipts, total_disbursements).


## Math invariants — characterization

`DailyReport.total_receipts` (Python `@property`):
```
total_receipts = taxable_sales + non_taxable + sales_tax
                + bill_payment_charge + phone_recargas + boost_mobile
                + money_transfer + money_order
                + check_cashing_fees + return_check_hold_fees
                + return_check_paid_back
                + forward_balance + from_bank + other_cash_in
                + rebates_commissions
```

`DailyReport.total_disbursements` (Python `@property`):
```
total_disbursements = cash_purchases + cash_expense
                    + check_purchases + check_expense
                    + outside_cash_drops
                    + cash_deposit + checks_deposit
                    + payroll_expense + other_cash_out
```

`DailyReport.net` (in the read response):
```
net = total_receipts - total_disbursements
```

`MoneyTransferSummary.individual_total`:
```
individual_total = amount + fees + commission + federal_tax
```

**Do not change these formulas** without coordinating with the
monthly P&L module (`api/Modules/Monthly/`), which sums these into
monthly totals.


## Forward-balance carry

`forward_balance` is the opening cash a day starts with. It is
**auto-carried from the previous logged day**:

```
forward_balance(today) = prior.outside_cash_drops + prior.safe_balance
```

where `prior` is the most recent report with `report_date <` today
(`find_prior_report` — "previous *logged* day", so a store closed
Sunday carries Saturday's close into Monday; a bare GET never
creates a row, so gaps are skipped, not zero-filled).

Rules:

- **First logged day** (no prior report): `forward_balance_auto` is
  `False`. The operator seeds the opening balance by hand and the
  field is editable. This is the ONLY day it's editable.
- **Every later day**: `forward_balance_auto` is `True`. The editor
  renders the field read-only; `update_daily_report` **ignores any
  client-sent `forward_balance` and forces the carried value**, so a
  stale or tampered form can't clobber it (same posture as the auto
  sales-tax field).
- `summarize_report` overrides the stored column with the fresh
  carry value on read and adjusts `total_receipts` / `net` by the
  delta — so editing yesterday's drops/safe is reflected on today
  even before today is re-saved. `carry_forward_from(prior)` is the
  single source of the formula (Services/reports.py).
- **`summarize_period` does NOT override** — the range report uses
  the stored column (`forward_balance_auto` defaults `False` there).
  Fine because the value was forced-correct at each day's save.
- **`forward_balance` does NOT feed the Monthly P&L.** Monthly's
  `_DAILY_DERIVED_FIELDS` sums only cash/check purchases + expenses,
  payroll, and check-cashing fees — never `forward_balance`,
  `safe_balance`, or `outside_cash_drops`. So the carry only affects
  the daily book's own receipts / net / over-short display.

If you change the carry formula, update `carry_forward_from`,
`test_dailybook_services.py` (the `test_forward_balance_*` cases),
and this section together.


## Lock rules

`locked_at` is the kill-switch:

- `locked_at IS NULL`: the report is writable. Cashier can edit
  fields, add/remove line items, edit notes.
- `locked_at IS NOT NULL`: **every write to this report and ANY of
  its line items is rejected with HTTP 403** + the message
  `"Daily report is locked — unlock it before editing."` — including
  the `notes` field. This is by design (see
  `test_put_rejects_locked_report`); a locked report is an
  archived close-out.

To re-open: `POST /api/v2/daily/{store}/{date}/unlock` (admin /
owner / superadmin only). The unlock writes an operator audit row.


## Audit invariants

Every mutation through the FastAPI controllers writes an
operator-audit row via `_audit_daily_action`. The intent is logged,
not the dollar amounts (sensitive numbers like `over_short` and the
disbursement totals stay out of the audit summary). Don't bypass
this — search for `_audit_daily_action` and copy the pattern.

Actions audited today:
- `update_daily_report` (summary: comma-separated list of fields
  the operator touched)
- `lock_daily_report` / `unlock_daily_report`
- Line-item create / **update** / delete

If you add a new mutation route to this module, add the matching
`_audit_daily_action` call.


## Cross-module dependencies

The daily book feeds:

- **Monthly P&L** (`api/Modules/Monthly/`): sums daily totals into
  the monthly roll-up. Several `DailyReport` fields back specific
  monthly lines via `_BANK_CATEGORY_PL_FIELD`. Changing the field
  set here can break monthly without warning.
- **Transfers** (`api/Modules/Transfers/`): the per-(store,
  date, company) `mt_summary` table is the source of truth for
  `DailyReport.money_transfer`.  Cashier-entered transfers in
  `Transfer` do NOT auto-update `mt_summary` — the operator
  applies them via the MT-breakdown editor (`PUT
  /api/v2/daily/{store}/{date}/mt-breakdown`), which is the only
  write path.  The editor's auto-fill defaults come from
  `summarize_transfers_for_day` reading `Transfer` rows, but
  applying them is an explicit action — that's why a fresh day
  pre-fills with the day's totals and an overridden day keeps
  the cashier's edits.
- **Bank sync** (`api/Modules/BankSync/`): some bank-charge rows
  feed line-item kinds (see `BUILTIN_BANK_RULES`). Those line items
  show up under the existing line-item-derived fields.
- **Return checks** (`api/Modules/ReturnChecks/`): recording a
  return-check payback creates a `daily_line_item` with
  `kind='return_payback'` whose amount rolls into
  `return_check_paid_back`.

**Net rule**: never make daily-report fields depend on each other
in custom server-side logic. If A depends on B, model that
dependency via the line-item system or a derivation function —
don't fan it out across the codebase.


## What's safe to change

The daily book is conservative. Things that are safe:

- Adding a new operator-editable field: append to
  `EDITABLE_REPORT_FIELDS`, add the column to the model, add an
  Alembic migration, add the field to `DailyReportUpdateRequest`,
  add to `EDITABLE_KEYS` in `EditDailyBook.tsx`. The new field
  shows up in `total_receipts` / `total_disbursements` ONLY if you
  also add it to the `@property` formula.
- Adding a new line-item kind: one entry in `LINE_ITEM_KINDS`, one
  column on `DailyReport` for the rolled-up sum, one migration.
  `_recompute_line_items_total` handles the rest.
- UI changes that don't touch the field set (layout, animations,
  styling).
- Tests pinned to existing behavior.

Things that need a design discussion FIRST:

- Changing the `total_receipts` / `total_disbursements` / `net`
  formulas.
- Changing the locked-day rules (e.g. allowing notes edits when
  locked).
- Adding cross-field validation (e.g. "over_short can't exceed
  $X") — these have a way of being wrong in production.
- Adding a new computed property to the read response.
- Renaming or removing any existing field — historical reports
  depend on the names being stable across the read path.


## Test surface

`tests/Modules/DailyBook/` covers:

- `test_dailybook_controllers.py` — every PUT / POST / GET route,
  including the locked-day 403 + the derived-field 422.
- `test_dailybook_services.py` — `update_daily_report`,
  `ensure_daily_report`, `lock_report`, `unlock_report`.
- `test_dailybook_repository.py` — `find_report_by_date`,
  `list_reports_in_period`.
- `test_line_items_service.py` — line-item CRUD + the
  `_recompute_line_items_total` invariant.
- `test_kinds_service.py` — `LINE_ITEM_KINDS` registry helpers.
- `test_lock_service.py` / `test_locks_service.py` — lock state.
- `test_mt_breakdown.py` — `money_transfer` derivation from
  `mt_summary` rows.
- `test_transfers_summary.py` — Transfer → `mt_summary` recompute.
- `test_audit_coverage.py` — every mutation route writes an
  audit row.

Before changing this module, run:

```bash
pytest tests/Modules/DailyBook/ -v
```

If any test fails, you've broken an invariant. Either:
1. Your change is wrong — fix it.
2. The invariant has genuinely changed — update the test AND this
   document AND open a PR that's explicit about the contract
   change.
