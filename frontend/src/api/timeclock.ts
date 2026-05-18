// Time-clock v1 API hooks. Backed by /api/v2/timeclock/* +
// /api/v2/admin/timeclock for the payroll history view.

import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";

export interface TimeClockEntryRow {
  id:                number;
  store_employee_id: number;
  employee_name:     string;
  clock_in_at:       string;          // ISO-8601 UTC
  clock_out_at:      string | null;
  hours_worked:      number | null;
  notes:             string;
}

export interface TimeClockStatusResponse {
  open_entries: TimeClockEntryRow[];
}

export interface TimeClockPunchResponse {
  entry: TimeClockEntryRow;
}

export interface TimeClockEntryList {
  rows:        TimeClockEntryRow[];
  total_hours: number;
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


export function useClockInMutation() {
  return useMutation({
    mutationFn: (input: { store_employee_id: number; notes: string }) =>
      api<TimeClockPunchResponse>("/api/v2/timeclock/clock-in", {
        method: "POST",
        json: input,
      }),
  });
}


export function useClockOutMutation() {
  return useMutation({
    mutationFn: (input: { store_employee_id: number; notes: string }) =>
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
