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

// Module snapshots (P1-10): each enabled module contributes its
// dashboard section; null = module on but nothing recorded yet.
export interface DayCloseSnapshot {
  date: string;
  gross_sales: number;
  sales_tax: number;
  over_short: number | null;
  uncounted_drawers: number;
  closes: number;
  top_departments: Array<{ name: string; amount: number }>;
}

export interface LotterySnapshot {
  date: string;
  tickets_sold: number;
  value: number;
  uncounted_active_packs: number;
  active_packs: number;
}

export interface AdminDashboard {
  role: "admin";
  today: string;
  modules: string[];
  day_close: DayCloseSnapshot | null;
  lottery: LotterySnapshot | null;
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
  modules: string[];
  day_close: DayCloseSnapshot | null;
  lottery: LotterySnapshot | null;
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
  const enabled =
    identity != null && !["owner", "support"].includes(identity.role);
  return useQuery<DashboardSummary>({
    enabled,
    queryKey: ["dashboard", "summary"],
    queryFn: async () =>
      api<DashboardSummary>("/api/v2/dashboard/summary"),
  });
}
