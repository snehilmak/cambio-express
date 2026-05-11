# ADR-001 — SPA migration recap

> **Status:** ACCEPTED — executed (PRs #395–#419, May 2026).
> **Last updated:** 2026-05-11
> **Authors:** Snehil Mak, Claude.
> **Supersedes:** none.
> **Tracked by:** BACKLOG.md "Post-SPA-migration cleanup" section.

## Context

[`MIGRATION_ADR.md`](MIGRATION_ADR.md) (May 2026) committed us to a
modular FastAPI backend + a separate React frontend, with a
strangler-fig migration from the Flask + Jinja monolith. The backend
half of that ADR was carried out across PRs #200–#394 between Feb and
May 2026: read-side FastAPI routers under `/api/v2/{auth, customers,
transfers, bank, reports, daily}` were standing by, but the customer-
facing chrome was still Jinja templates rendered by Flask.

This ADR records **what we actually shipped on the frontend side** —
the May 2026 SPA migration (PRs #395–#419) that finished the
migration from the user's perspective and is now the basis for all
follow-up cleanup work. The on-paper plan in MIGRATION_ADR.md was
"frontend stack: React" with no further specification; this ADR is
the concrete realization.

## Decision

The whole authenticated product chrome moved to a single React SPA
that talks exclusively to the FastAPI `/api/v2/*` surface. Concretely:

- **One SPA bundle** under `frontend/` — Vite + React 19 + React
  Router 7 + TanStack Query. Mounted at `/app/*` (admin/employee) and
  `/owner/*` (owner umbrella) on the same Flask process.
- **Flask is now a static-asset host + redirect plane** for the
  authenticated paths. Every legacy `/dashboard`, `/transfers`,
  `/reports/*`, `/owner/*` route returns a 301 to the SPA equivalent.
- **Public-facing pages stay on Flask + Jinja** for now: the landing
  page (`/`), login / signup / forgot-password, the offline page,
  privacy policy, and `/tv/<token>` (the kiosk display that public
  shop customers point a tablet at). The TV display deliberately
  stays on Jinja because it's a read-mostly public endpoint that
  doesn't need React's interactivity layer.
- **All 35 superadmin BI report drilldowns** were rebuilt as React
  routes against `/api/v2/superadmin/bi/<slug>` endpoints. The
  generic `ReportDrilldown` and `SuperadminBIDrilldown` components
  handle every drilldown via a `columns` + `kpis` spec, so adding a
  new report is a config-only change.
- **chart.js + react-chartjs-2** is the visualization layer. Auto-
  detection picks Line vs. Bar based on row shape (date-like key →
  Line; categorical → Bar).
- **Dual-auth window** during migration: cookie sessions (legacy
  Flask) and JWT in localStorage (SPA) both work. Both are accepted
  by `/api/v2/*`. ADR-002 retires the cookie path.

## Consequences

What this unlocks:

- **No more page reloads** on any in-app workflow. Tabs, drilldowns,
  filter changes, form submits are all client-side.
- **One client contract** to maintain — every page hits
  `/api/v2/*` via the typed `api()` wrapper in `frontend/src/lib/`.
  No more "this template reads a Flask-flashed message, that one
  reads a TanStack query."
- **OpenAPI-driven type safety** is on the table (BACKLOG E7) now
  that the SPA is the only client.
- **Smoke tests** moved up the stack: Playwright covers the SPA
  golden path; Flask-side Jinja tests were retired.

What this makes harder, and how we're handling it:

- **Bundle size.** ~900 KB raw (240 KB gzipped) after chart.js. Code-
  splitting per-route is BACKLOG C1.
- **CSS coherence.** The Jinja templates shared a tightly scoped CSS
  bundle (`design-tokens.css` + `content.css` + `shell.css`). The
  SPA started with each route inlining its own style objects, which
  drifted fast. BACKLOG A1–A6 fixes this; the `frontend/src/
  components/ui/` design-system module landed in PR #422 as the
  starting point.
- **Two auth transports during the transition.** Cookie session
  carries through Flask; JWT lives in localStorage for the SPA.
  ADR-002 closes this out.

What we accepted:

- **No isomorphic rendering / SSR.** The SPA renders client-side; the
  initial HTML is a 1.5 KB shell. For a logged-in B2B SaaS where
  SEO doesn't matter and the user is past auth before any "page" is
  shown, this is the right tradeoff. (Public pages still render
  server-side on Flask, so they're SEO-friendly.)
- **localStorage JWT instead of HttpOnly cookie JWT (for now).**
  MIGRATION_ADR.md §6 prescribed HttpOnly cookies; we shipped
  localStorage to keep the migration moving. ADR-002 makes the
  cookie move.

## Alternatives

| Option | Why we didn't pick it |
|---|---|
| Keep Jinja, add HTMX for interactivity | Doesn't deliver the OpenAPI-typed client story MIGRATION_ADR.md committed to. Doesn't unblock a future mobile / desktop client either. |
| Next.js / SSR React | The SaaS doesn't need SEO inside the authenticated product. SSR adds a Node runtime and a build complication for no user-visible win. |
| Lit / Web Components | Smaller team familiarity. React's hiring pool was a stated reason in MIGRATION_ADR.md §5 Q1. |
| Defer SPA migration, finish backend first | The Flask + Jinja chrome was the bottleneck on UX velocity. Backend was already 80% done; finishing the user-facing half was the higher-leverage move. |

## Implementation

What shipped, in rough order:

| Phase | PRs | Scope |
|---|---|---|
| SPA scaffold | #395 | Vite + React + React Router + TanStack Query under `frontend/`. SPA serves at `/app/*` via Flask catch-all. |
| Dashboards | #396–#400 | Admin / employee / owner dashboards. chart.js wired for owner. |
| Transfers + Customers | #401–#406 | List + create + edit + autocomplete. The big write surface. |
| Daily / Monthly / Batches / Return Checks | #407–#412 | Bookkeeping core. |
| Reports — admin + owner | #413–#416 | All non-superadmin drilldowns through the generic `ReportDrilldown` component. |
| Reports — superadmin BI | #417–#419 | All 35 BI drilldowns through `SuperadminBIDrilldown` + the BI router on the backend. |

What's still left, tracked in BACKLOG:

- **Visual polish** — A1 (motion), A2 (spacing), A3 (typography),
  A4–A6 (empty / loading / error states). PR #422 laid the design-
  system foundation; per-route adoption is in flight.
- **Charts on superadmin BI** — B1–B4. Time-series + bar
  auto-detection landed in PR #423.
- **Code splitting** — C1.
- **Auth simplification** — D3 / ADR-002.
- **Bundle observability** — Sentry on the React side (E1), build
  gate in CI (E3 / E6, PR #426).

## Changelog

- **2026-05-11** — Initial draft, ACCEPTED retroactively (the work
  is already shipped).
