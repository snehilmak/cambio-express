// Account-side API helpers (password change, store info,
// future profile / preferences, etc.).

import { useQuery } from "@tanstack/react-query";

import { api } from "./../lib/api";
import { getCurrentIdentity } from "./../lib/auth";

export interface ChangePasswordBody {
  current_password: string;
  new_password: string;
  confirm_password: string;
}

export async function changePassword(
  body: ChangePasswordBody,
): Promise<{ status: string }> {
  return api<{ status: string }>(
    "/api/v2/auth/change-password",
    { method: "POST", json: body },
  );
}

export interface StoreInfoRow {
  id: number;
  name: string;
  slug: string;
  email: string;
  phone: string;
  address: string;
  plan: string;
  federal_tax_rate: number;
  is_active: boolean;
}

export interface StoreInfoUpdateBody {
  name?: string;
  email?: string;
  phone?: string;
  address?: string;
  federal_tax_rate?: number;
}

export function useStoreInfo() {
  const identity = getCurrentIdentity();
  return useQuery<{ store: StoreInfoRow }>({
    enabled: identity?.store_id != null,
    queryKey: ["admin", "store-info", identity?.store_id],
    queryFn: () =>
      api<{ store: StoreInfoRow }>("/api/v2/admin/store-info"),
  });
}

export async function updateStoreInfo(
  body: StoreInfoUpdateBody,
): Promise<{ store: StoreInfoRow }> {
  return api<{ store: StoreInfoRow }>(
    "/api/v2/admin/store-info",
    { method: "PUT", json: body },
  );
}
