// Time-clock v1 API hooks. Backed by /api/v2/timeclock/* +
// /api/v2/admin/timeclock for the payroll history view.

import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";

export type TimeClockStatus = "pending" | "approved" | "rejected";

export interface TimeClockEntryRow {
  id:                number;
  store_employee_id: number;
  employee_name:     string;
  clock_in_at:       string;          // ISO-8601 UTC
  clock_out_at:      string | null;
  hours_worked:      number | null;
  notes:             string;
  status:            TimeClockStatus;
  adjusted:          boolean;
  /** Set while the cashier is on break; null after End break
   *  or clock-out. */
  break_started_at:  string | null;
  /** Running total of break minutes accumulated across all
   *  pause/resume cycles within this shift. ``clock_out``
   *  subtracts this from elapsed wall-clock before computing
   *  ``hours_worked``. */
  break_minutes:     number;
  /** Minutes the ``clock_in_at`` lagged the matching planned
   *  shift's ``start_time`` in store-local time. Negative =
   *  early, 0 = on time, ``null`` = no planned shift to
   *  compare against. The SPA only paints a "Late" pill when
   *  this exceeds ``late_threshold_minutes`` on the list. */
  late_minutes:      number | null;
}

export interface TimeClockStatusResponse {
  open_entries: TimeClockEntryRow[];
}

export interface TimeClockPunchResponse {
  entry: TimeClockEntryRow;
}

export interface TimeClockEntryList {
  rows:                   TimeClockEntryRow[];
  total_hours:            number;
  approved_hours:         number;
  pending_hours:          number;
  late_threshold_minutes: number;
}


/** Live "who's on the clock?" — polled by the punch page so the
 *  Clock-in / Clock-out button reflects the current state. */
export function useTimeClockStatus() {
  return useQuery<TimeClockStatusResponse>({
    queryKey: ["timeclock", "status"],
    queryFn: () =>
      api<TimeClockStatusResponse>("/api/v2/timeclock/status"),
    // 20s polling matches the transfers list — fresh enough that
    // two cashiers on different terminals see each other within
    // a normal session, but not so chatty it spams the server.
    refetchInterval: 20_000,
    refetchIntervalInBackground: false,
  });
}


export interface PunchInput {
  store_employee_id: number;
  notes:             string;
  /** WebAuthn assertion (from ``navigator.credentials.get()``)
   *  + the matching ``assert_token`` that came back from
   *  ``/timeclock/passkey/challenge``. Required only when
   *  ``store.timeclock_require_passkey`` is True. */
  assert_token?:     string;
  assertion?:        unknown;
  /** Browser geolocation. Required only when
   *  ``store.timeclock_require_geofence`` is True; ignored
   *  otherwise. */
  geo_lat?:          number;
  geo_lng?:          number;
}


export function useClockInMutation() {
  return useMutation({
    mutationFn: (input: PunchInput) =>
      api<TimeClockPunchResponse>("/api/v2/timeclock/clock-in", {
        method: "POST",
        json: input,
      }),
  });
}


export function useClockOutMutation() {
  return useMutation({
    mutationFn: (input: PunchInput) =>
      api<TimeClockPunchResponse>("/api/v2/timeclock/clock-out", {
        method: "POST",
        json: input,
      }),
  });
}


/** Admin payroll history. ``from`` / ``to`` are YYYY-MM-DD
 *  (half-open: ``to`` is the day AFTER the period end). */
export function useAdminTimeClock(
  from: string, to: string, storeEmployeeId?: number,
) {
  const empParam = storeEmployeeId
    ? `&store_employee_id=${storeEmployeeId}`
    : "";
  return useQuery<TimeClockEntryList>({
    queryKey: ["timeclock", "admin", from, to, storeEmployeeId ?? null],
    queryFn: () =>
      api<TimeClockEntryList>(
        `/api/v2/admin/timeclock?from=${encodeURIComponent(from)}`
        + `&to=${encodeURIComponent(to)}${empParam}`,
      ),
    enabled: Boolean(from && to),
  });
}


// ── Admin CRUD ──────────────────────────────────────────────

export interface AdminCreateEntryBody {
  store_employee_id: number;
  clock_in_at:       string;          // ISO-8601, e.g. "2026-05-15T09:00"
  clock_out_at:      string | null;   // omit / null → open entry
  notes:             string;
}

export interface AdminUpdateEntryBody {
  /** Set explicitly to ``null`` (not undefined) to re-open the entry. */
  clock_in_at?:  string;
  clock_out_at?: string | null;
  notes?:        string;
  status?:       TimeClockStatus;
}

export function adminCreateEntry(
  body: AdminCreateEntryBody,
): Promise<TimeClockPunchResponse> {
  return api<TimeClockPunchResponse>("/api/v2/admin/timeclock", {
    method: "POST",
    json: body,
  });
}

export function adminUpdateEntry(
  id: number, body: AdminUpdateEntryBody,
): Promise<TimeClockPunchResponse> {
  return api<TimeClockPunchResponse>(`/api/v2/admin/timeclock/${id}`, {
    method: "PUT",
    json: body,
  });
}

export function adminDeleteEntry(id: number): Promise<void> {
  return api<void>(`/api/v2/admin/timeclock/${id}`, {
    method: "DELETE",
  });
}

export interface TimeClockHistoryRow {
  id:         number;
  at:         string;     // ISO-8601 UTC
  actor:      string;
  actor_role: string;
  action:     string;
  summary:    string;
}

export interface TimeClockHistoryResponse {
  rows: TimeClockHistoryRow[];
}

