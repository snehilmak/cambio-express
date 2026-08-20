# Monthly P&L — Invariants

> **Read this before editing anything in `api/Modules/Monthly/`,
> `frontend/src/routes/EditMonthly.tsx`, or `frontend/src/api/monthly.ts`.**
>
> The monthly P&L is the per-store, per-month profit-and-loss
> roll-up that feeds the tax export. Casual edits to "fix"
> something here can quietly drift the year-end numbers, cause
> bank-charges to double-count, or let a tampered client overwrite
> the locked daily-ledger sums without any visible UI signal.
>
> Every rule below is enforced by tests in
> `tests/Modules/Monthly/` and `tests/test_monthly_locked_fields.py`.
> Breaking one of these invariants will break a test. If you find
> yourself needing to break a rule, the change deserves its own
> design discussion + a separate PR — don't sneak it in as a
> "small fix".


## What the monthly P&L is

One row in `monthly_financial` per `(store_id, year, month)`
capturing the per-month roll-up: income lines, purchases,
expenses, the return-check write-offs, bank charges, and the
end-of-month adjustments (over/short, borrowed-money returns,
profit distributed, cash carry-forward).

It is the **bookkeeping output** of the daily ledger — the daily
book is the raw cash flow, the monthly P&L is the accountant-
readable view of the same money rolled up to a month + augmented
with cross-month adjustments.

Unlike `daily_report`, the monthly row has **no lock state**. The
data inputs are locked (see "Field categories" below), but the
row itself stays editable forever.


## Data model

One table:

| Table | What it holds |
|---|---|
| `monthly_financial` | The per-month P&L row. ~30 numeric columns + `notes`. UNIQUE on `(store_id, year, month)`. |

That's it. Every other table the P&L cares about (`daily_report`,
`bank_transaction`, the return-check workflow) is read on save and
the resulting sums are written into the matching columns here.


## The three field categories — DO NOT MIX THEM UP

### Category 1: Operator-editable

The cashier types these directly into the form. Writable via
`PUT /api/v2/monthly/{year}/{month}`. The canonical list lives in
`api/Modules/Monthly/Services/write.py` :: `EDITABLE_MONTHLY_FIELDS`:

```
taxable_sales, non_taxable, bill_payment_charge,
phone_recargas, boost_mobile,
return_check_hold_fees, rebates_commissions,
mt_commission_in_bank,
other_income_1, other_income_2, other_income_3,
credit_card_fees, money_order_rent, emaginenet_tech,
irs_payroll_tax, texas_workforce, other_taxes,
accounting_charges,
other_expense_1, other_expense_2, other_expense_3,
other_expense_4, other_expense_5,
over_short, borrowed_money_return, profit_distributed,
cash_carry_forward
```

Plus `notes` (text, separate handling — popped from the payload
before `setattr`).

### Category 2: Daily-ledger-derived (always locked)

These columns are the **sum of `daily_report` rows for the month**.
The mapping is canonical in
`api/Modules/Monthly/Services/write.py` :: `_DAILY_DERIVED_FIELDS`:

