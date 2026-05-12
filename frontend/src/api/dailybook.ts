// Daily book hooks — backed by the existing DailyBook FastAPI
// module. Two endpoints today:
//
//   GET /api/v2/daily/{store_id}/{date}   single day's report
//   GET /api/v2/daily/{store_id}/period   range summary
//
// Both 404 when there's no report logged for the requested day.
// The hooks let TanStack Query treat 404 as a normal data state
// (data === null) so the route can render "no report yet"
// without a thrown error.

import { useQuery } from "@tanstack/react-query";

import { api, ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";

export interface DailyReportRow {
  id: number;
  store_id: number;
  report_date: string;
  taxable_sales: number;
  non_taxable: number;
  sales_tax: number;
  money_transfer: number;
  money_order: number;
  cash_expense: number;
  check_expense: number;
  cash_deposit: number;
  checks_deposit: number;
  safe_balance: number;
  over_short: number;
  locked: boolean;
  notes: string;
  total_receipts: number;
  total_disbursements: number;
  net: number;
}

export interface DailyReportResponse {
  report: DailyReportRow;
}

export interface DailyReportUpdateBody {
  taxable_sales?: number;
  non_taxable?: number;
  sales_tax?: number;
  bill_payment_charge?: number;
  phone_recargas?: number;
  boost_mobile?: number;
  money_order?: number;
  check_cashing_fees?: number;
  return_check_hold_fees?: number;
  forward_balance?: number;
  from_bank?: number;
  rebates_commissions?: number;
  cash_deposit?: number;
  safe_balance?: number;
  payroll_expense?: number;
  over_short?: number;
  notes?: string;
}

// PUT /api/v2/daily/{store_id}/{date} — saves the editable
// totals. The schema is extra=forbid server-side, so derived
// fields (money_transfer, drops, check_deposits, etc.) MUST NOT
// be in the body — they roll up from line items.
export async function updateDailyReport(
  storeId: number, date: string, body: DailyReportUpdateBody,
): Promise<DailyReportResponse> {
  return api<DailyReportResponse>(
    `/api/v2/daily/${storeId}/${date}`,
    { method: "PUT", json: body },
  );
}

// POST /api/v2/daily/{store_id}/{date}/lock — auto-creates the
// row when missing, marks it as locked. Idempotent.
export async function lockDailyReport(
  storeId: number, date: string,
): Promise<DailyReportResponse> {
  return api<DailyReportResponse>(
    `/api/v2/daily/${storeId}/${date}/lock`,
    { method: "POST", json: {} },
  );
}

// POST /api/v2/daily/{store_id}/{date}/unlock — clears the lock.
// 404 if no report exists for that date.
export async function unlockDailyReport(
  storeId: number, date: string,
): Promise<DailyReportResponse> {
  return api<DailyReportResponse>(
    `/api/v2/daily/${storeId}/${date}/unlock`,
    { method: "POST", json: {} },
  );
}

// ── Line items ──────────────────────────────────────────────

export interface LineItemRow {
  id: number;
  kind: string;
  at_time: string;  // HH:MM
  amount: number;
  note: string;
  return_check_id: number | null;
}

interface LineItemListResponse {
  items: LineItemRow[];
}

// Hook: line items for one (store, date), optionally narrowed
// to a single kind.
export function useLineItems(date: string | undefined, kind?: string) {
  const identity = getCurrentIdentity();
  const storeId = identity?.store_id;
  return useQuery<LineItemListResponse>({
    enabled:
      Boolean(date) && storeId !== null && storeId !== undefined,
    queryKey: ["dailybook", "line-items", storeId, date, kind ?? ""],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (kind) params.set("kind", kind);
      const qs = params.toString() ? `?${params}` : "";
      return api<LineItemListResponse>(
        `/api/v2/daily/${storeId}/${date}/line-items${qs}`,
      );
    },
  });
}

export interface LineItemCreateBody {
  kind: string;
  at_time: string;  // HH:MM
  amount: number;
  note?: string;
}

export async function createLineItem(
  storeId: number, date: string, body: LineItemCreateBody,
): Promise<LineItemRow> {
  return api<LineItemRow>(
    `/api/v2/daily/${storeId}/${date}/line-items`,
    { method: "POST", json: body },
  );
}

export async function deleteLineItem(
  storeId: number, itemId: number,
): Promise<void> {
  await api<void>(
    `/api/v2/daily/${storeId}/line-items/${itemId}`,
    { method: "DELETE" },
  );
}

// `date` is YYYY-MM-DD. When undefined the hook is disabled.
export function useDailyReport(date: string | undefined) {
  const identity = getCurrentIdentity();
  const storeId = identity?.store_id;

  return useQuery<DailyReportRow | null>({
    enabled:
      Boolean(date) && storeId !== null && storeId !== undefined,
    queryKey: ["dailybook", "report", storeId, date],
    queryFn: async () => {
      try {
        const resp = await api<DailyReportResponse>(
          `/api/v2/daily/${storeId}/${date}`,
        );
        return resp.report;
      } catch (err) {
        // 404 → "no report yet for this day". Surface as null
        // rather than throwing so the route can render a normal
        // empty-state placeholder.
        if (err instanceof ApiError && err.status === 404) return null;
        throw err;
      }
    },
  });
}


// Range summary used by the calendar landing page. Returns one
// DailyReportRow per day with a report on it inside the [from, to]
// window plus the totals. Days that have no report are simply
// missing from the array — the calendar renders them as empty
// cells.
export interface PeriodSummary {
  rows: DailyReportRow[];
  total_receipts: number;
  total_disbursements: number;
  net: number;
  days_logged: number;
}

export function useDailyPeriod(from: string, to: string) {
  const identity = getCurrentIdentity();
  const storeId = identity?.store_id;

  return useQuery<PeriodSummary>({
    enabled:
      Boolean(from) && Boolean(to) &&
      storeId !== null && storeId !== undefined,
    queryKey: ["dailybook", "period", storeId, from, to],
    queryFn: async () => {
      return await api<PeriodSummary>(
        `/api/v2/daily/${storeId}/period?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
      );
    },
  });
}
