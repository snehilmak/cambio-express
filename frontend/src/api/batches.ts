// Batches API hooks. Backed by /api/v2/batches.
//
// One read-side endpoint today: list-all-for-store with sort
// + precomputed transfers_total + variance + transfer_count.
// Write-side (create / edit / link transfers) stays on the
// legacy Flask path.

import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";

export interface BatchRow {
  id: number;
  ach_date: string;
  company: string;
  batch_ref: string;
  ach_amount: number;
  status: string;
  reconciled: boolean;
  transfer_dates: string;
  notes: string;
  transfers_total: number;
  variance: number;
  transfer_count: number;
}

export interface BatchListResponse {
  rows: BatchRow[];
}

export type BatchSort =
  | "ach_date" | "company" | "batch_ref" | "ach_amount" | "status" | "";
export type BatchDir = "asc" | "desc";

export function useBatches(sort: BatchSort = "", direction: BatchDir = "desc") {
  const identity = getCurrentIdentity();
  const enabled = identity?.store_id != null;
  return useQuery<BatchListResponse>({
    enabled,
    queryKey: ["batches", "list", identity?.store_id, sort, direction],
    queryFn: () => {
      const params = new URLSearchParams();
      if (sort) params.set("sort", sort);
      params.set("direction", direction);
      return api<BatchListResponse>(
        `/api/v2/batches?${params.toString()}`,
      );
    },
  });
}
