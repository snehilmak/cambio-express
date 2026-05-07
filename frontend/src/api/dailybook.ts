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
