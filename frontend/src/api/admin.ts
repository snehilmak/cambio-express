import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";

// Per-store admin endpoints — distinct from `account.ts` (store-info,
// team, passkeys) and `superadmin.ts` (platform-wide). New admin
// Controllers belong here too.

export interface AdminAuditRow {
  ts:           string;
  user_name:    string;
  user_role:    string;
  action:       string;
  target_type:  string;
  target_id:    string;
  target_label: string;
  summary:      string;
  source:       string;
}

export interface AdminAuditUserOption {
  id:    number;
  label: string;
  role:  string;
}

export interface AdminAuditLogResponse {
  rows:           AdminAuditRow[];
  total:          number;
  page:           number;
  per_page:       number;
  total_pages:    number;
  store_users:    AdminAuditUserOption[];
  target_filter:  string;
  action_filter:  string;
  user_filter:    string;
}

export function useAdminAuditLog(
  page: number, target: string, action: string, user: string,
) {
  return useQuery<AdminAuditLogResponse>({
    queryKey: ["admin", "audit-log", page, target, action, user],
    queryFn: () => {
      const p = new URLSearchParams();
      p.set("page", String(page));
      if (target) p.set("target", target);
      if (action) p.set("action", action);
      if (user)   p.set("user", user);
      return api<AdminAuditLogResponse>(
        `/api/v2/admin/audit-log?${p.toString()}`,
      );
    },
  });
}


export interface ReferralRedemptionRow {
  redeemed_at:            string;
  referee_store_id:       number;
  self_credit_applied:    boolean;
  referee_credit_applied: boolean;
  stripe_self_txn_id:     string;
}

export interface ReferralCodeResponse {
  code:                  string;
  is_active:             boolean;
  reward_self_cents:     number;
  reward_referee_cents:  number;
  redeemed_count:        number;
  credits_earned_cents:  number;
  share_url:             string;
  redemptions:           ReferralRedemptionRow[];
}

export function useReferralCode() {
  return useQuery<ReferralCodeResponse>({
    queryKey: ["admin", "referrals"],
    queryFn: () => api<ReferralCodeResponse>("/api/v2/admin/referrals"),
  });
}


// ── Per-store user management ──────────────────────────────

export interface AdminUserRow {
  id:         number;
  username:   string;
  full_name:  string;
  role:       string;
  is_active:  boolean;
  created_at: string;
  // null = every module the store has; a list restricts this
  // user's visible modules (U-3).
  module_access: string[] | null;
  // R-1: true when the user carries a custom-access permission
  // overlay instead of pure role permissions.
  has_custom_permissions: boolean;
}

export interface AdminUserListResponse {
  rows: AdminUserRow[];
}

export interface AdminUserDetailResponse {
  user: AdminUserRow;
}

export interface AdminUserCreateBody {
  // Identity (L-2): the person signs in with their email or phone.
  // At least one is required — the API 422s when both are blank.
  // There is no username to type; the server derives and stores it.
  email?:     string;
  phone?:     string;
  password:   string;
  full_name?: string;
  role?:      string;
  module_access?: string[] | null;
  // R-2: custom-access overlay written at creation time.
  // Omitted/null = pure role permissions.
  permissions?: PermMatrix | null;
}

export interface AdminUserUpdateBody {
  full_name?: string;
  role?:      string;
  is_active?: boolean;
  password?:  string;
  // PATCH semantics: omitted = unchanged; null = all modules;
  // a list = restrict to those modules.
  module_access?: string[] | null;
}

export function useAdminUsers() {
  const identity = getCurrentIdentity();
  return useQuery<AdminUserListResponse>({
    enabled: identity?.store_id != null,
    queryKey: ["admin", "users", identity?.store_id],
    queryFn: () =>
      api<AdminUserListResponse>("/api/v2/admin/users"),
  });
}

export function useAdminUser(uid: number | null) {
  return useQuery<AdminUserDetailResponse>({
    enabled: uid != null && Number.isFinite(uid),
    queryKey: ["admin", "users", "detail", uid],
    queryFn: () =>
      api<AdminUserDetailResponse>(`/api/v2/admin/users/${uid}`),
  });
}

export async function createAdminUser(
  body: AdminUserCreateBody,
): Promise<AdminUserRow> {
  return api<AdminUserRow>(
    "/api/v2/admin/users",
    { method: "POST", json: body },
  );
}

export async function updateAdminUser(
  uid: number, body: AdminUserUpdateBody,
): Promise<AdminUserRow> {
  return api<AdminUserRow>(
    `/api/v2/admin/users/${uid}`,
    { method: "PATCH", json: body },
  );
}

// ── Per-user custom access (R-1 overlay) ───────────────────

/** resource → action → allowed */
export type PermMatrix = Record<string, Record<string, boolean>>;

export interface UserPermissionMatrix {
  user_id:   number;
  role:      string;
  store_id:  number;
  resources: string[];
  actions:   string[];
  matrix:    PermMatrix;
  has_custom: boolean;
}

export function useAdminUserPermissions(uid: number | null) {
  return useQuery<UserPermissionMatrix>({
    enabled: uid != null && Number.isFinite(uid),
    queryKey: ["admin", "users", "permissions", uid],
    queryFn: () =>
      api<UserPermissionMatrix>(`/api/v2/admin/users/${uid}/permissions`),
  });
}

export async function setAdminUserPermissions(
  uid: number, matrix: PermMatrix,
): Promise<UserPermissionMatrix> {
  return api<UserPermissionMatrix>(
    `/api/v2/admin/users/${uid}/permissions`,
    { method: "PUT", json: { matrix } },
  );
}

export async function clearAdminUserPermissions(
  uid: number,
): Promise<UserPermissionMatrix> {
  return api<UserPermissionMatrix>(
    `/api/v2/admin/users/${uid}/permissions`,
    { method: "DELETE" },
  );
}
