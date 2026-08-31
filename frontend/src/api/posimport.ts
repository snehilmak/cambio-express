import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import type { components } from "./openapi";

// Typed straight off the FastAPI OpenAPI spec (CLAUDE.md standard).
export type NaxmlPreview = components["schemas"]["NaxmlPreviewResponse"];
export type ImportRegisterRow = components["schemas"]["ImportRegisterRow"];
export type MappingRow = components["schemas"]["MappingRow"];
export type NaxmlCommitResult = components["schemas"]["NaxmlCommitResponse"];
export type AgentKey = components["schemas"]["AgentKeyRow"];
export type StagedDay = components["schemas"]["StagedDayRow"];

type MappingListResponse = components["schemas"]["MappingListResponse"];
type AgentKeyListResponse = components["schemas"]["AgentKeyListResponse"];
type AgentKeyIssueResponse = components["schemas"]["AgentKeyIssueResponse"];
type StagedDaysResponse = components["schemas"]["StagedDaysResponse"];

export async function previewNaxml(
  contentBase64: string,
): Promise<NaxmlPreview> {
  return api<NaxmlPreview>("/api/v2/posimport/naxml/preview", {
    method: "POST", json: { content_base64: contentBase64 },
  });
}

export async function fetchMappings(): Promise<MappingListResponse> {
  return api<MappingListResponse>("/api/v2/posimport/mapping");
}

export async function saveMappings(
  mappings: Array<{ merchandise_code: string; department_id: number }>,
): Promise<MappingListResponse> {
  return api<MappingListResponse>("/api/v2/posimport/mapping", {
    method: "PUT", json: { mappings },
  });
}

export async function commitNaxml(
  contentBase64: string, day: string,
): Promise<NaxmlCommitResult> {
  return api<NaxmlCommitResult>("/api/v2/posimport/naxml/commit", {
    method: "POST", json: { content_base64: contentBase64, day },
  });
}

export function useAgentKeys() {
  return useQuery<AgentKeyListResponse>({
    queryKey: ["posimport", "agent-keys"],
    queryFn: () => api<AgentKeyListResponse>("/api/v2/posimport/agent-keys"),
  });
}

export async function issueAgentKey(
  label: string,
): Promise<AgentKeyIssueResponse> {
  return api<AgentKeyIssueResponse>("/api/v2/posimport/agent-keys", {
    method: "POST", json: { label },
  });
}

export async function revokeAgentKey(
  id: number,
): Promise<AgentKeyListResponse> {
  return api<AgentKeyListResponse>(
    `/api/v2/posimport/agent-keys/${id}/revoke`, { method: "POST" },
  );
}

export function useStagedDays() {
  return useQuery<StagedDaysResponse>({
    queryKey: ["posimport", "staged"],
    queryFn: () => api<StagedDaysResponse>("/api/v2/posimport/staged"),
    refetchInterval: 60_000,   // agent pushes land continuously
  });
}

export async function commitStagedDay(
  day: string,
): Promise<NaxmlCommitResult> {
  return api<NaxmlCommitResult>("/api/v2/posimport/staged/commit", {
    method: "POST", json: { day },
  });
}

/** Read a File into the base64 payload the ingest API expects. */
export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error);
    reader.onload = () => {
      // result is "data:<mime>;base64,<payload>" — strip the prefix.
      const url = String(reader.result);
      resolve(url.slice(url.indexOf(",") + 1));
    };
    reader.readAsDataURL(file);
  });
}

// ── Price-book warm start (P2-3) ─────────────────────────────

export type PriceBookHarvest =
  components["schemas"]["PriceBookHarvestResponse"];
export type PriceBookSeedResult =
  components["schemas"]["PriceBookSeedResponse"];

export async function previewPriceBookSeed(): Promise<PriceBookHarvest> {
  return api<PriceBookHarvest>("/api/v2/posimport/pricebook/preview");
}

export async function commitPriceBookSeed(): Promise<PriceBookSeedResult> {
  return api<PriceBookSeedResult>("/api/v2/posimport/pricebook/commit", {
    method: "POST",
  });
}

// ── Item movement (G-2) ──────────────────────────────────────

export type ItemMovement =
  components["schemas"]["ItemMovementResponse"];

export function useItemMovement(params: {
  start: string; end: string; q: string; page: number;
}) {
  return useQuery<ItemMovement>({
    enabled: Boolean(params.start && params.end),
    queryKey: ["posimport", "item-movement", params],
    queryFn: () => {
      const p = new URLSearchParams({
        start: params.start, end: params.end,
        page: String(params.page),
      });
      if (params.q) p.set("q", params.q);
      return api<ItemMovement>(
        `/api/v2/posimport/item-movement?${p.toString()}`,
      );
    },
  });
}


// ── Transactions (G-6) ──────────────────────────────────────

export type PosTransactionRow = components["schemas"]["PosTransactionRow"];
export type PosTransaction = components["schemas"]["PosTransactionDetail"];
export type PosTransactionLine =
  components["schemas"]["PosTransactionLineRow"];
export type PosTransactionTender =
  components["schemas"]["PosTransactionTenderRow"];

type PosTransactionListResponse =
  components["schemas"]["PosTransactionListResponse"];
type PosTransactionDetailResponse =
  components["schemas"]["PosTransactionDetailResponse"];

export function useTransactions(params: {
  start: string;
  end: string;
  q?: string;
  kind?: string;
  registerId?: string;
  voidedOnly?: boolean;
  page?: number;
}) {
  const qs = new URLSearchParams({
    start: params.start,
    end: params.end,
    page: String(params.page ?? 1),
  });
  if (params.q) qs.set("q", params.q);
  if (params.kind) qs.set("kind", params.kind);
  if (params.registerId) qs.set("register_id", params.registerId);
  if (params.voidedOnly) qs.set("voided_only", "true");
  return useQuery<PosTransactionListResponse>({
    // Both dates must be present or the server 422s on the range.
    enabled: params.start.length === 10 && params.end.length === 10,
    queryKey: ["posimport", "transactions", qs.toString()],
    queryFn: () => api<PosTransactionListResponse>(
      `/api/v2/posimport/transactions?${qs.toString()}`,
    ),
  });
}

export function useTransaction(id: number | null) {
  return useQuery<PosTransactionDetailResponse>({
    enabled: id != null && id > 0,
    queryKey: ["posimport", "transaction", id],
    queryFn: () => api<PosTransactionDetailResponse>(
      `/api/v2/posimport/transactions/${id}`,
    ),
  });
}
