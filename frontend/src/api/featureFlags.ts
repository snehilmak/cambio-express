import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";

// ── Feature Flags ───────────────────────────────────────────

export interface FeatureFlagRow {
  id: number;
  key: string;
  label: string;
  description: string;
  enabled_by_default: boolean;
  created_at: string;
}

interface FeatureFlagListResponse {
  rows: FeatureFlagRow[];
  total: number;
}

interface FeatureFlagResponse {
  flag: FeatureFlagRow;
}

export function useFeatureFlags() {
  return useQuery<FeatureFlagListResponse>({
    queryKey: ["feature-flags"],
    queryFn: () => api<FeatureFlagListResponse>("/api/v2/feature-flags"),
  });
}

export async function createFeatureFlag(body: {
  key: string;
  label?: string;
  description?: string;
  enabled_by_default?: boolean;
}): Promise<FeatureFlagResponse> {
  return api<FeatureFlagResponse>("/api/v2/feature-flags", {
    method: "POST",
    json: body,
  });
}

export async function toggleFeatureFlag(
  key: string,
  enabled_by_default: boolean,
): Promise<FeatureFlagResponse> {
  return api<FeatureFlagResponse>(`/api/v2/feature-flags/${key}/toggle`, {
    method: "POST",
    json: { enabled_by_default },
  });
}

export async function deleteFeatureFlag(key: string): Promise<void> {
  await api(`/api/v2/feature-flags/${key}`, { method: "DELETE" });
}

// ── Store Overrides ─────────────────────────────────────────

export interface StoreOverrideRow {
  store_id: number;
  store_slug: string;
  store_name: string;
  flag_key: string;
  enabled: boolean;
  updated_at: string;
}

interface StoreOverrideListResponse {
  rows: StoreOverrideRow[];
  total: number;
}

interface StoreOverrideResponse {
  override: StoreOverrideRow;
}

export function useStoreOverrides(flagKey: string) {
  return useQuery<StoreOverrideListResponse>({
    enabled: !!flagKey,
    queryKey: ["feature-flag-overrides", flagKey],
    queryFn: () =>
      api<StoreOverrideListResponse>(
        `/api/v2/feature-flags/${flagKey}/overrides`,
      ),
  });
}

export async function setStoreOverride(
  key: string,
  storeId: number,
  enabled: boolean,
): Promise<StoreOverrideResponse> {
  return api<StoreOverrideResponse>(
    `/api/v2/feature-flags/${key}/stores/${storeId}`,
    { method: "PUT", json: { enabled } },
  );
}

export async function clearStoreOverride(
  key: string,
  storeId: number,
): Promise<void> {
  await api(`/api/v2/feature-flags/${key}/stores/${storeId}`, {
    method: "DELETE",
  });
}

// ── Discounts ───────────────────────────────────────────────

export interface DiscountCodeRow {
  id: number;
  code: string;
  label: string;
  percent_off: number | null;
  amount_off_cents: number | null;
  value_label: string;
  duration: string;
  duration_in_months: number | null;
  max_redemptions: number | null;
  redeemed_count: number;
  expires_at: string;
  is_active: boolean;
  is_redeemable: boolean;
  stripe_coupon_id: string;
  stripe_promotion_code_id: string;
  created_at: string;
}

interface DiscountCodeListResponse {
  rows: DiscountCodeRow[];
  total: number;
}

interface DiscountCodeResponse {
  discount: DiscountCodeRow;
}

export function useDiscounts() {
  return useQuery<DiscountCodeListResponse>({
    queryKey: ["superadmin-discounts"],
    queryFn: () =>
      api<DiscountCodeListResponse>("/api/v2/superadmin/discounts"),
  });
}

export async function toggleDiscount(
  discountId: number,
  isActive: boolean,
): Promise<DiscountCodeResponse> {
  return api<DiscountCodeResponse>(
    `/api/v2/superadmin/discounts/${discountId}/toggle`,
    { method: "POST", json: { is_active: isActive } },
  );
}
