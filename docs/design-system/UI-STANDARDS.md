# UI control & pattern standards — ONE way to do each thing

**Binding for all future development.** For every kind of data and
every kind of feedback there is exactly ONE control / pattern. If a
screen needs something this file doesn't cover, add the rule here in
the same PR that introduces it — never invent a second way to render
something that already has a row below.

The kit (`frontend/src/components/ui/index.tsx`) is the only place
controls come from. If the kit lacks a primitive you need, add it to
the kit first, then use it — never hand-roll one in a route.

---

## 1. Controls by data type

| Data | Control | Never |
|---|---|---|
| Boolean **setting** (feature/preference that applies immediately or on save: `enabled`, `enforce_business_hours`, `require_passkey`, theme, auto_post) | `<Switch>` | On/Off or Yes/No `<Select>`; radio pairs |
| Boolean **attribute of a record in a form** (`taxable`, `is_ebt`, `reconciled`, `is_active` on an edit form, "update costs") | `<Checkbox>` | Yes/No `<Select>`; radio pairs |
| Boolean **selection** ("include this row", store pickers, matrix cells) | `<Checkbox>` (with `aria-label` when the row provides the visible label) | raw `<input type="checkbox">` |
| Boolean toggled **from a table row** | `<RowActions>` item ("Deactivate"/"Reactivate", "Disable"/"Enable") | a Switch inside a table cell |
| Enum (3+ meaningful values) | `<Select>` | radios for >2 options unless all options must be visible at once |
| Two-to-four **modes that change what's below** (not a boolean) | radio group or `<TabsButton>` segmented control | — |
| Free text | `<Field>` + `<Input>` / `<Textarea>` | raw inputs |
| Money | `<MoneyInput>` | raw number inputs |
| Date | `<DateInput>` | raw `type="date"` |
| Phone | `<PhoneField>` | — |

Radio-for-a-boolean is banned: a two-option radio group whose value is
a single `true/false` is a `<Checkbox>` (form) or `<Switch>` (setting).

## 2. Feedback

| Event | Pattern |
|---|---|
| Save/mutation succeeded, staying on page | `useToast()` `tone: "success"` |
| Save succeeded, navigating away | toast FIRST, then navigate (see `SuperadminStoreForm`) |
| Fetch failed (page/table data) | `<ErrorState message onRetry>` — always with retry; never `EmptyState` |
| Mutation/form failed | `<Alert tone="error">` (root) + `<Field error>` (per-field) |
| Data loading | list/table routes: `<TableStates>` (skeleton→error→empty); everything else: `<Loading />`. Never bare "Loading…" text, never an info Alert |
| Zero rows (whole region: table, tab pane, page section) | `<EmptyState title body>` — never an ad-hoc muted `<p>` |
| Zero rows (small in-card sub-list) or permission/scope gate | `<Empty>` |
| Destructive action | `<ConfirmDialog>` — never `window.confirm` / `alert()` |

## 3. Status display

Pill tones carry ONE meaning each — the same status kind gets the
same tone on every screen:

| Semantic | Tone | Cell text |
|---|---|---|
| Active / on / enabled / approved / completed / credited | `accent` | `Active` |
| Inactive / off / disabled / archived | `neutral` | `Inactive` |
| Pending / expiring / needs attention | `warning` | — |
| Failed / rejected / cancelled / destructive | `negative` | — |
| Informational / secondary identity (owner role, info) | `info` | — |

- Boolean table cells: `Active` / `Inactive` (lifecycle) — never
  `Yes`/`No`, `Disabled`, `✓`, or `—` — except dense matrices, where
  `✓` / `—` is the standard pair.
- Role pills: `admin → accent`, `employee → neutral`, `owner → info`.
- Tone maps shared by 2+ routes live in the API layer next to the
  type (see `TICKET_STATUS_TONES` in `api/support.ts`), not copied
  per route.

## 4. Formatting

| Value | Formatter (`lib/formatters.ts`, `lib/datetime.ts`) | Never |
|---|---|---|
| Money | `fmtMoney2` (or `fmtMoney` for whole-dollar KPIs) | `` `$${x.toFixed(2)}` `` (drops thousands separators), private clones, inline `toLocaleString` |
| Timestamp | `formatTimestamp` (timezone-aware) | `toLocaleString()` inline |
| Date | `formatDate`; `fmtDateCompact` in dense tables | `.slice(0, 10)` (wrong calendar date for US stores on UTC timestamps) |
| Counts | `fmtNumber` | — |

## 5. Layout & styling (recap — details in CLAUDE.md)

- Kit primitives first; page-specific leftovers in a co-located
  `<Route>.module.css`. No bottom-of-file `CSSProperties` constants,
  no large inline `style={{…}}` blocks.
- No hardcoded hex — `--db-*` tokens (or `tokens.*` in TSX). A color
  used twice gets a token.
- Tables: kit `<Table>`; the permission matrix uses the shared
  matrix component, not a per-route copy.
- Steppers (prev/next day/month) and other widgets used by 2+ routes
  get extracted to the kit — two copies is the threshold.

## 6. Enforcement

- PR review checklist: any `<select>` with 2 boolean-shaped options,
  any `window.confirm`, any `toFixed(2)` on money, any `.slice(0,10)`
  on a date is a change request.
- When you fix a drift, fix ALL instances of that drift in the same
  PR — one pattern, everywhere, or the standard erodes again.
