# DineroBook — SPA Component Catalog

> Last updated: 2026-05-12
> Source of truth: [`frontend/src/components/ui/index.tsx`](../../frontend/src/components/ui/index.tsx)

The SPA's design system lives in a single file —
`frontend/src/components/ui/index.tsx` — plus the motion stylesheet
[`ui.css`](../../frontend/src/components/ui/ui.css). This doc is a
flat reference so contributors can find the right primitive
without re-reading 700 lines of TypeScript.

**When you add a new component to `ui/index.tsx`, add a row here
in the same PR.** An out-of-date catalog is worse than no catalog.

## Conventions used by every primitive

- **Tokens, not hex.** Every color / radius / spacing comes from
  CSS variables declared in `static/design-tokens.css`. Hard-coded
  hex blocks a PR review (see CLAUDE.md "Design system"
  invariant).
- **Dark-only.** `data-theme="dark"` is unconditional; no light
  mode. Components don't render a theme toggle.
- **One accent color.** Neon green `#3fff00` for primary CTAs +
  positive money + active nav. Jewel tones for secondary
  emphasis (`--db-co-intermex/maxi/barri`) and the four state
  colors (`--db-info/warning/negative` + neon).
- **Three fonts.** Space Grotesk (display), Inter (body),
  JetBrains Mono (money, dates, IDs).
- **Motion baked in.** Hover lift, scale-press, focus glow, page
  fade-up are wired into the primitives via the `.ds-*` classes
  in `ui.css`. `prefers-reduced-motion: reduce` strips animations
  via the global rule in `frontend/src/styles.css`.

## Layout primitives

### `<PageShell maxWidth={…} gap={…}>`

Top-level wrapper for every authenticated route. Sets
`max-width`, flex column, the page-fade-up animation, and the
1.5rem padding scale.

```tsx
<PageShell maxWidth="75rem" gap="1.25rem">
  <PageHeader title="…" actions={…} />
  <Section>…</Section>
</PageShell>
```

| Prop | Default | Notes |
|---|---|---|
| `maxWidth` | `"68rem"` | Override for wide tables (82rem) or narrow forms (50rem) |
| `gap` | `space.xl` (1.5rem) | Vertical gap between top-level children |

Wraps content in `<main className="ds-page">` — the
`.ds-page` keyframe gives the fade-up entry. Honors
reduced-motion automatically.

### `<PageHeader title actions?>`

Page-title row with optional actions slot. Use as the FIRST child
of `PageShell`. The actions slot is intended for buttons / link
groups; lays out flex with `space-between`.

### `<Section title? children>`

Sub-section inside a page. Optional inline `<SectionTitle>`
header. Used for grouping related cards.

### `<SectionTitle>{children}</SectionTitle>`

The section-title typography. Don't roll your own `<h2>` — use
this so the type ramp stays consistent.

### `<Card padding? interactive? children>`

Default content surface. Wraps in `.ds-card` for hover lift +
border-color animation. `interactive` adds the `.ds-card--interactive`
class for a stronger hover state (use on rows the user can click).

### `<KpiGrid minWidth={…}>` + `<KpiCard label value sub? tone?>`

KPI strip pattern. `KpiGrid` is the responsive grid container
(auto-fill, min-width controllable per row); `KpiCard` is the
individual stat tile with tabular-nums for the value glyph.

```tsx
<KpiGrid minWidth="180px">
  <KpiCard label="Revenue" value="$12,345" sub="MoM +3%" tone="positive" />
  <KpiCard label="Churn"   value="2.1%"    tone="warning" />
</KpiGrid>
```

`tone` is one of `"default"`, `"positive"`, `"negative"`,
`"info"`, `"warning"`. Tones drive the value color, not the
border.

## Forms

### `<Field label children error?>`

The standard label + control wrapper. Use around any input so
labels stay consistent. Renders the error message in red below
the control when `error` is non-empty.

```tsx
<Field label="Store name" error={errors.store_name}>
  <Input
    value={name}
    onChange={(e) => setName(e.target.value)}
  />
</Field>
```

### `<Input>` / `<Select>` / `<Textarea>`

Forward-ref wrappers that attach the `.ds-input` class (focus
glow + border-color transition). Otherwise pass-through to the
native element — every standard HTML prop works.

## Tables

### `<Table headers={…}>{rows}</Table>`

Striped data table with the design-system padding + the
`.ds-card` border styling on the outer wrapper. Headers can be
strings (right-align numeric, left-align text) or objects with
explicit alignment.

Inside the body, use the exported `thStyle` / `tdStyle` /
`tokens` helpers if you need to attach inline styles to specific
cells — they pull from the token registry rather than
hand-rolling.

### `<TableSkeleton rows={n} cols={m}>`

Shimmer-animated placeholder for a loading table. Use inside the
`isLoading` branch so the layout doesn't jump when data arrives.

## States

