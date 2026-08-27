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

// ── Purchase invoices (P3) ───────────────────────────────────

export type InvoiceRow = components["schemas"]["InvoiceRow"];
export type InvoiceDetail = components["schemas"]["InvoiceDetail"];
export type InvoiceLineRow = components["schemas"]["InvoiceLineRow"];
export type InvoiceList = components["schemas"]["InvoiceListResponse"];
export type InvoiceWrite = components["schemas"]["InvoiceWriteRequest"];
export type InvoiceUpdate = components["schemas"]["InvoiceUpdateRequest"];
type InvoiceResponse = components["schemas"]["InvoiceResponse"];

export function useInvoices(params: {
  q: string;
  page: number;
  vendorId: string;
  status: string;
}) {
  const qs = new URLSearchParams({ page: String(params.page) });
  if (params.q) qs.set("q", params.q);
  if (params.vendorId) qs.set("vendor_id", params.vendorId);
  if (params.status) qs.set("status", params.status);
  return useQuery<InvoiceList>({
    queryKey: ["catalog", "invoices", params],
    queryFn: () => api<InvoiceList>(`/api/v2/catalog/invoices?${qs}`),
  });
}

export function useInvoice(id: number | null) {
  return useQuery<InvoiceResponse>({
    enabled: id != null,
    queryKey: ["catalog", "invoice", id],
    queryFn: () => api<InvoiceResponse>(`/api/v2/catalog/invoices/${id}`),
  });
}

export async function createInvoice(
  body: InvoiceWrite,
): Promise<InvoiceResponse> {
  return api<InvoiceResponse>("/api/v2/catalog/invoices", {
    method: "POST", json: body,
  });
}

export async function updateInvoice(
  // Partial: openapi-typescript marks server-defaulted fields
  // (clear_due_date, update_item_costs) required; the API treats
  // absent fields as "leave unchanged".
  id: number, body: Partial<InvoiceUpdate>,
): Promise<InvoiceResponse> {
  return api<InvoiceResponse>(`/api/v2/catalog/invoices/${id}`, {
    method: "PUT", json: body,
  });
}

export async function deleteInvoice(id: number): Promise<{ ok: boolean }> {
  return api<{ ok: boolean }>(`/api/v2/catalog/invoices/${id}`, {
    method: "DELETE",
  });
}

/** Resolve a scanned/typed code to a price-book item (exact
 *  pos_code match only) — the invoice line editor's item lookup. */
export async function lookupItemByCode(
  code: string,
): Promise<PriceBookItem | null> {
  const qs = new URLSearchParams({ q: code, per_page: "50" });
  const list = await api<ItemList>(`/api/v2/catalog/items?${qs}`);
  return list.rows.find((r) => r.pos_code === code) ?? null;
}
