// Owner-portal API hooks. Backed by /api/v2/owner/*.
//
// First slice: locations list. Dashboard, P&L rollup, store
// drill-down, and connect/unlink invitation flow ship in
// subsequent PRs.

import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";

export type OwnerPeriod = "today" | "month" | "year";

export interface OwnerStoreCompanyChip {
  company: string;
  count: number;
  volume: number;
}

export interface OwnerStoreRow {
  store_id: number;
  store_name: string;
  store_slug: string;
  transfer_count: number;
  volume: number;
  over_short: number;
  report_count: number;
  companies: OwnerStoreCompanyChip[];
}

export interface OwnerLocationsResponse {
  rows: OwnerStoreRow[];
  total: number;
  matched: number;
}

export function useOwnerLocations(period: OwnerPeriod = "month", q = "") {
  const identity = getCurrentIdentity();
  const enabled =
    identity?.role === "owner" || identity?.role === "superadmin";
  return useQuery<OwnerLocationsResponse>({
    enabled,
    queryKey: ["owner", "locations", identity?.user_id, period, q],
    queryFn: () => {
      const p = new URLSearchParams();
      p.set("period", period);
      if (q) p.set("q", q);
      return api<OwnerLocationsResponse>(
        `/api/v2/owner/locations?${p.toString()}`,
      );
    },
    placeholderData: (prev) => prev,
  });
}


export interface OwnerPLRollupRow {
  store_id: number;
  store_name: string;
  store_slug: string;
  has_pl: boolean;
  revenue: number;
  purchases: number;
  expenses: number;
  over_short: number;
  net: number;
}

export interface OwnerPLRollupTotals {
  revenue: number;
  purchases: number;
  expenses: number;
  over_short: number;
  net: number;
}

export interface OwnerPLRollupResponse {
  year: number;
  month: number;
  rows: OwnerPLRollupRow[];
  totals: OwnerPLRollupTotals;
  year_choices: number[];
}

export interface OwnerConnectCodeRow {
  id:                  number;
  code:                string;
  created_at:          string;
  expires_at:          string;
  used_at:             string;
  used_by_store_name:  string;
  revoked_at:          string;
  is_redeemed:         boolean;
  is_revoked:          boolean;
  is_expired:          boolean;
}

export interface OwnerConnectCodeListResponse {
  rows:  OwnerConnectCodeRow[];
  total: number;
}

export function useOwnerConnectCodes() {
  const identity = getCurrentIdentity();
  return useQuery<OwnerConnectCodeListResponse>({
    enabled: identity?.role === "owner",
    queryKey: ["owner", "connect-codes", identity?.user_id],
    queryFn: () =>
      api<OwnerConnectCodeListResponse>("/api/v2/owner/connect-codes"),
  });
}

export async function generateOwnerConnectCode(): Promise<OwnerConnectCodeRow> {
  const r = await api<{ code: OwnerConnectCodeRow }>(
    "/api/v2/owner/connect-codes",
    { method: "POST" },
  );
  return r.code;
}

export async function revokeOwnerConnectCode(
  code_id: number,
): Promise<OwnerConnectCodeRow> {
  const r = await api<{ code: OwnerConnectCodeRow }>(
    `/api/v2/owner/connect-codes/${code_id}/revoke`,
    { method: "POST" },
  );
  return r.code;
}


export function useOwnerPLRollup(year?: number, month?: number) {
  const identity = getCurrentIdentity();
  const enabled =
    identity?.role === "owner" || identity?.role === "superadmin";
  return useQuery<OwnerPLRollupResponse>({
    enabled,
    queryKey: ["owner", "pl-rollup", identity?.user_id, year, month],
    queryFn: () => {
      const p = new URLSearchParams();
      if (year)  p.set("year",  String(year));
      if (month) p.set("month", String(month));
      const qs = p.toString();
      return api<OwnerPLRollupResponse>(
        `/api/v2/owner/pl-rollup${qs ? `?${qs}` : ""}`,
      );
    },
    placeholderData: (prev) => prev,
  });
}


// ── Owner dashboard + store detail (PR for /app/owner/dashboard) ──

export interface OwnerKpis {
  agg_transfers: number;
  agg_volume: number;
  agg_over_short: number;
  agg_transfers_delta: number;
  agg_volume_delta: number;
  agg_over_short_delta: number;
}

export interface OwnerStoreCard {
  id: number;
  name: string;
  slug: string;
  count: number;
  volume: number;
  over_short: number;
}

