import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import type { components } from "./openapi";

// Typed straight off the FastAPI OpenAPI spec (CLAUDE.md standard).
export type Department = components["schemas"]["DepartmentRow"];
export type RegisterClose = components["schemas"]["RegisterCloseRow"];
export type DayCloseSummary = components["schemas"]["DayCloseSummaryResponse"];
export type RegisterCloseWrite =
  components["schemas"]["RegisterCloseWriteRequest"];

type DepartmentListResponse = components["schemas"]["DepartmentListResponse"];
type DepartmentResponse = components["schemas"]["DepartmentResponse"];

export function useDepartments(includeInactive = false) {
  const qs = includeInactive ? "?include_inactive=1" : "";
  return useQuery<DepartmentListResponse>({
    queryKey: ["dayclose", "departments", includeInactive],
    queryFn: () =>
      api<DepartmentListResponse>(`/api/v2/dayclose/departments${qs}`),
  });
}

export function useDayClose(day: string) {
  return useQuery<DayCloseSummary>({
    enabled: day.length === 10,
    queryKey: ["dayclose", "day", day],
    queryFn: () => api<DayCloseSummary>(`/api/v2/dayclose/day/${day}`),
  });
}

export async function createDepartment(body: {
  name: string; sort_order?: number; parent_id?: number | null;
}): Promise<DepartmentResponse> {
  return api<DepartmentResponse>("/api/v2/dayclose/departments", {
    method: "POST", json: body,
  });
}

export async function updateDepartment(
  id: number,
  body: {
    name?: string; sort_order?: number; is_active?: boolean;
    // 0 clears the parent link (server PATCH semantics).
    parent_id?: number;
  },
): Promise<DepartmentResponse> {
  return api<DepartmentResponse>(`/api/v2/dayclose/departments/${id}`, {
    method: "PUT", json: body,
  });
}

export async function upsertRegisterClose(
  day: string, body: RegisterCloseWrite,
): Promise<DayCloseSummary> {
  return api<DayCloseSummary>(`/api/v2/dayclose/day/${day}/closes`, {
    method: "POST", json: body,
  });
}

export async function deleteRegisterClose(
  id: number,
): Promise<DayCloseSummary> {
  return api<DayCloseSummary>(`/api/v2/dayclose/closes/${id}`, {
    method: "DELETE",
  });
}
