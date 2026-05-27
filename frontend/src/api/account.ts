// Account-side API helpers (password change, store info,
// future profile / preferences, etc.).

import { useQuery } from "@tanstack/react-query";

import { api, ApiError } from "./../lib/api";
import { getCurrentIdentity } from "./../lib/auth";
import type { components } from "./openapi";

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
  receipt_logo_url: string;
  receipt_footer:   string;
  receipt_tax_id:   string;
  timezone:         string;
  timezone_choices: string[];
  store_hours:      StoreHourEntry[];
  enforce_business_hours: boolean;
  timeclock_require_passkey: boolean;
  timeclock_geofence_lat:       number | null;
  timeclock_geofence_lng:       number | null;
  timeclock_geofence_radius_m:  number;
  timeclock_require_geofence:   boolean;
  timeclock_late_minutes_threshold: number;
  legal_name:       string;
  ein:              string;
  business_address: string;
}

export interface StoreHourEntry {
  day:    number;
  open:   string;
  close:  string;
  closed: boolean;
}

export interface StoreInfoUpdateBody {
  name?: string;
  email?: string;
  phone?: string;
  address?: string;
  federal_tax_rate?: number;
  receipt_logo_url?: string;
  receipt_footer?:   string;
  receipt_tax_id?:   string;
  timezone?:         string;
  store_hours?:      StoreHourEntry[];
  enforce_business_hours?: boolean;
  timeclock_require_passkey?: boolean;
  timeclock_geofence_lat?:       number | null;
  timeclock_geofence_lng?:       number | null;
  timeclock_geofence_radius_m?:  number;
  timeclock_require_geofence?:   boolean;
  timeclock_late_minutes_threshold?: number;
  legal_name?:       string;
  ein?:              string;
  business_address?: string;
}

// Allowed values for the per-user theme toggle. Dark is the
// design-system default; light is opt-in.
export type ThemePreference = "dark" | "light";

export interface ProfileResponse {
  user_id:           number;
  username:          string;
  role:              string;
  full_name:         string;
  email:             string;
  phone:             string;
  timezone:          string;
  theme_preference:  ThemePreference;
  created_at:        string;
  last_login_at:     string;
  timezone_choices:  string[];
}

export interface ProfileUpdateBody {
  full_name?:        string;
  email?:            string;
  phone?:            string;
  timezone?:         string;
  theme_preference?: ThemePreference;
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
  notify_trial_reminders:        boolean;
  notify_announcement_email:     boolean;
  notify_locked_day_digest:      boolean;
  notify_daily_summary:          boolean;
  notify_trial_reminders_push:   boolean;
  notify_announcement_push:      boolean;
  notify_locked_day_digest_push: boolean;
  notify_daily_summary_push:     boolean;
  notify_high_variance:          boolean;
  notify_high_variance_push:     boolean;
  notify_store_offline:          boolean;
  notify_store_offline_push:     boolean;
  trial_toggle_applies:          boolean;
  locked_day_digest_applies:     boolean;
  daily_summary_applies:         boolean;
  high_variance_applies:         boolean;
  store_offline_applies:         boolean;
  role:                          string;
}

