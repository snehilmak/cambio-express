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
