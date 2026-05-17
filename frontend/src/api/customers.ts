// Customers API hooks. Backed by /api/v2/customers/search.
//
// The search endpoint scopes results to the umbrella of stores
// owned by whoever owns the current store_id — same behavior
// as the legacy /api/customers/search route. Single-store admins
// see only their store; multi-store owners see every sibling.

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";

export interface CustomerRow {
  id: number;
  full_name: string;
  dob: string;
  address: string;
  phone_country: string;
  phone_number: string;
  home_store_id: number;
  home_store_name: string;
}

export interface CustomerSearchResponse {
  matches: CustomerRow[];
  suggestions: CustomerRow[];
}

export function useCustomerSearch(q: string) {
  const identity = getCurrentIdentity();
  const storeId = identity?.store_id;

  // Match the backend's <2-char policy: skip the network call
  // entirely and return an empty envelope. Saves 1 round-trip
  // per keystroke for short queries.
  const useable = q.trim().length >= 2;

  return useQuery<CustomerSearchResponse>({
    enabled: useable && storeId !== null && storeId !== undefined,
    queryKey: ["customers", "search", storeId, q],
    queryFn: async () => {
      const params = new URLSearchParams({
        store_id: String(storeId),
        q,
      });
      return api<CustomerSearchResponse>(
        `/api/v2/customers/search?${params.toString()}`,
      );
    },
    placeholderData: keepPreviousData,
  });
}


// ── Merge ────────────────────────────────────────────────────

export interface CustomerMergeResponse {
  winner_id:           number;
  loser_id:            number;
  transfers_repointed: number;
}

/** Merge ``loser_id`` into ``winner_id``. All Transfers pointing
 *  at the loser get re-pointed at the winner, then the loser row
 *  is deleted. Server enforces umbrella scoping + admin role. */
export async function mergeCustomers(
  winnerId: number,
  loserId:  number,
): Promise<CustomerMergeResponse> {
  return api<CustomerMergeResponse>(
    `/api/v2/customers/${winnerId}/merge`,
    { method: "POST", json: { loser_id: loserId } },
  );
}
