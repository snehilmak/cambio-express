# Transfers — Invariants

> **Read this before editing anything in `api/Modules/Transfers/`,
> `api/Modules/Customers/Services/customers.py` (the upsert path),
> `frontend/src/routes/NewTransfer.tsx`, or
> `frontend/src/routes/EditTransfer.tsx`.**
>
> The Transfer is the core revenue-bearing entity. Every fee dollar
> the store earns, every federal-tax dollar that leaves with the
> ACH withdrawal, flows through this module. A subtle bug here
> compounds: it shows up in the next ACH batch, in the monthly
> P&L, in the cashier productivity report, and in the customer's
> receipt. By the time anyone notices, the books have already
> been closed on the wrong numbers.
>
> Every rule below is enforced by tests in
> `tests/Modules/Transfers/`. Breaking one of these invariants
> will break a test. If you find yourself needing to break a rule,
> the change deserves its own design discussion + a separate PR.


## What a transfer is

One row in `transfer` per money-movement event a cashier logs:
remittance (send money to family abroad), bill payment, top up,
or recharge. The Transfer carries:

- the customer who sent it (linked to `Customer` for autofill on
  return visits; mirrored into `sender_*` columns on this row so
  the receipt prints correctly even after the Customer row is
  edited or deleted),
- the recipient details,
- the **money math** (`send_amount`, `fee`, `federal_tax`,
  `commission`),
- the **status** (Sent / Cancelled / etc.),
- the cashier who entered it (`created_by` for the login user +
  `employee_id` / `employee_name` for the "Processed by"
  attribution, which is the source of truth for
  cashier-productivity reports + payroll commission splits),
- the company (Intermex / Maxi / Barri / etc.).

Transfers are read-mostly: the typical cashier creates one,
maybe edits it once if a typo, rarely deletes. ACH batches +
monthly P&L sum across them; cancellation flips the status
without deleting the row (the audit trail needs it).


## Money math — the four-field invariant

Every transfer has four money fields:

| Field | Source | Who collects it |
|---|---|---|
| `send_amount` | Cashier enters | Goes to the recipient (via ACH) |
| `fee` | Cashier enters | **Store revenue** |
| `federal_tax` | **Server-computed** (see below) | Leaves with ACH; remitted to IRS |
| `commission` | Cashier enters (optional) | Internal — store's commission from the company |

**The bedrock formula** (`Transfer.total_collected`):

```
total_collected = send_amount + fee + federal_tax
```

