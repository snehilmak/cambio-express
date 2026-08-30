// Unified Employees hub (E-2) — typed client for
// /api/v2/admin/employees. Shapes come from the generated
// OpenAPI types (CLAUDE.md: no hand-written interfaces).
import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import type { components } from "./openapi";

export type EmployeeRow = components["schemas"]["EmployeeRow"];
export type EmployeeLoginInfo = components["schemas"]["EmployeeLoginInfo"];
export type LoginOnlyRow = components["schemas"]["LoginOnlyRow"];
export type EmployeesListResponse =
  components["schemas"]["EmployeesListResponse"];
export type EmployeeCreateBody =
  components["schemas"]["EmployeeCreateRequest"];
export type EmployeeUpdateBody =
  components["schemas"]["EmployeeUpdateRequest"];

export function useEmployees() {
  const identity = getCurrentIdentity();
  return useQuery<EmployeesListResponse>({
    enabled: identity?.store_id != null,
    queryKey: ["employees", identity?.store_id],
    queryFn: () =>
      api<EmployeesListResponse>("/api/v2/admin/employees"),
  });
}

export async function createEmployee(
  body: EmployeeCreateBody,
): Promise<EmployeeRow> {
  return api<EmployeeRow>(
    "/api/v2/admin/employees",
    { method: "POST", json: body },
  );
}

export async function updateEmployee(
  id: number, body: EmployeeUpdateBody,
): Promise<EmployeeRow> {
  return api<EmployeeRow>(
    `/api/v2/admin/employees/${id}`,
    { method: "PATCH", json: body },
  );
}

export async function linkEmployeeLogin(
  id: number, userId: number,
): Promise<EmployeeRow> {
  return api<EmployeeRow>(
    `/api/v2/admin/employees/${id}/link`,
    { method: "POST", json: { user_id: userId } },
  );
}

export async function unlinkEmployeeLogin(
  id: number,
): Promise<EmployeeRow> {
  return api<EmployeeRow>(
    `/api/v2/admin/employees/${id}/link`,
    { method: "DELETE" },
  );
}
