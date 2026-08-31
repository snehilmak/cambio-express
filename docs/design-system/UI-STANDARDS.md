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
| Live state: active / on / enabled / in-progress | `accent` | `Active` |
| Completed outcome: approved / settled / delivered / cleared / credited / resolved | `success` | — |
| Inactive / off / disabled / archived — NOT red; red is for failures | `neutral` | `Inactive` |
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

## 5. Overlay & interaction behavior — headless primitives, never hand-rolled

Anything with open/close/dismiss/focus behavior is built on a
headless primitive INSIDE the kit — we style it; we never
re-implement outside-click, Escape handling, focus trapping, or
keyboard navigation ourselves (that's where a11y bugs breed):

| Behavior | Base | Kit surface |
|---|---|---|
| Modal / confirm | `@radix-ui/react-dialog` | `<Modal>` / `<ConfirmDialog>` |
| Bottom sheet (mobile row actions) | Radix Dialog | `<RowActions>` |
| Dropdown / popover menu | `@radix-ui/react-dropdown-menu` | `UserMenu` (pattern) |
| Tooltip | `@radix-ui/react-tooltip` | `<Tooltip>` / `<InfoTip>` |
| Command palette | `cmdk` | `CommandPalette` |
| Date picker | `react-day-picker` | `<DateInput>` |
| Form boolean controls | **native `<input>`** (deliberate — best form-library + a11y compat; do NOT swap for Radix Switch/Checkbox) | `<Checkbox>` / `<Switch>` |

Routes never import `@radix-ui/*` directly — they use the kit
component. Need a new overlay kind? Add the Radix-based primitive
to the kit first, styled with `--db-*` tokens and the `.ds-popover`
motion class, then use it.

## 6. Reuse before you build — MANDATORY

**Before writing any component, hook, helper or CSS block, check
whether one already exists.** This is a gate, not a suggestion:
every duplicate is a second place to fix the same bug, and we have
already paid for that twice (see below).

The check, in order:

1. **`frontend/src/components/ui/index.tsx`** — the kit's export
   list is the inventory. Read it. It is short on purpose.
2. **`grep` for the concept**, not the name you'd have chosen.
   Looking for a calendar? `grep -rn "grid-template-columns:
   repeat(7"`. A money field? `grep -rn "MoneyInput"`. The thing
   you want often exists under a name you didn't guess.
3. **Look at the nearest existing page that does the same job.**
   Building a daily sheet? The MSB daily book already is one.
   Building a list with filters? Transfers is the reference.

**Two copies is the extraction threshold.** If you are about to
write something a second time, extract it first and move the
existing caller onto it in the SAME PR. Extracting for the new
page only, and leaving the old copy alone, doubles the maintenance
instead of halving it — the point is fewer implementations, not
more abstractions.

**When you extract, take the hard-won details with you.** A
component earns its keep by carrying the fixes that are easy to
forget: containment rules, accessibility labels, edge-case
handling. Put a comment on them saying *why* they exist, so the
next person doesn't "simplify" them away.

Known shared components, and what they own:

| Use this | Instead of |
|---|---|
| `MonthCalendar` + `MonthCalendarLegend` | a month grid, cell states, money/variance containment |
| `MoneyInput` | `<input type="number">` + your own cents parsing |
| `Table`, `TableStates` | a `<table>` plus hand-rolled loading/empty/error |
| `PermissionMatrixTable` | a per-route permission grid |
| `RowActions` | inline row buttons (it handles the mobile sheet) |
| `TabsBar` / `TabsLink` / `TabsButton` | a hand-built tab strip |
| `ConfirmDialog` | `window.confirm` |
| `fmtMoney2` / `formatDate` / `formatTimestamp` | `toFixed(2)`, `.slice(0, 10)` |
| `Modal`, `Tooltip`, `Switch`, `Checkbox`, `Pill`, `KpiCard` | hand-rolled equivalents |

The same rule applies on the backend: a Service that two modules
need lives in `api/Core/` or the owning module's `Services/`, not
copy-pasted. `PLAN_CATALOG` exists because plan prices had been
duplicated into three modules and two had silently drifted.

**Cautionary tale, so this isn't abstract.** The Store Daily Book
shipped with its own month calendar — the same grid maths, the
same cell states, and a hand-copied version of the containment
rules that fix a real overflow bug. It also used raw number inputs
instead of `MoneyInput`. Consolidating took 933 lines across two
implementations down to 843 across one, and cut one page's
stylesheet from 137 lines to 12. None of that work would have been
needed if the kit had been checked first.

## 7. Layout & styling (recap — details in CLAUDE.md)

- Kit primitives first; page-specific leftovers in a co-located
  `<Route>.module.css`. No bottom-of-file `CSSProperties` constants,
  no large inline `style={{…}}` blocks.
- No hardcoded hex — `--db-*` tokens (or `tokens.*` in TSX). A color
  used twice gets a token.
- Tables: kit `<Table>`; the permission matrix uses the shared
  matrix component, not a per-route copy.
- Steppers (prev/next day/month) and other widgets used by 2+ routes
  get extracted to the kit — two copies is the threshold.

## 8. Enforcement

- PR review checklist: any `<select>` with 2 boolean-shaped options,
  any `window.confirm`, any `toFixed(2)` on money, any `.slice(0,10)`
  on a date is a change request. **So is a component that duplicates
  something in section 6's table.**
- When you fix a drift, fix ALL instances of that drift in the same
  PR — one pattern, everywhere, or the standard erodes again.
