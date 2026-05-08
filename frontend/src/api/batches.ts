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

export interface BatchWriteBody {
  ach_date: string;
  company: string;
  batch_ref: string;
  ach_amount: number;
  transfer_dates?: string;
  status?: string;
  reconciled?: boolean;
  notes?: string;
}

export function useBatch(batchId: number | undefined) {
  const identity = getCurrentIdentity();
  return useQuery<{ batch: BatchRow }>({
    enabled:
      Number.isFinite(batchId) &&
      identity?.store_id != null,
    queryKey: ["batches", "detail", identity?.store_id, batchId],
    queryFn: () => api<{ batch: BatchRow }>(`/api/v2/batches/${batchId}`),
  });
}

export async function createBatch(
  body: BatchWriteBody,
): Promise<{ batch: BatchRow }> {
  return api<{ batch: BatchRow }>(
    "/api/v2/batches",
    { method: "POST", json: body },
  );
}

export async function updateBatch(
  batchId: number, body: BatchWriteBody,
): Promise<{ batch: BatchRow }> {
  return api<{ batch: BatchRow }>(
    `/api/v2/batches/${batchId}`,
    { method: "PUT", json: body },
  );
}

export interface BatchLinkedTransferRow {
  id: number;
  send_date: string;
  company: string;
  sender_name: string;
  recipient_name: string;
  country: string;
  confirm_number: string;
  send_amount: number;
  fee: number;
  federal_tax: number;
  total_collected: number;
  status: string;
}

export function useBatchTransfers(batchId: number | undefined) {
  const identity = getCurrentIdentity();
  return useQuery<{ transfers: BatchLinkedTransferRow[] }>({
    enabled:
      Number.isFinite(batchId) &&
      identity?.store_id != null,
    queryKey: ["batches", "transfers", identity?.store_id, batchId],
    queryFn: () =>
      api<{ transfers: BatchLinkedTransferRow[] }>(
        `/api/v2/batches/${batchId}/transfers`,
      ),
  });
}

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
