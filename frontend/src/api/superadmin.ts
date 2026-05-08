// Superadmin API hooks. Backed by /api/v2/superadmin/*.
//
// First slice: stores list. Controls dashboard, anomaly feed,
// audit log, announcements / discounts / feature-flag CRUD,
// and impersonation ship in subsequent PRs.

import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";

export interface SuperadminStoreRow {
  store_id: number;
  name: string;
  slug: string;
  email: string;
  phone: string;
  plan: string;
  billing_cycle: string;
  is_active: boolean;
  created_at: string;
  trial_ends_at: string;
  grace_ends_at: string;
  data_retention_until: string;
  stripe_customer_id: string;
  stripe_subscription_id: string;
}

export interface SuperadminStoreListResponse {
  rows: SuperadminStoreRow[];
  total: number;
}

export function useSuperadminStores() {
  const identity = getCurrentIdentity();
  return useQuery<SuperadminStoreListResponse>({
    enabled: identity?.role === "superadmin",
    queryKey: ["superadmin", "stores", identity?.user_id],
    queryFn: () =>
      api<SuperadminStoreListResponse>("/api/v2/superadmin/stores"),
  });
}