export interface OwnerDashboardPayload extends OwnerKpis {
  period: string;
  prev_label: string;
  period_start: string;
  period_end: string;
  store_count: number;
  stores: OwnerStoreCard[];
  series_labels: string[];
  series_volume: number[];
  series_count: number[];
  company_breakdown: Array<{ company: string; count: number; volume: number }>;
  store_comparison: Array<{ id: number; name: string; volume: number; count: number }>;
  rc_period: { count: number; balance_open_cents: number; recovered_cents: number; written_off_cents: number };
  rc_aging: { age_0_30: number; age_31_60: number; age_61_90: number; age_91_plus: number };
  rc_labels: string[];
  rc_recoveries: number[];
  rc_losses: number[];
  [key: string]: unknown;
}

export function useOwnerDashboard(period: "today" | "month" | "year") {
  return useQuery<OwnerDashboardPayload>({
    queryKey: ["owner", "dashboard", period],
    queryFn: () =>
      api<OwnerDashboardPayload>(
        `/api/v2/owner/dashboard?period=${encodeURIComponent(period)}`,
      ),
  });
}

export interface OwnerStoreDetailRow {
  id: number;
  send_date: string;
  sender_name: string;
  recipient_name: string;
  company: string;
  send_amount: number;
  country: string;
  status: string;
}

export interface OwnerStoreDetailPayload {
  store: { id: number; name: string; slug: string; plan: string };
  period: string;
  prev_label: string;
  period_start: string;
  period_end: string;
  company_rows: Array<{
    company: string;
    count: number;
    volume: number;
    fees: number;
    tax: number;
  }>;
  period_count: number;
  period_volume: number;
  period_fees: number;
  period_tax: number;
  period_over_short: number;
  prev_count: number;
  prev_volume: number;
  daily_labels: string[];
  over_short_data: number[];
  receipts_data: number[];
  recent_transfers: OwnerStoreDetailRow[];
}

export function useOwnerStoreDetail(
  storeId: number, period: "today" | "month" | "year",
) {
  return useQuery<OwnerStoreDetailPayload>({
    queryKey: ["owner", "store", storeId, period],
    queryFn: () =>
      api<OwnerStoreDetailPayload>(
        `/api/v2/owner/store/${storeId}?period=${encodeURIComponent(period)}`,
      ),
    enabled: storeId > 0,
  });
}


// ── Bulk add user ───────────────────────────────────────────

export interface OwnerBulkAddUserBody {
  username:  string;
  password:  string;
  full_name: string;
  role:      "admin" | "employee";
  store_ids: number[];
}

export interface OwnerBulkAddUserResultRow {
  store_id:   number;
  store_name: string;
  status:     "created" | "skipped" | "rejected";
  detail:     string;
}

export interface OwnerBulkAddUserResponse {
  created:  number;
  skipped:  number;
  rejected: number;
  results:  OwnerBulkAddUserResultRow[];
}

export async function bulkAddUser(
  body: OwnerBulkAddUserBody,
): Promise<OwnerBulkAddUserResponse> {
  return api<OwnerBulkAddUserResponse>("/api/v2/owner/bulk-add-user", {
    method: "POST",
    json: body,
  });
}


// ── Cross-store defaults ────────────────────────────────────

export interface OwnerStoreHourEntry {
  day:    number;
  open:   string;
  close:  string;
  closed: boolean;
}

export interface OwnerCrossStoreDefaultsBody {
  store_ids: number[];
  /** Every field below is optional — the operator picks which
   *  ones to push. The server treats undefined as "don't
   *  touch this field". */
  federal_tax_rate?:          number;
  timezone?:                  string;
  store_hours?:               OwnerStoreHourEntry[];
  enforce_business_hours?:    boolean;
  timeclock_require_passkey?: boolean;
  phone?:                     string;
  address?:                   string;
}

export interface OwnerCrossStoreResultRow {
  store_id:   number;
  store_name: string;
  status:     "updated" | "rejected";
  detail:     string;
}

export interface OwnerCrossStoreResponse {
  updated:  number;
  rejected: number;
  results:  OwnerCrossStoreResultRow[];
}

export async function applyCrossStoreDefaults(
  body: OwnerCrossStoreDefaultsBody,
): Promise<OwnerCrossStoreResponse> {
  return api<OwnerCrossStoreResponse>(
    "/api/v2/owner/cross-store-defaults",
    { method: "POST", json: body },
  );
}

export async function unlinkStore(storeId: number): Promise<void> {
  await api(`/api/v2/owner/unlink/${storeId}`, {
    method: "POST",
    json: {},
  });
}

export async function redeemConnectCode(code: string): Promise<{ owner_name: string }> {
  return api<{ owner_name: string }>("/api/v2/admin/redeem-connect-code", {
    method: "POST",
    json: { code },
  });
}