export interface NotificationsUpdateBody {
  notify_trial_reminders?:        boolean;
  notify_announcement_email?:     boolean;
  notify_locked_day_digest?:      boolean;
  notify_daily_summary?:          boolean;
  notify_trial_reminders_push?:   boolean;
  notify_announcement_push?:      boolean;
  notify_locked_day_digest_push?: boolean;
  notify_daily_summary_push?:     boolean;
  notify_high_variance?:          boolean;
  notify_high_variance_push?:     boolean;
  notify_store_offline?:          boolean;
  notify_store_offline_push?:     boolean;
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


// ── Push subscriptions ────────────────────────────────────

export interface PushStatusResponse {
  enabled:      boolean;
  public_key:   string;
  subscribed:   boolean;
  device_count: number;
}

export function usePushStatus() {
  return useQuery<PushStatusResponse>({
    queryKey: ["account", "push-status"],
    queryFn:  () => api<PushStatusResponse>("/api/v2/auth/push/status"),
  });
}

export function subscribePush(input: {
  endpoint: string; p256dh: string; auth: string; user_agent?: string;
}): Promise<PushStatusResponse> {
  return api<PushStatusResponse>("/api/v2/auth/push/subscribe", {
    method: "POST",
    json: { user_agent: "", ...input },
  });
}

export function unsubscribePush(
  input: { endpoint: string },
): Promise<PushStatusResponse> {
  return api<PushStatusResponse>("/api/v2/auth/push/subscribe", {
    method: "DELETE",
    json: input,
  });
}


export interface StoreInfoResponse {
  store: StoreInfoRow;
  referral_code: string | null;
}

export function useStoreInfo() {
  const identity = getCurrentIdentity();
  return useQuery<StoreInfoResponse>({
    enabled: identity?.store_id != null,
    queryKey: ["admin", "store-info", identity?.store_id],
    queryFn: () =>
      api<StoreInfoResponse>("/api/v2/admin/store-info"),
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
  id:          number;
  name:        string;
  is_active:   boolean;
  hourly_rate: number;
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

export async function createTeamMember(
  name: string, hourly_rate = 0,
): Promise<TeamMemberRow> {
  return api<TeamMemberRow>(
    "/api/v2/admin/team",
    { method: "POST", json: { name, hourly_rate } },
  );
}

export async function updateTeamMember(
  id: number,
  body: { name?: string; is_active?: boolean; hourly_rate?: number },
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


// ── Passkey enrollment ─────────────────────────────────────
//
// Drives the WebAuthn registration dance against the FastAPI
// /passkeys/register/{begin,finish} endpoints. The browser-side
// `navigator.credentials.create()` call sits in the middle,
// producing the credential the server verifies.
//
// Browser support check: `window.PublicKeyCredential` exists on
// every modern Chromium / Firefox / Safari (and on most mobile
// browsers). Older builds lack it — the SPA hides the Add button
// when this returns false.

interface PasskeyRegisterBeginResponse {
  options_json:   string;
  register_token: string;
}

export function passkeysSupported(): boolean {
  return typeof window !== "undefined"
    && typeof window.PublicKeyCredential === "function";
}

// WebAuthn ships its options as base64url-encoded byte fields
// (challenge, user.id, excludeCredentials[].id). The browser API
// wants ArrayBuffer, so we decode + return the underlying buffer.
// Mirror of the helper in static/passkeys.js so the SPA can drop
// that legacy file once every page using passkeys is on React.
function _b64urlToArrayBuffer(s: string): ArrayBuffer {
  const pad = "=".repeat((4 - (s.length % 4)) % 4);
  const b64 = (s + pad).replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(b64);
  // Allocate fresh ArrayBuffer (not SharedArrayBuffer) so the
  // resulting BufferSource is compatible with WebAuthn's lib types.
  const out = new ArrayBuffer(bin.length);
  const view = new Uint8Array(out);
  for (let i = 0; i < bin.length; i++) view[i] = bin.charCodeAt(i);
  return out;
}

function _bytesToB64url(bytes: ArrayBuffer | Uint8Array): string {
  const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let bin = "";
  for (let i = 0; i < arr.length; i++) bin += String.fromCharCode(arr[i]);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export async function registerPasskey(name: string): Promise<PasskeyRow> {
  if (!passkeysSupported()) {
    throw new Error(
      "This browser doesn't expose the WebAuthn API. Use a modern Chrome, Safari, Firefox, or Edge build.",
    );
  }
  const begin = await api<PasskeyRegisterBeginResponse>(
    "/api/v2/auth/passkeys/register/begin",
    { method: "POST", json: {} },
  );
  const opts = JSON.parse(begin.options_json) as {
    challenge: string;
    user: { id: string; name: string; displayName: string };
    rp: { id: string; name: string };
    pubKeyCredParams: { type: string; alg: number }[];
    timeout?: number;
    excludeCredentials?: { id: string; type: string; transports?: string[] }[];
    authenticatorSelection?: PublicKeyCredentialCreationOptions["authenticatorSelection"];
    attestation?: PublicKeyCredentialCreationOptions["attestation"];
  };

  const publicKey: PublicKeyCredentialCreationOptions = {
    challenge: _b64urlToArrayBuffer(opts.challenge),
    rp: { id: opts.rp.id, name: opts.rp.name },
    user: {
      id: _b64urlToArrayBuffer(opts.user.id),
      name: opts.user.name,
      displayName: opts.user.displayName,
    },
    pubKeyCredParams: opts.pubKeyCredParams as PublicKeyCredentialParameters[],
    timeout: opts.timeout,
    excludeCredentials: (opts.excludeCredentials ?? []).map((c) => ({
      id: _b64urlToArrayBuffer(c.id),
      type: c.type as PublicKeyCredentialType,
      transports: c.transports as AuthenticatorTransport[] | undefined,
    })),
    authenticatorSelection: opts.authenticatorSelection,
    attestation: opts.attestation,
  };

  const cred = (await navigator.credentials.create({ publicKey })) as PublicKeyCredential | null;
  if (cred === null) throw new Error("Passkey creation was cancelled.");
  const att = cred.response as AuthenticatorAttestationResponse;
  const credentialJson = {
    id:       cred.id,
    rawId:    _bytesToB64url(cred.rawId),
    type:     cred.type,
    response: {
      clientDataJSON:    _bytesToB64url(att.clientDataJSON),
      attestationObject: _bytesToB64url(att.attestationObject),
    },
  };

  const finish = await api<{ passkey: PasskeyRow }>(
    "/api/v2/auth/passkeys/register/finish",
    {
      method: "POST",
      json: {
        register_token: begin.register_token,
        credential:     credentialJson,
        name,
      },
    },
  );
  return finish.passkey;
}


// ── My activity feed ─────────────────────────────────────────
// Cross-store per-user audit log. Powers /app/account/activity.

export type MyActivityRow = components["schemas"]["MyActivityRow"];
export type MyActivityResponse = components["schemas"]["MyActivityResponse"];

export interface ActivityFilters {
  target?: string;
  action?: string;
  page?:   number;
}

export function useMyActivity(filters: ActivityFilters = {}) {
  const qs = new URLSearchParams();
  if (filters.target) qs.set("target", filters.target);
  if (filters.action) qs.set("action", filters.action);
  if (filters.page && filters.page > 1) qs.set("page", String(filters.page));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return useQuery<MyActivityResponse>({
    queryKey: ["account", "activity", filters.target ?? "",
               filters.action ?? "", filters.page ?? 1],
    queryFn: () =>
      api<MyActivityResponse>(`/api/v2/auth/activity${suffix}`),
  });
}


// ── Active sessions / devices ───────────────────────────────

export interface ActiveSessionRow {
  session_id:   string;
  user_agent:   string;
  ip_address:   string;
  started_at:   string;
  last_used_at: string;
  expires_at:   string;
  is_current:   boolean;
}

export interface ActiveSessionsResponse {
  sessions: ActiveSessionRow[];
}

export interface SessionRevokeResponse {
  revoked: number;
}

export function useActiveSessions() {
  return useQuery<ActiveSessionsResponse>({
    queryKey: ["account", "sessions"],
    queryFn: () => api<ActiveSessionsResponse>("/api/v2/auth/sessions"),
  });
}

export async function revokeSession(
  sessionId: string,
): Promise<SessionRevokeResponse> {
  return api<SessionRevokeResponse>(
    `/api/v2/auth/sessions/${encodeURIComponent(sessionId)}`,
    { method: "DELETE" },
  );
}

export async function revokeOtherSessions(): Promise<SessionRevokeResponse> {
  return api<SessionRevokeResponse>(
    "/api/v2/auth/sessions/others",
    { method: "DELETE" },
  );
}
