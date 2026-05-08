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