### `<EmptyState title description? action?>`

Use when a query succeeded but returned no rows. Pattern:

```tsx
{data && data.length === 0 && (
  <EmptyState
    title="No transfers in this period."
    description="Pick a different range above."
  />
)}
```

The `action` slot is rendered below the description — typically a
"New X" button.

### `<ErrorState message onRetry?>`

Use when a query failed. Renders the error message + a retry
button (when `onRetry` is given). The route-level error boundary
(`RouteErrorBoundary` in `App.tsx`, Sentry-aware) is what catches
unhandled render exceptions; this primitive is for handled-fetch
failures.

### `<Loading label="Loading…" />`

The spinner-only placeholder. For tables prefer `<TableSkeleton>`
so the page layout doesn't jump.

## Pagination

### `<Pager page totalPages onPage onPageSize? pageSize?>`

Compact prev/next + page-number-pill control. Handles the URL
sync — pass `onPage(n)` to update your route's local state and
the URL `?page=n` query string.

## Pills

### `<Pill tone children>` — `tone: PillTone`

Status badge. Tones (`PillTone`):

| Tone | Color | Use for |
|---|---|---|
| `neutral` | gray border, gray text | Default state |
| `info` | blue border, blue text | Informational |
| `positive` | green border, green text | Success / paid / live |
| `warning` | amber border, amber text | Expiring / inactive trial |
| `negative` | red border, red text | Failed / declined / fraud |

Don't render a free-form `<span>` with inline colors when a pill
fits the data — the pill keeps the entire app's status vocabulary
consistent.

## Buttons + links

### `<Button tone size? children>` — `tone: ButtonTone`

Primary action element. Tones:

| Tone | Visual |
|---|---|
| `primary` | Neon green background, dark text — only ONE per view (the canonical CTA) |
| `secondary` | Outlined, default text |
| `danger` | Red outline, red text on hover |
| `ghost` | No border, hover-only emphasis |

Size: `"sm"` or default. Both attach the `.ds-btn` class so
hover-lift + scale-press are uniform.

### `<ButtonLink tone size? href download? children>`

Same visual contract as `<Button>` but renders an `<a>` so the
browser handles `href` / `download`. Use for `Export CSV`-type
actions where the destination URL builds the file response.

## Other shared exports

| Symbol | Use |
|---|---|
| `tokens` | Inline-style helper. `tokens.text`, `tokens.surface`, `tokens.border`, `tokens.fontMono`, etc. Use instead of hard-coding hex / font strings. |
| `space` | Padding scale (`xs=4`, `sm=8`, `md=12`, `lg=16`, `xl=24`, `2xl=32`). |
| `thStyle` / `tdStyle` | Table header / cell base styles. Spread into your `style` prop when you can't use `<Table>`. |
| `Empty` | Lower-level than `<EmptyState>` — just the icon + line. Prefer `EmptyState` for full layouts. |

## Motion classes (CSS-only)

Some interactions don't need a React wrapper. Attach these via
`className` on the relevant element:

| Class | What it does |
|---|---|
| `.ds-page` | Fade-up on mount (200ms). Already on `PageShell`. |
| `.ds-card` | Border-color + transform transition. Already on `Card`. |
| `.ds-card--interactive` | Adds hover-lift + active-press. Attach to `.ds-card` rows you want clickable. |
| `.ds-btn` + `.ds-btn--{primary,secondary,danger,ghost}` | Already on `Button`. |
| `.ds-input` | Focus glow. Already on `Input`/`Select`/`Textarea`. |
| `.ds-link` | Underline-reveal on hover. Use on `<a>` elements outside button contexts. |
| `.ds-popover` | Fade-scale-in on mount (200ms). Use on dropdowns / popovers (e.g. `SenderAutocomplete`). |
| `.ds-skel` | Shimmer animation. Used inside `TableSkeleton`. |
| `.ds-pill--pulse` | Subtle opacity pulse. Attach to `<Pill>` when state is "live updating" (rare). |

## Where to use NEW ad-hoc styling

Almost never. The primitives above cover ~95% of the SPA. If you
need something that isn't here, do this:

1. **Is there a token you can reuse?** Look in `tokens.ts` and
   `static/design-tokens.css`. 80% of "new" needs are an existing
   token applied differently.
2. **Could it be a new primitive here?** If three routes would
   use it, extract it into `ui/index.tsx` and add a row to this
   doc.
3. **Is the surface temporary?** If a one-shot inline style
   prevents a 100-line refactor, ship it — but leave a TODO
   pointing at the primitive that should subsume it.

## Doc maintenance contract

Update this doc when you:

* Add or rename an export in `frontend/src/components/ui/index.tsx`.
* Add a new `.ds-*` class to `ui.css`.
* Change the `tokens.ts` registry shape.
* Retire a primitive (mark it deprecated here for one release,
  then remove the row when the last call site is gone).
