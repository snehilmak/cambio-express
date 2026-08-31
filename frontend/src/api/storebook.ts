// Store Daily Book (D-2) — typed client for /api/v2/storebook/*.
// Shapes come from the generated OpenAPI types (CLAUDE.md: no
// hand-written interfaces).
import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import type { components } from "./openapi";

export type StoreBookDay = components["schemas"]["StoreBookDayResponse"];
export type StoreBookMonth =
  components["schemas"]["StoreBookMonthResponse"];
export type StoreBookMonthRow =
  components["schemas"]["StoreBookMonthRow"];
export type StoreBookColumn = components["schemas"]["StoreBookColumnSpec"];
export type StoreBookSection =
  components["schemas"]["StoreBookSectionSpec"];
export type StoreBookField = components["schemas"]["StoreBookFieldSpec"];
export type StoreBookTotals = components["schemas"]["StoreBookTotals"];
export type StoreBookUpdateBody =
  components["schemas"]["StoreBookUpdateRequest"];

/** One day's sheet. The layout ships with it, so the page never
 *  holds its own copy of the field list. */
export function useStoreBookDay(day: string) {
  const identity = getCurrentIdentity();
  return useQuery<StoreBookDay>({
    enabled: identity?.store_id != null && Boolean(day),
    queryKey: ["storebook", "day", identity?.store_id, day],
    queryFn: () => api<StoreBookDay>(`/api/v2/storebook/${day}`),
  });
}

export function useStoreBookMonth(year: number, month: number) {
  const identity = getCurrentIdentity();
  return useQuery<StoreBookMonth>({
    enabled: identity?.store_id != null,
    queryKey: ["storebook", "month", identity?.store_id, year, month],
    queryFn: () =>
      api<StoreBookMonth>(
        `/api/v2/storebook/month?year=${year}&month=${month}`,
      ),
    placeholderData: (prev) => prev,
  });
}

export async function updateStoreBookDay(
  day: string, body: StoreBookUpdateBody,
): Promise<StoreBookDay> {
  return api<StoreBookDay>(`/api/v2/storebook/${day}`, {
    method: "PATCH", json: body,
  });
}

export async function setStoreBookLock(
  day: string, locked: boolean,
): Promise<StoreBookDay> {
  return api<StoreBookDay>(`/api/v2/storebook/${day}/lock`, {
    method: "POST", json: { locked },
  });
}

/** Take the register's imported number back for one field. */
export async function restoreStoreBookField(
  day: string, fieldKey: string,
): Promise<StoreBookDay> {
  return api<StoreBookDay>(`/api/v2/storebook/${day}/restore`, {
    method: "POST", json: { field_key: fieldKey },
  });
}