export function useTimeClockHistory(entryId: number | null) {
  return useQuery<TimeClockHistoryResponse>({
    queryKey: ["timeclock", "history", entryId ?? 0],
    queryFn: () =>
      api<TimeClockHistoryResponse>(
        `/api/v2/admin/timeclock/${entryId}/history`,
      ),
    enabled: entryId != null && entryId > 0,
  });
}


// ── Passkey-required punch (v2 anti-buddy-punching) ─────────

export interface TimeClockCredentialRow {
  store_employee_id: number;
  employee_name:     string;
  has_passkey:       boolean;
  name:              string;
  registered_at:     string;
  last_used_at:      string;
}

export interface TimeClockCredentialList {
  rows: TimeClockCredentialRow[];
}

export interface PunchChallengeResponse {
  options_json: string;
  assert_token: string;
}

export interface RegisterBeginResponse {
  options_json:   string;
  register_token: string;
}

export function useTimeClockCredentials() {
  return useQuery<TimeClockCredentialList>({
    queryKey: ["timeclock", "credentials"],
    queryFn: () =>
      api<TimeClockCredentialList>(
        "/api/v2/admin/timeclock/credentials",
      ),
  });
}

export function fetchPunchChallenge(
  store_employee_id: number,
): Promise<PunchChallengeResponse> {
  return api<PunchChallengeResponse>(
    "/api/v2/timeclock/passkey/challenge",
    { method: "POST", json: { store_employee_id } },
  );
}

export function adminRegisterCredentialBegin(
  store_employee_id: number,
): Promise<RegisterBeginResponse> {
  return api<RegisterBeginResponse>(
    `/api/v2/admin/timeclock/credentials/${store_employee_id}/register/begin`,
    { method: "POST", json: {} },
  );
}

export function adminRegisterCredentialFinish(
  store_employee_id: number,
  body: { register_token: string; credential: unknown; name?: string },
): Promise<TimeClockCredentialRow> {
  return api<TimeClockCredentialRow>(
    `/api/v2/admin/timeclock/credentials/${store_employee_id}/register/finish`,
    { method: "POST", json: body },
  );
}

export function adminDeleteCredential(
  store_employee_id: number,
): Promise<void> {
  return api<void>(
    `/api/v2/admin/timeclock/credentials/${store_employee_id}`,
    { method: "DELETE" },
  );
}


// ── Paystub (v2 payroll) ────────────────────────────────────

export interface PaystubShiftRow {
  id:            number;
  clock_in_at:   string;
  clock_out_at:  string | null;
  hours_worked:  number | null;
  status:        TimeClockStatus;
  notes:         string;
}

export interface PaystubResponse {
  store_employee_id: number;
  employee_name:     string;
  hourly_rate:       number;
  approved_hours:    number;
  gross_pay:         number;
  from_date:         string;
  to_date:           string;
  shifts:            PaystubShiftRow[];
}

export function usePaystub(
  storeEmployeeId: number | null, from: string, to: string,
) {
  return useQuery<PaystubResponse>({
    queryKey: [
      "timeclock", "paystub",
      storeEmployeeId ?? 0, from, to,
    ],
    queryFn: () =>
      api<PaystubResponse>(
        `/api/v2/admin/timeclock/paystub/${storeEmployeeId}`
        + `?from=${encodeURIComponent(from)}`
        + `&to=${encodeURIComponent(to)}`,
      ),
    enabled: storeEmployeeId != null
             && storeEmployeeId > 0
             && Boolean(from && to),
  });
}


// ── Break tracking (v2) ────────────────────────────────────

export function useStartBreakMutation() {
  return useMutation({
    mutationFn: (input: { store_employee_id: number }) =>
      api<TimeClockPunchResponse>("/api/v2/timeclock/break/start", {
        method: "POST",
        json: input,
      }),
  });
}

export function useStopBreakMutation() {
  return useMutation({
    mutationFn: (input: { store_employee_id: number }) =>
      api<TimeClockPunchResponse>("/api/v2/timeclock/break/stop", {
        method: "POST",
        json: input,
      }),
  });
}


// ── Shift scheduling (v2) ──────────────────────────────────

export interface ShiftRow {
  id:                number;
  store_employee_id: number;
  employee_name:     string;
  shift_date:        string;  // "YYYY-MM-DD"
  start_time:        string;  // "HH:MM:SS"
  end_time:          string;  // "HH:MM:SS"
  notes:             string;
}

export interface ShiftList {
  rows: ShiftRow[];
}

export interface ShiftCreateInput {
  store_employee_id: number;
  shift_date:        string;  // "YYYY-MM-DD"
  start_time:        string;  // "HH:MM" or "HH:MM:SS"
  end_time:          string;
  notes?:            string;
}

export interface ShiftUpdateInput {
  store_employee_id?: number;
  shift_date?:        string;
  start_time?:        string;
  end_time?:          string;
  notes?:             string;
}

export function useShifts(from: string, to: string) {
  return useQuery<ShiftList>({
    queryKey: ["timeclock", "shifts", from, to],
    queryFn: () => api<ShiftList>(
      `/api/v2/admin/timeclock/shifts?from=${encodeURIComponent(from)}`
      + `&to=${encodeURIComponent(to)}`,
    ),
    enabled: Boolean(from && to),
  });
}

export function createShift(input: ShiftCreateInput): Promise<ShiftRow> {
  return api<ShiftRow>("/api/v2/admin/timeclock/shifts", {
    method: "POST",
    json: input,
  });
}

export function updateShift(
  id: number, input: ShiftUpdateInput,
): Promise<ShiftRow> {
  return api<ShiftRow>(`/api/v2/admin/timeclock/shifts/${id}`, {
    method: "PATCH",
    json: input,
  });
}

export function deleteShift(id: number): Promise<void> {
  return api<void>(`/api/v2/admin/timeclock/shifts/${id}`, {
    method: "DELETE",
  });
}