| `MonthlyFinancial` field | `DailyReport` field | What it sums |
|---|---|---|
| `cash_purchases`     | `cash_purchases`     | Cash drawer petty purchases |
| `check_purchases`    | `check_purchases`    | Checks written for purchases |
| `cash_expenses`      | `cash_expense`       | Cash paid for expenses (singular on DailyReport — historic) |
| `check_expenses`     | `check_expense`      | Checks written for expenses |
| `cash_payroll`       | `payroll_expense`    | Cash paid for payroll |
| `check_payroll`      | `payroll_check`      | Payroll paid by check (skips the daily book's totals by design) |
| `check_cashing_fees` | `check_cashing_fees` | Fee revenue from check cashing |

**These fields are NOT writable via the monthly PUT.** They get
overwritten by `_sum_daily(...)` on every save. If you try to PUT
them, the schema's `extra="forbid"` rejects with HTTP 422 — and
that 422 is INTENTIONAL.

The contract is "**always trust the daily ledger, never the stored
MonthlyFinancial value**". This means:

- Re-saving the monthly P&L picks up fresh daily edits — even ones
  made after the first save.
- Backdating a daily-book entry (e.g. recording a missed cash
  expense for the 5th in the middle of the month) automatically
  flows into the locked column the next time the operator saves
  the monthly.
- Tampered PUT bodies that include any of these field names get
  the whole payload rejected — not silently overwritten.

### Category 3: Cross-table-derived

Two fields today:

| Field | Source | Lock semantics |
|---|---|---|
| `return_check_gl` | `Owners.Services.return_check_monthly_pl` (signed) | Always overwritten on save |
| `bank_charges_total` | `BankSync.Services.bank_charges_for_month(prefix="bank_charge")` | **Conditionally locked** — see below |

`return_check_gl` uses EXPENSE convention: positive value means net
loss for the month, negative means net gain. The OPPOSITE convention
appears in the owner dashboard — see `Owners/Services/return_checks.py`
docstring.

`bank_charges_total` is the **only field with conditional locking**.
The rule (from `update_monthly`):

```python
auto_bc = _auto_bank_charges_total(...)
if auto_bc > 0:
    setattr(row, "bank_charges_total", auto_bc)           # lock
elif "bank_charges_total" in fields:
    setattr(row, "bank_charges_total", float(fields[...])) # accept manual
```

So:

- **Bank-sync active + has charges this month** → server value wins.
- **Bank-sync inactive (or no charges this month)** → operator's
  typed value wins.

This is deliberate: stores on the Basic plan (no bank sync) need to
type the number in by hand. Don't unconditionally lock it or you'll
wipe Basic-plan stores' manual entries on every save.

Both `return_check_gl` and `bank_charges_total` are NOT in
`EDITABLE_MONTHLY_FIELDS`. `bank_charges_total` IS in the schema
(`MonthlyUpdateRequest`) — that's how the operator types it when
bank sync isn't active. `return_check_gl` is NOT in the schema —
the workflow is the only path that touches it.


## The 422 trap — explicit DO-NOT-WRITE list

Any code that constructs the monthly-P&L PUT body MUST NOT include
these fields, or the request 422s:

- `cash_purchases` (Category 2 — daily-derived)
- `check_purchases` (Category 2 — daily-derived)
- `cash_expenses` (Category 2 — daily-derived)
- `check_expenses` (Category 2 — daily-derived)
- `cash_payroll` (Category 2 — daily-derived)
- `check_payroll` (Category 2 — daily-derived)
- `check_cashing_fees` (Category 2 — daily-derived)
- `return_check_gl` (Category 3 — return-check workflow)
- `bank_charges_210` (legacy split, no longer rendered)
- `bank_charges_230` (legacy split, no longer rendered)

Plus the database-managed fields (`id`, `store_id`, `year`,
`month`, `updated_at`) and the computed properties
(`total_income`, `total_expenses`, `net_profit`).

`bank_charges_total` IS allowed in the PUT — but the server will
overwrite the client value when bank-sync data is present (see
Category 3 above).


## Math invariants — characterization

`MonthlySummary.total_income` (computed in
`api/Modules/Monthly/Services/monthly.py`):

```
total_income = taxable_sales + non_taxable
             + bill_payment_charge + phone_recargas + boost_mobile
             + check_cashing_fees + return_check_hold_fees
             + rebates_commissions + mt_commission_in_bank
             + other_income_1 + other_income_2 + other_income_3
```

`MonthlySummary.total_expenses`:

```
total_expenses = cash_purchases + check_purchases
               + cash_expenses + check_expenses + cash_payroll
               + check_payroll
               + bank_charges_total + credit_card_fees
               + money_order_rent + emaginenet_tech
               + irs_payroll_tax + texas_workforce + other_taxes
               + accounting_charges + return_check_gl
               + other_expense_1 + other_expense_2 + other_expense_3
               + other_expense_4 + other_expense_5
               + over_short + borrowed_money_return + profit_distributed
```

`MonthlySummary.net_profit`:

```
net_profit = total_income - total_expenses
```

**Note**: `over_short`, `borrowed_money_return`, and
`profit_distributed` sit in the EXPENSE bucket above. They're
operator-editable adjustments that reduce net profit when positive.
This is the legacy template's bucketing — don't move them.

The legacy `MonthlyFinancial.total_revenue` / `total_purchases` /
`total_expenses` / `net_income` `@property`s on the model use a
DIFFERENT bucketing (purchases as their own line; `bank_charges_210`
+ `bank_charges_230` instead of `bank_charges_total`; `over_short`
ADDED to net_income instead of subtracted). These properties are
preserved for the old Jinja template + the BI report; the React
SPA reads the `MonthlySummary` shape above. **If you touch one, the
other still has consumers.**


## Auto-derive contract — "trust the ledger, never the stored value"

The order of operations in `update_monthly` is:

1. Apply operator-editable fields from the request body
   (`EDITABLE_MONTHLY_FIELDS` only).
2. Overwrite every Category 2 field from `_sum_daily(...)`.
3. Overwrite `return_check_gl` from the workflow.
4. Conditionally write `bank_charges_total` (lock when > 0).
5. Set `notes` + `updated_at`.

This means:

- A locked field always reflects the **current** state of the
  underlying ledger — not whatever was stored last time.
- Operator-editable values from the same payload are NOT lost when
  the locked fields refresh; they're written first.
- A blank PUT (`{"notes": ""}`) is enough to re-roll the locked
  fields without touching any operator value.

Don't reorder these steps — the locked-field refresh has to happen
AFTER the operator-editable write so a payload that includes both
doesn't have its operator values clobbered by leftover model state.


## Audit invariants

No audit log on the monthly write today. Mutations don't go through
`_audit_daily_action` (that's the DailyBook helper). If you add
audit coverage in the future, mirror the DailyBook pattern: log the
operator + the comma-separated list of fields they actually
touched, NOT the dollar amounts (the P&L numbers are sensitive).


## Cross-module dependencies

The monthly P&L reads from:

- **DailyBook** (`api/Modules/DailyBook/`): every Category 2 field
  is `Σ DailyReport.<field>` for the month. Editing a daily row
  changes the next monthly save's locked-field values.
- **BankSync** (`api/Modules/BankSync/`): `bank_charges_total` =
  `Σ BankTransaction WHERE category_slug LIKE 'bank_charge%'` for
  the month. Includes the legacy `bank_charge` slug + every
  per-account slug (`bank_charge_210`, `bank_charge_230`, future
  `bank_charge_<last4>`). The prefix match means new built-in
  rules auto-flow without registry maintenance.
- **ReturnChecks** (via `api/Modules/Owners/Services/`):
  `return_check_gl` = `-(period_aggregates['net_gl'])` for the
  month. The sign flip converts the owner-dashboard convention
  (positive = gain) to the P&L convention (positive = expense /
  loss).

The monthly P&L feeds:

- **Reports** (`api/Modules/Reports/`): per-store + platform-wide
  monthly roll-ups, CSV / Excel exports. Schema changes here
  propagate via the registry — but if you rename a field, the
  CSV column header drifts too.
- **Superadmin BI** (`api/Modules/Superadmin/`): aggregated
  cross-store totals.

**Net rule**: never make monthly fields depend on each other in
custom server-side logic. If A depends on B, model that dependency
via the daily-ledger / bank-charge / return-check feed — don't fan
it out across the codebase.


## What's safe to change

Things that are safe:

- Adding a new operator-editable field: add the column to the
  model, add an Alembic migration, append to
  `EDITABLE_MONTHLY_FIELDS`, append to `MonthlyUpdateRequest`,
  append to `MonthlyRow`, append to the form's editable map in
  `frontend/src/routes/EditMonthly.tsx`. Add the field to the
  matching income or expense field list in
  `Services/monthly.py` (`INCOME_FIELDS` / `EXPENSE_FIELDS`) if it
  should flow into the totals.
- Adding a new daily-derived field: one entry in
  `_DAILY_DERIVED_FIELDS`, one matching column on
  `MonthlyFinancial`, one migration. The auto-derive on save
  handles the rest.
- Adding a new built-in bank-charge rule: it auto-flows into
  `bank_charges_total` via the `bank_charge%` prefix match. No
  monthly-side change needed unless you want a separately-displayed
  line.
- UI changes that don't touch the field set (layout, tooltips,
  animations).
- Tests pinned to existing behavior.

Things that need a design discussion FIRST:

- Changing the `total_income` / `total_expenses` / `net_profit`
  formulas.
- Adding cross-field validation (e.g. "over_short can't exceed
  $X") — these have a way of being wrong in production.
- Reordering the steps in `update_monthly` (the order matters —
  see "Auto-derive contract" above).
- Unconditionally locking `bank_charges_total` (you'll wipe
  Basic-plan stores' manual entries).
- Renaming or removing any existing column — historical rows
  depend on the names being stable across the read path.
- Adding audit coverage (mirror the DailyBook pattern — don't
  invent a new one).
- Moving `over_short` / `borrowed_money_return` /
  `profit_distributed` out of the EXPENSE bucket on the
  service-layer DTO without coordinating the change with the
  legacy `MonthlyFinancial.net_income` @property and the BI
  report consumers.


## Test surface

`tests/Modules/Monthly/` + `tests/test_monthly_locked_fields.py`
cover:

- `test_monthly_controllers.py` — every GET / PUT route, including
  the 404 on missing months, the 403 on non-admin / superadmin,
  the 422 on bad month + tampered fields.
- `test_monthly_locked_fields.py` — the daily-derived auto-fill
  contract, the 422 on tampered locked fields, the
  resave-refresh-from-ledger guarantee.
- `test_monthly_invariants.py` — parametrized 422-trap sweep over
  every read-only field + bedrock formula characterization.

Before changing this module, run:

```bash
pytest tests/Modules/Monthly/ tests/test_monthly_locked_fields.py -v
```

If any test fails, you've broken an invariant. Either:
1. Your change is wrong — fix it.
2. The invariant has genuinely changed — update the test AND this
   document AND open a PR that's explicit about the contract
   change.
