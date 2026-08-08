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

// Full DailyReport payload — every model column the editor needs
// to hydrate every input, plus derived totals + lock state.
// Line-item-derived fields (cash_purchases, checks_deposit, etc.)
// are read-only in the UI; they roll up from the line-item tables.
export interface DailyReportRow {
  id: number;
  store_id: number;
  report_date: string;
  // Sales
  taxable_sales: number;
  non_taxable: number;
  sales_tax: number;
  // Receipts — operator-editable
  bill_payment_charge: number;
  phone_recargas: number;
  boost_mobile: number;
  money_transfer: number;
  money_order: number;
  money_order_fees: number;
  check_cashing_fees: number;
  return_check_hold_fees: number;
  forward_balance: number;
  /** True when forward_balance is auto-carried from the prior logged
   *  day (drops + safe) and the editor renders it read-only. False
   *  only on the store's first logged day (operator-seeded). */
  forward_balance_auto: boolean;
  from_bank: number;
  rebates_commissions: number;
  // Receipts — line-item derived (read-only)
  return_check_paid_back: number;
  other_cash_in: number;
  // Disbursements — operator-editable
  cash_deposit: number;
  safe_balance: number;
  payroll_expense: number;
  // Disbursements — line-item derived (read-only)
  cash_purchases: number;
  cash_expense: number;
  check_purchases: number;
  check_expense: number;
  outside_cash_drops: number;
  checks_deposit: number;
  other_cash_out: number;
  // Other
  over_short: number;
  locked: boolean;
  notes: string;
  /** ISO datetime when the report was locked, "" otherwise. */
  locked_at: string;
  // Derived
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
  money_order_fees?: number;
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

export interface LineItemUpdateBody {
  at_time?: string;  // HH:MM
  amount?: number;
  note?: string;
}

/** PATCH one line item.  All fields optional — only the ones the
 *  caller includes get written.  Returns the canonical row from
 *  the server so the React-Query cache can refresh in place.
 *  The DailyReport's roll-up total recomputes server-side on a
 *  successful patch — invalidate the report query to pick it up.
 *
 *  Backend contract:
 *  - `extra="forbid"` on the request schema (so `kind` / store_id
 *    / report_date can't be patched — they're identity, not data).
 *  - 403 when the parent daily report is locked.
 *  - 409 when the row is linked to a ReturnCheck.
 *  - 422 on `amount <= 0` or unknown extra field.
 */
export async function updateLineItem(
  storeId: number, itemId: number, body: LineItemUpdateBody,
): Promise<LineItemRow> {
  return api<LineItemRow>(
    `/api/v2/daily/${storeId}/line-items/${itemId}`,
    { method: "PATCH", json: body },
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

// ── Money-transfer auto-fill ─────────────────────────────────

export interface TransferCompanyTotals {
  company: string;
  count: number;
  amount: number;
  fees: number;
  federal_tax: number;
  commission: number;
  total: number;
}

export interface TransfersSummary {
  companies: string[];
  by_company: TransferCompanyTotals[];
  grand_total: number;
}

// Hook: per-day MT roll-up from the employee transfer log.
// Read-only — the daily book's `money_transfer` field is the
// operator's writable counterpart; this hook just shows what
// the transfer table already has so the cashier doesn't have
// to re-key it.
export function useTransfersSummary(date: string | undefined) {
  const identity = getCurrentIdentity();
  const storeId = identity?.store_id;
  return useQuery<TransfersSummary>({
    enabled:
      Boolean(date) && storeId !== null && storeId !== undefined,
    queryKey: ["dailybook", "transfers-summary", storeId, date],
    queryFn: async () => {
      return await api<TransfersSummary>(
        `/api/v2/daily/${storeId}/${date}/transfers-summary`,
      );
    },
  });
}


// ── Editable per-company MT breakdown ────────────────────────

export interface MTBreakdownRow {
  company: string;
  saved_amount: number;
  saved_fees: number;
  saved_federal_tax: number;
  saved_commission: number;
  saved_total: number;
  auto_amount: number;
  auto_fees: number;
  auto_federal_tax: number;
  auto_commission: number;
  auto_count: number;
  auto_total: number;
}

export interface MTBreakdown {
  rows: MTBreakdownRow[];
  saved_total: number;
  auto_total: number;
}

export interface MTBreakdownWriteRow {
  company: string;
  amount: number;
  fees: number;
  federal_tax: number;
  commission: number;
}

// Hook: per-company saved + auto values for the editor's Money
// Transfers tab. Each row carries BOTH saved (operator's last
// entry) and auto (transfer-log aggregate) so the form can pre-
// fill from saved-when-present, auto-otherwise.
export function useMTBreakdown(date: string | undefined) {
  const identity = getCurrentIdentity();
  const storeId = identity?.store_id;
  return useQuery<MTBreakdown>({
    enabled:
      Boolean(date) && storeId !== null && storeId !== undefined,
    queryKey: ["dailybook", "mt-breakdown", storeId, date],
    queryFn: async () => {
      return await api<MTBreakdown>(
        `/api/v2/daily/${storeId}/${date}/mt-breakdown`,
      );
    },
  });
}

// PUT /api/v2/daily/{store}/{date}/mt-breakdown — bulk-replace
// every saved row + sync the grand total into the daily report's
// `money_transfer` field in one transaction.
export async function replaceMTBreakdown(
  storeId: number, date: string, rows: MTBreakdownWriteRow[],
): Promise<MTBreakdown> {
  return api<MTBreakdown>(
    `/api/v2/daily/${storeId}/${date}/mt-breakdown`,
    { method: "PUT", json: { rows } },
  );
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
