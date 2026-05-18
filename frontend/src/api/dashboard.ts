// Dashboard summary client. Hits /api/v2/dashboard/summary,
// which returns a role-shaped payload — the route component
// branches on `role` and the TS discriminated union below
// narrows the payload accordingly.

import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";

export interface AdminDashboardKpis {
  total_transfers: number;
  today_transfers: number;
  pending_ach: number;
  today_report_entered: boolean;
  net_income_month: number | null;
}

export interface CompanyStat {
  company: string;
  count: number;
  total: number;
  fees: number;
}

export interface DashboardTransferRow {
  id: number;
  send_date: string;
  sender_name: string;
  company: string;
  send_amount: number;
  status: string;
}

export interface DashboardBatchRow {
  id: number;
  ach_date: string;
  company: string;
  ach_amount: number;
  variance: number;
  status: string;
}

export interface DashboardBankAccount {
  id: number;
  display_name: string | null;
  institution_name: string | null;
  last4: string | null;
  last_balance: number;
  last_balance_as_of: string | null;
}

export interface AdminDashboard {
  role: "admin";
  today: string;
  kpis: AdminDashboardKpis;
  company_stats: CompanyStat[];
  recent_transfers: DashboardTransferRow[];
  recent_batches: DashboardBatchRow[];
  stripe_accounts: DashboardBankAccount[];
}

export interface EmployeeTodayRow {
  id: number;
  created_at: string | null;
  sender_name: string;
  company: string;
  send_amount: number;
  fee: number;
  recipient_name: string | null;
  country: string | null;
  confirm_number: string | null;
  status: string;
}

export interface EmployeeDashboard {
  role: "employee";
  today: string;
  today_transfers: EmployeeTodayRow[];
  totals: { sent: number; fees: number; count: number };
}

// Shape of the superadmin payload is intentionally loose — the
// underlying service returns a wide assortment of fields that we
// want to surface without rebuilding pydantic models for each.
// The SPA component reads what it needs and ignores the rest.
export interface SuperadminDashboard {
  role: "superadmin";
  [key: string]: unknown;
}

export type DashboardSummary =
  | AdminDashboard
  | EmployeeDashboard
  | SuperadminDashboard;

export function useDashboardSummary() {
  // Owners have no store_id on their JWT — /api/v2/dashboard/summary
  // 400s for them. The Dashboard route component <Navigate>s them
  // away, but the hook still mounts before that branch returns, so
  // we gate the fetch here too. Belt-and-suspenders against the
  // Rules of Hooks ordering.
  const identity = getCurrentIdentity();
  const enabled = identity != null && identity.role !== "owner";
  return useQuery<DashboardSummary>({
    enabled,
    queryKey: ["dashboard", "summary"],
    queryFn: async () =>
      api<DashboardSummary>("/api/v2/dashboard/summary"),
  });
}


// ── Peak-hour heatmap ──────────────────────────────────────

export interface PeakHoursResponse {
  from_date:       string;
  to_date:         string;
  timezone:        string;
  total_transfers: number;
  max_count:       number;
  grid:            number[][];   // [Mon..Sun][0..23]
  busiest: {
    day_of_week: number | null;
    hour:        number | null;
    count:       number;
  };
}

export function usePeakHours(days = 30, enabled = true) {
  return useQuery<PeakHoursResponse>({
    queryKey: ["dashboard", "peak-hours", days],
    queryFn: () =>
      api<PeakHoursResponse>(
        `/api/v2/dashboard/peak-hours?days=${days}`,
      ),
    enabled,
  });
}
