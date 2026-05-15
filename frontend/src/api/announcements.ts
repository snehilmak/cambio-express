// Announcements API hooks. Backed by /api/v2/announcements/*.
//
// Superadmin-scoped CRUD over the global banner.
//
// Types are sourced from ``openapi.d.ts`` (regenerate with
// ``npm run generate-types``) so request/response shapes stay in
// lockstep with the Pydantic schemas on the backend. See
// ``docs/architecture/openapi-types.md`` for the workflow.

import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import type { components } from "./openapi";

export type AnnouncementRow = components["schemas"]["AnnouncementRow"];
export type AnnouncementListResponse =
  components["schemas"]["AnnouncementListResponse"];
export type CreateAnnouncementBody =
  components["schemas"]["AnnouncementCreateRequest"];
type AnnouncementResponse = components["schemas"]["AnnouncementResponse"];

export function useAnnouncements() {
  const identity = getCurrentIdentity();
  return useQuery<AnnouncementListResponse>({
    enabled: identity?.role === "superadmin",
    queryKey: ["announcements", "list", identity?.user_id],
    queryFn: () =>
      api<AnnouncementListResponse>("/api/v2/announcements"),
  });
}

export async function createAnnouncement(
  body: CreateAnnouncementBody,
): Promise<AnnouncementResponse> {
  return api<AnnouncementResponse>(
    "/api/v2/announcements",
    { method: "POST", json: body },
  );
}

export async function toggleAnnouncement(
  id: number, isActive: boolean,
): Promise<AnnouncementResponse> {
  return api<AnnouncementResponse>(
    `/api/v2/announcements/${id}/toggle`,
    { method: "POST", json: { is_active: isActive } },
  );
}

export async function deleteAnnouncement(id: number): Promise<void> {
  await api<void>(`/api/v2/announcements/${id}`, { method: "DELETE" });
}
