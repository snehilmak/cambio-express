import { api } from "../lib/api";
import type { components } from "./openapi";

// Typed straight off the FastAPI OpenAPI spec (CLAUDE.md standard).
export type NaxmlPreview = components["schemas"]["NaxmlPreviewResponse"];
export type ImportRegisterRow = components["schemas"]["ImportRegisterRow"];
export type MappingRow = components["schemas"]["MappingRow"];
export type NaxmlCommitResult = components["schemas"]["NaxmlCommitResponse"];

type MappingListResponse = components["schemas"]["MappingListResponse"];

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