That's what the customer hands over at the counter. It includes
the tax (which leaves) but NOT the commission (which is internal
accounting between the store and the wire company; the customer
doesn't pay it).

Reports that aggregate transfers (Sales by Company, Sales by
Employee, ACH Volume, etc.) follow the same formula. **Do not
change it.** Page-total sums in `list_transfers` use the same
expression — keep them in sync.

## Federal tax — server-computed, never client-supplied

`federal_tax` is the single most-corrupted field in this system
if you let the client send it. The rule:

> `federal_tax` is **always** recomputed server-side from
> `(send_amount, service_type, country, store)` via
> `federal_tax_for()` in `api/Modules/Transfers/Services/tax.py`.

The create + edit endpoints intentionally drop any `federal_tax`
the client sends. The Pydantic schema (`CreateTransferRequest`)
doesn't even list `federal_tax` as a field — `extra="forbid"`
makes sending it a 422.

`federal_tax_for()` returns 0.0 in three cases:

1. `service_type` is in `TAX_EXEMPT_SERVICES` (Bill Payment,
   Top Up, Recharge — no ACH withdrawal crosses a border).
2. Recipient `country` is in `DOMESTIC_COUNTRIES` (today: just
   "United States" — the federal tax is the IRS levy on money
   sent abroad).
3. The store has no `federal_tax_rate` set (defensive — defaults
   to 0.01 = 1% in seed data).

Otherwise: `round(send_amount * store.federal_tax_rate, 2)`.

**Anti-drift rules:**

- Don't let "edit transfer" preserve a federal_tax from the
  before-state. Always recompute — the tax rate could have
  changed at the store level, or the cashier could have changed
  the country/service_type.
- Don't move the tax computation into `before_insert` /
  `before_update` SQLAlchemy hooks. The Service layer being the
  single chokepoint is the invariant — hooks add a parallel
  write path that's easy to forget about in tests.
- Don't try to "optimize" by skipping the recompute when
  fields appear unchanged. The recompute is cheap; the bug
  surface of conditional skipping is not.

## Service-type vocabulary

The complete set of valid `service_type` values lives in
`api/Modules/Transfers/Services/tax.py::SERVICE_TYPES`:

- `"Money Transfer"` — the historical default + the only tax-
  carrying service
- `"Bill Payment"` — tax-exempt
- `"Top Up"` — tax-exempt
- `"Recharge"` — tax-exempt

The transfer form's dropdown options MUST match this tuple
exactly. `normalize_service_type()` coerces unknown values to
`"Money Transfer"` (the historical default) rather than failing
loudly — this is intentional so a malformed payload can't
accidentally disable tax. Adding a new service type means:

1. Append to `SERVICE_TYPES`
2. Decide whether it's tax-exempt; if so add to
   `TAX_EXEMPT_SERVICES`
3. Update the dropdown options in `NewTransfer.tsx` +
   `EditTransfer.tsx`
4. Add a test variant in `tests/Modules/Transfers/test_tax_service.py`


## Customer upsert — owner-umbrella scope

The transfer form's "sender" block triggers a
`Customers.Services.upsert()` call on every save. The Customer
row is the source of truth for the autofill suggestions on
return visits, the cross-store directory, and the recent-
recipients hints.

**Lookup priority** (canonical contract in `customers.py`
docstring + `upsert()` body):

1. **Explicit `customer_id`** — the SPA passes this when the
   sender autocomplete picks an existing row. We accept the id
   ONLY if the target customer lives in the **owner umbrella**
   (`sibling_store_ids(db, store_id)`), never beyond. A cashier
   at one owner's store can't accidentally re-link a transfer
   to a customer from a different owner's store.
2. **`(phone_country, phone_number)` across the umbrella** —
   when the sender's phone matches an existing customer at ANY
   store in the owner umbrella, we reuse that customer row. A
   sender who's been to Store A and now shows up at Store B
   (same owner) gets one customer record, not two.
3. **Otherwise create new** — a fresh `Customer` row pinned to
   the current `store_id` (the "home store"). Later transfers
   at sibling stores point `customer_id` at this row; they don't
   create a duplicate.

The home store of a Customer **never moves**. A customer first
seen at Store A stays pinned to Store A in the `customer.
store_id` column even when they show up at Store B (same
owner). Sibling stores just reference the existing row by id.

**Last write wins** on every non-empty field. If a customer
visits Store B and the cashier updates their address, the
shared Customer row is updated — Store A sees the new address
next time too.

**Anti-drift rules:**

- `sibling_store_ids()` is the SINGLE chokepoint that defines
  the owner umbrella scope. Don't add new "is this customer
  visible to this store?" predicates elsewhere — extend that
  function instead.
- Unrelated stores (no shared owner) stay isolated. The phone
  match in step 2 ranges over the umbrella, NOT over every
  store in the platform.
- The `customer_id` passed in step 1 isn't trusted. We re-look-
  up by id with `find_by_id_in_stores(siblings)` so a forged
  payload can't link to a stranger's row.

## Status state machine

`Transfer.status` is a free-form string column today (legacy)
but only a handful of values are in active use:

- `"Sent"` — default, the happy path. Counts toward all
  reports, batch totals, monthly P&L.
- `"Cancelled"` — the transfer was reversed before settlement.
  The row stays for audit; reports filter it out via
  `status != "Cancelled"`.
- `"Pending"` — rarely used today. Reports treat as `"Sent"`.

**No deletion on cancel.** A cancelled transfer keeps the row so
the audit history survives. Hard-delete is a separate action via
`DELETE /api/v2/transfers/{id}` (admin-only; cascades the
`TransferAudit` rows).

## Audit invariants

Every mutation writes a `TransferAudit` row via
`Services/audit.py::record_audit`:

- `create_transfer` → action `"created"`, summary `"Logged by
  {employee_name}."`
- `update_transfer` → action `"updated"` OR `"status_changed"`
  (the latter when ONLY the status field changed; the admin UI
  highlights these), summary built from `summarize_changes`
  (before/after diff capped at 4 fields + "+N more" overflow).
- `delete_transfer` → no `TransferAudit` row (the cascade
  deletes the existing audit rows — operator's audit log gets
  its own entry via `OperatorAuditLog`).

The `TRANSFER_AUDIT_FIELDS` list defines which Transfer columns
get audited. Adding a column to that list adds it to the diff
summary; removing one silently stops auditing it (bad).
Internal columns (commission, internal_notes) are intentionally
NOT in the audit list — operator-only context, not legally-
relevant.

**Don't bypass the audit.** Every controller that mutates a
Transfer must call `record_audit`. Search for `record_audit` in
the Transfers Controllers if adding a new mutation route.

## Employee attribution ("Processed by")

Every transfer carries both:

- `created_by` — the **login user** who saved the row. Used
  for "who pressed Save", not for productivity metrics.
- `employee_id` + `employee_name` — the **named-employee
  roster pick** the cashier made in the "Processed by"
  dropdown. This is the source of truth for cashier-
  productivity reports + payroll commission splits.

These are SEPARATE concepts on purpose:
- A store manager can save transfers on behalf of a cashier who
  forgot to log one — `created_by` reflects the manager, but
  `employee_name` is the cashier who actually took the cash.
- The `employee_name` is **snapshotted** at save-time. If the
  StoreEmployee is later renamed, deactivated, or deleted, the
  transfer still shows the original name. Reports group by the
  name string, not by the FK, for this reason.

`pick_employee()` in `Services/form_inputs.py` is the only
helper that should resolve a roster id → `(StoreEmployee,
str)` pair. The create + edit endpoints require it to return a
non-None employee — anonymous transfers aren't allowed.

## Cross-module dependencies

- **Batches** (`api/Modules/Batches/`): aggregates transfers
  into ACH batches. `ACHBatch.transfers_total = Σ (send_amount
  + federal_tax)` (NOT plus fee — fee is store revenue and
  doesn't ride the ACH). Breaking the fee-vs-tax split here
  silently corrupts batch totals.
- **Monthly P&L** (`api/Modules/Monthly/`): sums transfer
  `(send_amount + fee + federal_tax)` into the monthly receipt
  line. Reads from `transfer` directly + the per-(store, date,
  company) `mt_summary` table (see below).
- **DailyBook** (`api/Modules/DailyBook/`): the per-store /
  per-date `mt_summary` table is the per-company roll-up the
  daily book reads. **Not auto-recomputed from `transfer` rows**
  — the cashier updates it manually via the MT-breakdown editor
  on the daily-book page (`PUT /daily/{store}/{date}/mt-
  breakdown`). The auto-fill defaults shown in that editor DO
  come from `summarize_transfers_for_day` reading `transfer`
  rows, but applying them is an explicit action.
- **Customers** (`api/Modules/Customers/`): every transfer save
  upserts a customer (see above). Customer merge / delete
  reassigns transfers via `customer_id`.
- **ReturnChecks** (`api/Modules/ReturnChecks/`): independent
  of transfers, but receipts can reference both.

**Net rule**: a Transfer write should not directly mutate
`mt_summary`, `ach_batch`, `monthly_financial`, or any other
roll-up table. Those tables either re-derive on demand
(monthly P&L) or have their own write paths (batches, MT
breakdown). Adding a fan-out from Transfer-write to a roll-up
table is the kind of change that creates phantom drift bugs.

## Indexes

The Transfer model defines five indexes (see model file). All
are load-bearing on hot-path queries:

- `ix_transfer_store_send_date` — every period filter on every
  Reports aggregator.
- `ix_transfer_customer_id` — umbrella-customer + new-vs-
  returning lookup.
- `ix_transfer_created_by` — sales-by-employee + employee-
  activity reports.
- `ix_transfer_status` — active-vs-cancelled filter on every
  list view.
- `ix_transfer_confirm_number` — transfers-list "look up by
  confirmation #" search.

**Don't drop these.** If you're tempted to remove one, run the
matching report at scale first (`pytest tests/test_transfer_
indexes.py` covers the EXPLAIN plans).

## What's safe to change

- Adding a new optional column to `Transfer` (with a migration,
  with a sensible default, and not in the audit list unless
  the column is operator-visible).
- Adding a new tax-exempt service type (one entry in
  `SERVICE_TYPES` + `TAX_EXEMPT_SERVICES` + the frontend
  dropdown + a test).
- Adding a new audit field (one tuple in
  `TRANSFER_AUDIT_FIELDS` — the diff helper picks it up
  automatically).
- Reports that read from `Transfer` (no schema change needed,
  just a new SELECT).

What needs a design discussion FIRST:

- Changing the `total_collected` formula.
- Changing where `federal_tax` is computed (e.g. moving it to
  a Pydantic validator, a SQLAlchemy event hook, etc.).
- Adding cross-field validation that depends on multiple
  transfers (e.g. "no more than N transfers per customer per
  day") — these tend to have edge cases nobody catches in code
  review.
- Auto-computing or auto-touching any roll-up table (mt_summary,
  ach_batch, monthly_financial) from the Transfer write path.
- Changing `sibling_store_ids` or the upsert lookup order.
- Renaming `service_type` values or dropping one (historical
  rows still reference them).

## Test surface

`tests/Modules/Transfers/` covers:

- `test_tax_service.py` — `federal_tax_for` across every
  (service_type, country, store) combination.
- `test_transfers_services.py` — `create_transfer`,
  `update_transfer`, `delete_transfer` — including the
  server-recompute of federal_tax + the audit row.
- `test_transfers_controllers.py` — every POST / GET / PUT /
  DELETE route, including the `extra="forbid"` 422 on a
  client-supplied `federal_tax`.
- `test_transfers_repository.py` — filter + pagination
  contracts.
- `test_audit_service.py` — `TRANSFER_AUDIT_FIELDS` + diff
  helper.
- `test_companies_service.py` — store-configured MT companies.
- `test_form_inputs_service.py` — `pick_employee` +
  `parse_dob`.
- `test_get_by_id_endpoint.py` / `test_receipt_endpoint.py` —
  single-row + receipt-render routes.
- `tests/Modules/Customers/test_upsert_service.py` — the
  three-step lookup chain across the owner umbrella.
- `tests/test_transfer_indexes.py` — index presence + EXPLAIN
  plans for the hot-path queries.

Before changing this module, run:

```bash
pytest tests/Modules/Transfers/ tests/Modules/Customers/test_upsert_service.py
```

If any test fails, you've broken an invariant. Either:
1. Your change is wrong — fix it.
2. The invariant has genuinely changed — update the test AND
   this document AND open a PR that's explicit about the
   contract change.
