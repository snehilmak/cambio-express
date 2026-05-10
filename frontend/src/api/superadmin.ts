// Superadmin API hooks. Backed by /api/v2/superadmin/*.
//
// First slice: stores list. Controls dashboard, anomaly feed,
// audit log, announcements / discounts / feature-flag CRUD,
// and impersonation ship in subsequent PRs.

import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";

// Detail row used by the create/edit form. Superset of the list-
// view row: includes address + federal_tax_rate which the table
// doesn't show but the form binds against.
export interface SuperadminStoreDetail {
  store_id: number;
  name: string;
  slug: string;
  email: string;
  phone: string;
  address: string;
  plan: string;
  billing_cycle: string;
  is_active: boolean;
  federal_tax_rate: number;
  created_at: string;
  trial_ends_at: string;
  grace_ends_at: string;
  data_retention_until: string;
  stripe_customer_id: string;
  stripe_subscription_id: string;
}

export interface SuperadminStoreDetailResponse {
  store: SuperadminStoreDetail;
}

// POST body — mirrors the legacy form. `plan` defaults to "trial"
// server-side if omitted, but we always send it to avoid relying
// on the default.
export interface SuperadminStoreCreateBody {
  name: string;
  slug: string;
  email?: string;
  phone?: string;
  address?: string;
  plan?: string;
  admin_username?: string;
  admin_name?: string;
  admin_password: string;
}

// PATCH body — every field optional. Only keys present are applied.
export interface SuperadminStoreUpdateBody {
  name?: string;
  slug?: string;
  email?: string;
  phone?: string;
  address?: string;
  plan?: string;
  federal_tax_rate?: number;
}

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


export interface SuperadminAuditRow {
  id: number;
  admin_id: number | null;
  admin_name: string;
  action: string;
  target_type: string;
  target_id: string;
  details: string;
  created_at: string;
}

export interface SuperadminAuditListResponse {
  rows: SuperadminAuditRow[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

// Single-store detail (used by the edit-form prefill). Disabled
// when storeId is null/undefined so the create-form path skips
// the fetch entirely.
export function useSuperadminStore(storeId: number | null | undefined) {
  const identity = getCurrentIdentity();
  return useQuery<SuperadminStoreDetailResponse>({
    enabled:
      identity?.role === "superadmin" &&
      storeId !== null && storeId !== undefined &&
      Number.isFinite(storeId),
    queryKey: ["superadmin", "store", storeId, identity?.user_id],
    queryFn: () =>
      api<SuperadminStoreDetailResponse>(
        `/api/v2/superadmin/stores/${storeId}`,
      ),
  });
}

export async function createSuperadminStore(
  body: SuperadminStoreCreateBody,
): Promise<SuperadminStoreDetailResponse> {
  return api<SuperadminStoreDetailResponse>(
    "/api/v2/superadmin/stores",
    { method: "POST", json: body },
  );
}

export async function updateSuperadminStore(
  storeId: number, body: SuperadminStoreUpdateBody,
): Promise<SuperadminStoreDetailResponse> {
  return api<SuperadminStoreDetailResponse>(
    `/api/v2/superadmin/stores/${storeId}`,
    { method: "PATCH", json: body },
  );
}


export function useSuperadminAuditLog(
  page = 1, action = "", perPage = 50,
) {
  const identity = getCurrentIdentity();
  return useQuery<SuperadminAuditListResponse>({
    enabled: identity?.role === "superadmin",
    queryKey: ["superadmin", "audit-log", identity?.user_id, page, action, perPage],
    queryFn: () => {
      const p = new URLSearchParams();
      p.set("page", String(page));
      p.set("per_page", String(perPage));
      if (action) p.set("action", action);
      return api<SuperadminAuditListResponse>(
        `/api/v2/superadmin/audit-log?${p.toString()}`,
      );
    },
    placeholderData: (prev) => prev,
  });
}


// ── Report center ───────────────────────────────────────────

export interface SuperadminReportRow {
  key: string;
  label: string;
  description: string;
  url: string | null;
  status: string;  // "ready" | "coming_soon"
}

export interface SuperadminReportCategory {
  key: string;
  label: string;
  icon: string;  // inline stroke SVG
  reports: SuperadminReportRow[];
}

export interface SuperadminReportListResponse {
  categories: SuperadminReportCategory[];
}

export function useSuperadminReports() {
  const identity = getCurrentIdentity();
  return useQuery<SuperadminReportListResponse>({
    enabled: identity?.role === "superadmin",
    queryKey: ["superadmin", "reports", identity?.user_id],
    queryFn: () =>
      api<SuperadminReportListResponse>("/api/v2/superadmin/reports"),
  });
}
