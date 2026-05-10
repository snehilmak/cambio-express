// Shared API client for the report-drilldown migration. The
// /api/v2/reports/<slug> endpoints all return a `{rows, totals}`
// envelope where rows share an `AggregatedRowBase` shape (count
// / sent / fees / tax / avg) plus one identity field per slug.

import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";

export interface AggregatedTotals {
  // Most reports use these four keys. New batches (e.g. new-vs-returning,
  // fees-vs-tax) ship totals with custom keys — the SPA narrows the
  // type at the call site for those.
  count?: number;
  sent?: number;
  fees?: number;
  tax?: number;
  // Bag of arbitrary extras (e.g. `ratio`, `customers`, `new_count`,
  // `amount`, `threshold`). Each report's TSX wrapper reads what it
  // needs through `as` casts.
  [key: string]: number | string | undefined;
}

export interface AggregatedRow {
  count: number;
  sent: number;
  fees: number;
  tax: number;
  avg: number;
  // Discriminator field varies by slug — e.g. `company`, `service_type`,
  // `employee_name`. The SPA component extracts it via a config key.
  [identity: string]: number | string | null | undefined;
}

export interface ReportDrilldownResponse {
  rows: AggregatedRow[];
  totals: AggregatedTotals;
}

interface UseReportDrilldownOpts {
  // API path slug — most match the Flask slug, but a few diverge
  // (e.g. Flask `sales-by-service-type` → API `sales-by-service`).
  apiSlug: string;
  // YYYY-MM-DD strings for the period filter.
  from: string;
  to: string;
  // Comma-separated list of store IDs from JWT or owner scope.
  storeIds: number[];
  // Extra query string fragments (e.g. `sort_by=count`). Passed
  // through verbatim — caller does its own URL encoding.
  extraParams?: Record<string, string>;
}

export function useReportDrilldown(opts: UseReportDrilldownOpts) {
  const params = new URLSearchParams();
  if (opts.from) params.set("from", opts.from);
  if (opts.to) params.set("to", opts.to);
  if (opts.storeIds.length > 0) {
    params.set("store_ids", opts.storeIds.join(","));
  }
  for (const [k, v] of Object.entries(opts.extraParams ?? {})) {
    params.set(k, v);
  }
  const enabled = opts.storeIds.length > 0;
  return useQuery<ReportDrilldownResponse>({
    enabled,
    queryKey: [
      "report", opts.apiSlug, opts.from, opts.to,
      opts.storeIds.join(","),
      JSON.stringify(opts.extraParams ?? {}),
    ],
    queryFn: () =>
      api<ReportDrilldownResponse>(
        `/api/v2/reports/${opts.apiSlug}?${params.toString()}`,
      ),
  });
}

export function defaultStoreIds(): number[] {
  // Drilldowns scope to the caller's own store (or umbrella for
  // owners). Single-store path: read store_id off the JWT.
  // Owner umbrella + multi-store rollup ship in a follow-up — for
  // now, owner sessions fall back to their currently-pinned store
  // (or an empty list, which leaves the query disabled).
  const identity = getCurrentIdentity();
  if (identity?.store_id != null) return [identity.store_id];
  return [];
}
