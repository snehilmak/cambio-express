// Transfers API hooks. Wraps the existing FastAPI controllers
// at /api/v2/transfers with typed return shapes + TanStack Query
// caching. Each hook is auth-gated: callers must already be
// inside a <RequireAuth> subtree, which guarantees a JWT is in
// localStorage and the api() wrapper attaches it as Bearer.

import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";

export interface TransferRow {
  id: number;
  send_date: string;
  company: string;
  service_type: string;
  sender_name: string;
  recipient_name: string;
  country: string;
  confirm_number: string;
  send_amount: number;
  fee: number;
  federal_tax: number;
  total_collected: number;
  status: string;
  batch_id: string;
  employee_name: string;
}

export interface TransferListResponse {
  rows: TransferRow[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
  page_amount: number;
}

interface RecentTransfersOptions {
  // How many rows to show on the dashboard card. Defaults to 10
  // — enough to spot the most recent activity at a glance,
  // small enough to render fast.
  limit?: number;
}

// Hook: most recent transfers for the signed-in user's store(s).
// Reads `store_id` from the JWT claims so the SPA never has to
// thread it through every component. Owners with multiple stores
// will get a follow-up PR to switch between umbrellas; for now
// the v1 dashboard scopes to the home store on the JWT.
export function useRecentTransfers({ limit = 10 }: RecentTransfersOptions = {}) {
  const identity = getCurrentIdentity();
  const storeId = identity?.store_id;

  return useQuery<TransferListResponse>({
    // Disabled when there's no store_id (e.g. superadmin viewing
    // the SPA before switching to a store). Avoids a 422 from
    // the controller — it requires `store_ids` to be non-empty.
    enabled: storeId !== null && storeId !== undefined,
    queryKey: ["transfers", "recent", storeId, limit],
    queryFn: async () => {
      const params = new URLSearchParams({
        store_ids: String(storeId),
        per_page: String(limit),
        page: "1",
        sort: "send_date",
        dir: "desc",
      });
      return api<TransferListResponse>(
        `/api/v2/transfers?${params.toString()}`,
      );
    },
  });
}

export interface TransferResponse {
  transfer: TransferRow;
}

export interface CreateTransferBody {
  send_date: string;
  company: string;
  service_type: string;
  sender_name: string;
  send_amount: number;
  fee?: number;
  commission?: number;
  recipient_name?: string;
  country?: string;
  recipient_phone?: string;
  sender_phone?: string;
  sender_phone_country?: string;
  sender_address?: string;
  sender_dob?: string;
  confirm_number?: string;
  status?: string;
  status_notes?: string;
  batch_id?: string;
  internal_notes?: string;
  employee_id?: number | null;
  customer_id?: number | null;
}

// POST /api/v2/transfers — server recomputes federal_tax from
// (send_amount, service_type, country, store), so the client
// CANNOT submit it (the schema's `extra="forbid"` rejects it).
export async function createTransfer(
  body: CreateTransferBody,
): Promise<TransferResponse> {
  return api<TransferResponse>("/api/v2/transfers", {
    method: "POST",
    json: body,
  });
}

// Hook: fetch a single transfer by id, scoped to the user's
// store(s). Server returns 404 (never 403) for cross-tenant
// lookups so tenancy boundaries stay opaque.
export function useTransfer(transferId: number | undefined) {
  const identity = getCurrentIdentity();
  const storeId = identity?.store_id;

  return useQuery<TransferResponse>({
    enabled:
      transferId !== undefined &&
      storeId !== null &&
      storeId !== undefined,
    queryKey: ["transfers", "detail", transferId, storeId],
    queryFn: async () => {
      const params = new URLSearchParams({ store_ids: String(storeId) });
      return api<TransferResponse>(
        `/api/v2/transfers/${transferId}?${params.toString()}`,
      );
    },
  });
}

export interface TransferFilters {
  q?: string;
  date_from?: string;
  date_to?: string;
  status?: string;
}

interface TransfersPageOptions extends TransferFilters {
  page: number;
  perPage: number;
}

// Hook: paginated transfer list with filters. Powers the
// /app/transfers page. Same backend endpoint as
// `useRecentTransfers` — different query key + filters so
// TanStack Query caches them independently.
export function useTransfers({
  page, perPage, q, date_from, date_to, status,
}: TransfersPageOptions) {
  const identity = getCurrentIdentity();
  const storeId = identity?.store_id;

  return useQuery<TransferListResponse>({
    enabled: storeId !== null && storeId !== undefined,
    // Include all filter values in the key so the cache
    // invalidates correctly when the user types.
    queryKey: [
      "transfers", "list", storeId, page, perPage,
      q ?? "", date_from ?? "", date_to ?? "", status ?? "",
    ],
    queryFn: async () => {
      const params = new URLSearchParams({
        store_ids: String(storeId),
        page: String(page),
        per_page: String(perPage),
        sort: "send_date",
        dir: "desc",
      });
      if (q) params.set("q", q);
      if (date_from) params.set("date_from", date_from);
      if (date_to) params.set("date_to", date_to);
      if (status) params.set("status", status);
      return api<TransferListResponse>(
        `/api/v2/transfers?${params.toString()}`,
      );
    },
    // Keep showing the previous page's data while the next
    // page is loading — avoids a flash of "Loading..." that
    // makes pagination feel laggy.
    placeholderData: (prev) => prev,
  });
}
