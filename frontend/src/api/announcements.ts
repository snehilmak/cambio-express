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
export type ActiveAnnouncementRow =
  components["schemas"]["ActiveAnnouncementRow"];
export type ActiveAnnouncementsResponse =
  components["schemas"]["ActiveAnnouncementsResponse"];

export function useAnnouncements() {
  const identity = getCurrentIdentity();
  return useQuery<AnnouncementListResponse>({
    enabled: identity?.role === "superadmin",
    queryKey: ["announcements", "list", identity?.user_id],
    queryFn: () =>
      api<AnnouncementListResponse>("/api/v2/announcements"),
  });
}

// Currently-visible banners for the AppShell top zone. Polled every
// 5 minutes — banner urgency is "we'd like the cashier to see this
// soon," not "right this second." Disabled when no identity is
// loaded so we don't 401-spam during the unauth phase.
export function useActiveAnnouncements() {
  const identity = getCurrentIdentity();
  return useQuery<ActiveAnnouncementsResponse>({
    enabled: !!identity,
    queryKey: ["announcements", "active", identity?.user_id],
    queryFn: () =>
      api<ActiveAnnouncementsResponse>("/api/v2/announcements/active"),
    refetchInterval: 5 * 60 * 1000,
    refetchIntervalInBackground: false,
    staleTime: 60 * 1000,
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
