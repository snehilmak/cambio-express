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
  business_type: string;
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
  business_type?: string;
  admin_username?: string;
  admin_name?: string;
  admin_password: string;
  // U-5b: "owner" makes the initial user a role=owner with this
  // store as home (+ StoreOwnerLink) — concierge onboarding.
  initial_role?: string;
}

// PATCH body — every field optional. Only keys present are applied.
export interface SuperadminStoreUpdateBody {
  name?: string;
  slug?: string;
  email?: string;
  phone?: string;
  address?: string;
  plan?: string;
  business_type?: string;
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


export interface PlanDistEntry {
  label: string;
  count: number;
}

export interface VolumeByCompany {
  company: string;
  count: number;
  total: number;
}

export interface TopReferrer {
  store_name: string;
  slug: string;
  code: string;
  redeemed: number;
  reward_total_cents: number;
}

export interface ActivityEntry {
  when: string;
  kind: "signup" | "cancel";
  store_name: string;
  detail: string;
  plan: string;
}

export interface SuperadminDashboardData {
  total_stores: number;
  active_count: number;
  trial_count: number;
  paid_count: number;
  inactive_count: number;
  estimated_mrr: number;
  new_stores_30d: number;
  new_stores_delta: number;
  churn_30d: number;
  churn_delta: number;
  basic_count: number;
  pro_count: number;
  basic_monthly: number;
  basic_yearly: number;
  pro_monthly: number;
  pro_yearly: number;
  basic_monthly_mrr: number;
  basic_yearly_mrr: number;
  pro_monthly_mrr: number;
  pro_yearly_mrr: number;
  signup_labels: string[];
  signup_direct: number[];
  signup_referral: number[];
  plan_dist: PlanDistEntry[];
  volume_by_company: VolumeByCompany[];
  total_volume_30d: number;
  total_transfers_30d: number;
  top_referrers: TopReferrer[];
  direct_signups: number;
  referral_signups: number;
  activity: ActivityEntry[];
  mrr_trend: { labels: string[]; values: number[] };
}

export function useSuperadminDashboard() {
  const identity = getCurrentIdentity();
  return useQuery<SuperadminDashboardData>({
    enabled: identity?.role === "superadmin",
    queryKey: ["superadmin", "dashboard"],
    queryFn: () =>
      api<SuperadminDashboardData>("/api/v2/superadmin/dashboard"),
  });
}


export interface SuperadminUserRow {
  id: number;
  username: string;
  full_name: string;
  email: string;
  role: string;
  store_id: number | null;
  store_name: string;
  is_active: boolean;
  has_2fa: boolean;
  last_login_at: string;
  created_at: string;
}

interface SuperadminUserListResponse {
  rows: SuperadminUserRow[];
  total: number;
  page: number;
  total_pages: number;
}

export function useSuperadminUsers(opts: {
  q?: string; role?: string; store_id?: number; page?: number;
}) {
  const identity = getCurrentIdentity();
  const params = new URLSearchParams();
  if (opts.q) params.set("q", opts.q);
  if (opts.role) params.set("role", opts.role);
  if (opts.store_id) params.set("store_id", String(opts.store_id));
  if (opts.page && opts.page > 1) params.set("page", String(opts.page));
  const qs = params.toString() ? `?${params}` : "";
  return useQuery<SuperadminUserListResponse>({
    enabled: identity?.role === "superadmin",
    queryKey: ["superadmin", "users", opts.q, opts.role, opts.store_id, opts.page],
    queryFn: () =>
      api<SuperadminUserListResponse>(`/api/v2/superadmin/users${qs}`),
  });
}

export async function createPlatformUser(body: {
  username: string;
  full_name: string;
  email: string;
  password: string;
}) {
  return api<{
    ok: boolean;
    user: {
      id: number; username: string; full_name: string;
      email: string; role: string;
    };
  }>("/api/v2/superadmin/platform-users", { method: "POST", json: body });
}

export async function changeUserRole(userId: number, role: string) {
  return api<{ ok: boolean; role: string }>(
    `/api/v2/superadmin/users/${userId}/change-role`,
    { method: "POST", json: { role } },
  );
}

export async function toggleUserActive(userId: number) {
  return api<{ ok: boolean; is_active: boolean }>(
    `/api/v2/superadmin/users/${userId}/toggle-active`,
    { method: "POST" },
  );
}

export async function resetUser2FA(userId: number) {
  return api<{ ok: boolean }>(
    `/api/v2/superadmin/users/${userId}/reset-2fa`,
    { method: "POST" },
  );
}

export async function forcePasswordReset(userId: number) {
  return api<{ ok: boolean; temp_password: string }>(
    `/api/v2/superadmin/users/${userId}/force-password-reset`,
    { method: "POST" },
  );
}

export async function revokeUserSessions(userId: number) {
  return api<{ ok: boolean; revoked_count: number }>(
    `/api/v2/superadmin/users/${userId}/revoke-sessions`,
    { method: "POST" },
  );
}

export async function impersonateUser(userId: number) {
  return api<{
    token: string;
    user: { id: number; username: string; role: string; store_id: number | null; full_name: string };
  }>(
    `/api/v2/superadmin/impersonate/${userId}`,
    { method: "POST" },
  );
}

export async function extendTrial(storeId: number, days: number = 14) {
  return api<{ ok: boolean; trial_ends_at: string }>(
    `/api/v2/superadmin/stores/${storeId}/extend-trial`,
    { method: "POST", json: { days } },
  );
}

export interface RetentionDryRunStoreRow {
  store_id: number;
  name: string;
  slug: string;
  canceled_at: string;
  data_retention_until: string;
  row_count: number;
  row_counts: Record<string, number>;
}

export interface RetentionDryRunResponse {
  now: string;
  store_count: number;
  total_child_rows: number;
  stores: RetentionDryRunStoreRow[];
}

export async function retentionDryRun() {
  return api<RetentionDryRunResponse>(
    `/api/v2/superadmin/retention-dry-run`,
    { method: "GET" },
  );
}

export async function clearStoreRetention(storeId: number) {
  return api<{ ok: boolean; already_clear?: boolean }>(
    `/api/v2/superadmin/stores/${storeId}/clear-retention`,
    { method: "POST" },
  );
}

export async function toggleStoreActive(storeId: number) {
  return api<{ ok: boolean; is_active: boolean }>(
    `/api/v2/superadmin/stores/${storeId}/toggle-active`,
    { method: "POST" },
  );
}

export interface StoreCreditResult {
  ok: boolean;
  amount_cents: number;
  stripe_txn_id: string;
}

// Issue a goodwill credit to a store's Stripe customer balance.
// `amountCents` is the POSITIVE credit size in cents (the backend
// negates it for Stripe). Surfaces 409 (no Stripe customer), 422
// (bad amount), 502/503 (Stripe error / not configured) as ApiError.
export async function creditStore(
  storeId: number, amountCents: number, reason: string,
) {
  return api<StoreCreditResult>(
    `/api/v2/superadmin/stores/${storeId}/credit`,
    { method: "POST", json: { amount_cents: amountCents, reason } },
  );
}

export interface StoreFreezeResult {
  ok: boolean;
  frozen: boolean;
  frozen_at: string;
  frozen_reason: string;
}

// Suspend a store (PR C). Its users get gated to a "suspended, contact
// support" screen. Re-subscribing does NOT lift it — only unfreezeStore.
export async function freezeStore(storeId: number, reason: string) {
  return api<StoreFreezeResult>(
    `/api/v2/superadmin/stores/${storeId}/freeze`,
    { method: "POST", json: { reason } },
  );
}

// Lift a store's suspension so its users can use the app again.
export async function unfreezeStore(storeId: number) {
  return api<StoreFreezeResult>(
    `/api/v2/superadmin/stores/${storeId}/unfreeze`,
    { method: "POST" },
  );
}

export async function emailStore(storeId: number, subject: string, message: string) {
  return api<{ ok: boolean; sent_to: string[]; total: number }>(
    `/api/v2/superadmin/stores/${storeId}/email`,
    { method: "POST", json: { subject, message } },
  );
}

export async function bulkStoreAction(
  store_ids: number[],
  action: "extend_trial" | "enable" | "disable",
  days?: number,
) {
  return api<{ ok: boolean; count: number; results: Array<Record<string, unknown>> }>(
    `/api/v2/superadmin/bulk-action`,
    { method: "POST", json: { store_ids, action, days } },
  );
}


// ── Owner links (U-5b concierge onboarding) ────────────────

export interface SuperadminOwnerLinkRow {
  owner_id:  number;
  username:  string;
  full_name: string;
  is_active: boolean;
  linked_at: string;
}

export interface SuperadminOwnerLinkListResponse {
  rows: SuperadminOwnerLinkRow[];
}

export function useStoreOwnerLinks(storeId: number | undefined) {
  return useQuery<SuperadminOwnerLinkListResponse>({
    enabled: storeId != null,
    queryKey: ["superadmin", "store", storeId, "owner-links"],
    queryFn: () =>
      api<SuperadminOwnerLinkListResponse>(
        `/api/v2/superadmin/stores/${storeId}/owner-links`,
      ),
  });
}

export async function linkOwnerToStore(
  storeId: number, ownerUsername: string,
): Promise<SuperadminOwnerLinkListResponse> {
  return api<SuperadminOwnerLinkListResponse>(
    `/api/v2/superadmin/stores/${storeId}/owner-links`,
    { method: "POST", json: { owner_username: ownerUsername } },
  );
}

export async function unlinkOwnerFromStore(
  storeId: number, ownerId: number,
): Promise<SuperadminOwnerLinkListResponse> {
  return api<SuperadminOwnerLinkListResponse>(
    `/api/v2/superadmin/stores/${storeId}/owner-links/${ownerId}`,
    { method: "DELETE" },
  );
}
