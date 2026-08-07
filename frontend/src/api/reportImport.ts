// Report-import API. Backed by /api/v2/report-import/*.
//
// The PDF is read client-side as base64 and posted in a JSON body —
// no multipart, and (for now) nothing is stored server-side: the
// backend parses in memory and returns the rows for review.

import { api } from "../lib/api";
import type { components } from "./openapi";

export type IntermexReport = components["schemas"]["IntermexReportResponse"];
export type IntermexRow = components["schemas"]["IntermexTxnRowResponse"];
export type SectionTotals = components["schemas"]["SectionTotalsResponse"];

/** Read a File as base64 (without the `data:...;base64,` prefix). */
function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result ?? "");
      const comma = result.indexOf(",");
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.onerror = () => reject(reader.error ?? new Error("read failed"));
    reader.readAsDataURL(file);
  });
}

/** Upload + parse an Intermex daily-close PDF. Returns the structured
 *  rows for review. Nothing is persisted. */
export async function parseIntermexReport(file: File): Promise<IntermexReport> {
  const content_base64 = await fileToBase64(file);
  return api<IntermexReport>("/api/v2/report-import/intermex/parse", {
    method: "POST",
    json: { content_base64, filename: file.name },
  });
}
