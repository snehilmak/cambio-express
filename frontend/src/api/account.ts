// Account-side API helpers (password change, store info,
// future profile / preferences, etc.).

import { useQuery } from "@tanstack/react-query";

import { api, ApiError } from "./../lib/api";
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

export interface SignupBody {
  store_name: string;
  email: string;
  password: string;
  phone?: string;
  ref_code?: string;
}

export interface ReferralPreview {
  code: string;
  reward_referee_cents: number;
}

export async function previewReferral(
  code: string,
): Promise<ReferralPreview | null> {
  try {
    return await api<ReferralPreview>(
      `/api/v2/auth/referral/${encodeURIComponent(code)}`,
    );
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

export interface SignupResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user_id: number;
  username: string;
  full_name: string;
  role: string;
  store_id: number | null;
  permissions: string[];
}

export async function signup(body: SignupBody): Promise<SignupResponse> {
  return api<SignupResponse>(
    "/api/v2/auth/signup",
    { method: "POST", json: body },
  );
}

export interface OwnerSignupBody {
  full_name: string;
  email: string;
  password: string;
}

export async function signupOwner(
  body: OwnerSignupBody,
): Promise<SignupResponse> {
  return api<SignupResponse>(
    "/api/v2/auth/signup/owner",
    { method: "POST", json: body },
  );
}

export interface StoreLookup {
  store_id: number;
  name: string;
  slug: string;
}

export interface TotpEnrollStartResponse {
  qr_svg:        string;
  secret:        string;
  secret_chunks: string;
  username:      string;
  issuer:        string;
}

export async function totpEnrollStart(
  pending_token: string,
): Promise<TotpEnrollStartResponse> {
  return api<TotpEnrollStartResponse>(
    "/api/v2/auth/login/totp/enroll/start",
    { method: "POST", json: { pending_token } },
  );
}

export async function totpEnrollFinish(
  pending_token: string, code: string,
): Promise<{ recovery_codes: string[] }> {
  return api<{ recovery_codes: string[] }>(
    "/api/v2/auth/login/totp/enroll/finish",
    { method: "POST", json: { pending_token, code } },
  );
}

export async function totpEnrollConfirm(
  pending_token: string,
): Promise<{ access_token: string; role: string; store_id: number | null }> {
  return api<{ access_token: string; role: string; store_id: number | null }>(
    "/api/v2/auth/login/totp/enroll/confirm",
    { method: "POST", json: { pending_token } },
  );
}

export async function lookupStoreBySlug(
  slug: string,
): Promise<StoreLookup | null> {
  try {
    return await api<StoreLookup>(
      `/api/v2/auth/store-by-slug/${encodeURIComponent(slug)}`,
    );
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}


export interface TaxExportYears {
  years:        number[];
  default_year: number;
}

export function useTaxExportYears() {
  return useQuery<TaxExportYears>({
    queryKey: ["admin", "tax-export", "years"],
    queryFn: () => api<TaxExportYears>("/api/v2/admin/tax-export/years"),
  });
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

export interface ProfileResponse {
  user_id:           number;
  username:          string;
  role:              string;
  full_name:         string;
  email:             string;
  phone:             string;
  timezone:          string;
  created_at:        string;
  last_login_at:     string;
  timezone_choices:  string[];
}

export interface ProfileUpdateBody {
  full_name?: string;
  email?:     string;
  phone?:     string;
  timezone?:  string;
}

export function useProfile() {
  return useQuery<ProfileResponse>({
    queryKey: ["account", "profile"],
    queryFn: () => api<ProfileResponse>("/api/v2/auth/profile"),
  });
}

export async function updateProfile(
  body: ProfileUpdateBody,
): Promise<ProfileResponse> {
  return api<ProfileResponse>("/api/v2/auth/profile", {
    method: "PUT", json: body,
  });
}


export interface NotificationsResponse {
  notify_trial_reminders:    boolean;
  notify_announcement_email: boolean;
  trial_toggle_applies:      boolean;
  role:                      string;
}

export interface NotificationsUpdateBody {
  notify_trial_reminders?:    boolean;
  notify_announcement_email?: boolean;
}

export function useNotifications() {
  return useQuery<NotificationsResponse>({
    queryKey: ["account", "notifications"],
    queryFn: () => api<NotificationsResponse>("/api/v2/auth/notifications"),
  });
}

export async function updateNotifications(
  body: NotificationsUpdateBody,
): Promise<NotificationsResponse> {
  return api<NotificationsResponse>("/api/v2/auth/notifications", {
    method: "PUT", json: body,
  });
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

// ── Team roster ────────────────────────────────────────────

export interface TeamMemberRow {
  id: number;
  name: string;
  is_active: boolean;
}

export function useTeam() {
  const identity = getCurrentIdentity();
  return useQuery<{ members: TeamMemberRow[] }>({
    enabled: identity?.store_id != null,
    queryKey: ["admin", "team", identity?.store_id],
    queryFn: () =>
      api<{ members: TeamMemberRow[] }>("/api/v2/admin/team"),
  });
}

export async function createTeamMember(name: string): Promise<TeamMemberRow> {
  return api<TeamMemberRow>(
    "/api/v2/admin/team",
    { method: "POST", json: { name } },
  );
}

export async function updateTeamMember(
  id: number,
  body: { name?: string; is_active?: boolean },
): Promise<TeamMemberRow> {
  return api<TeamMemberRow>(
    `/api/v2/admin/team/${id}`,
    { method: "PUT", json: body },
  );
}

export async function deactivateTeamMember(id: number): Promise<void> {
  await api<void>(
    `/api/v2/admin/team/${id}`,
    { method: "DELETE" },
  );
}

export async function forgotPassword(
  email: string,
): Promise<{ status: string }> {
  return api<{ status: string }>(
    "/api/v2/auth/forgot-password",
    { method: "POST", json: { email } },
  );
}

export interface ResetPasswordBody {
  token: string;
  new_password: string;
  confirm_password: string;
}

export async function resetPassword(
  body: ResetPasswordBody,
): Promise<{ status: string }> {
  return api<{ status: string }>(
    "/api/v2/auth/reset-password",
    { method: "POST", json: body },
  );
}


export interface PasskeyRow {
  id: number;
  name: string;
  aaguid: string;
  transports: string;
  created_at: string;
  last_used_at: string;
}

export interface PasskeyListResponse {
  passkeys: PasskeyRow[];
  total: number;
}

export function usePasskeys() {
  const identity = getCurrentIdentity();
  return useQuery<PasskeyListResponse>({
    enabled: identity != null,
    queryKey: ["account", "passkeys", identity?.user_id],
    queryFn: () => api<PasskeyListResponse>("/api/v2/auth/passkeys"),
  });
}

export async function deletePasskey(id: number): Promise<void> {
  await api<void>(`/api/v2/auth/passkeys/${id}`, { method: "DELETE" });
}
