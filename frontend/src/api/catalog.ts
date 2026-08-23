import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import type { components } from "./openapi";

// Typed straight off the FastAPI OpenAPI spec (CLAUDE.md standard).
export type Vendor = components["schemas"]["VendorRow"];
export type PriceBookItem = components["schemas"]["ItemRow"];
export type ItemList = components["schemas"]["ItemListResponse"];
export type ItemWrite = components["schemas"]["ItemWriteRequest"];
export type ItemUpdate = components["schemas"]["ItemUpdateRequest"];
export type VendorWrite = components["schemas"]["VendorWriteRequest"];
export type VendorUpdate = components["schemas"]["VendorUpdateRequest"];

type VendorListResponse = components["schemas"]["VendorListResponse"];
type VendorResponse = components["schemas"]["VendorResponse"];
type ItemResponse = components["schemas"]["ItemResponse"];

export function useVendors(includeInactive = false) {
  const qs = includeInactive ? "?include_inactive=1" : "";
  return useQuery<VendorListResponse>({
    queryKey: ["catalog", "vendors", includeInactive],
    queryFn: () =>
      api<VendorListResponse>(`/api/v2/catalog/vendors${qs}`),
  });
}

export function useItems(params: {
  q: string;
  page: number;
  departmentId: string;
  vendorId: string;
  includeInactive: boolean;
}) {
  const qs = new URLSearchParams({ page: String(params.page) });
  if (params.q) qs.set("q", params.q);
  if (params.departmentId) qs.set("department_id", params.departmentId);
  if (params.vendorId) qs.set("vendor_id", params.vendorId);
  if (params.includeInactive) qs.set("include_inactive", "1");
  return useQuery<ItemList>({
    queryKey: ["catalog", "items", params],
    queryFn: () => api<ItemList>(`/api/v2/catalog/items?${qs}`),
  });
}

export async function createVendor(body: VendorWrite): Promise<VendorResponse> {
  return api<VendorResponse>("/api/v2/catalog/vendors", {
    method: "POST", json: body,
  });
}

export async function updateVendor(
  id: number, body: VendorUpdate,
): Promise<VendorResponse> {
  return api<VendorResponse>(`/api/v2/catalog/vendors/${id}`, {
    method: "PUT", json: body,
  });
}

export async function createItem(body: ItemWrite): Promise<ItemResponse> {
  return api<ItemResponse>("/api/v2/catalog/items", {
    method: "POST", json: body,
  });
}

export async function updateItem(
  id: number, body: ItemUpdate,
): Promise<ItemResponse> {
  return api<ItemResponse>(`/api/v2/catalog/items/${id}`, {
    method: "PUT", json: body,
  });
}
