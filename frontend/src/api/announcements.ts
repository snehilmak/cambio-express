// Announcements API hooks. Backed by /api/v2/announcements/*.
//
// Superadmin-scoped CRUD over the global banner.

import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";

export interface AnnouncementRow {
  id: number;
  message: string;
  level: string;
  is_active: boolean;
  is_visible: boolean;
  starts_at: string;
  expires_at: string;
  created_at: string;
  created_by: number | null;
  broadcast_requested: boolean;
  broadcast_sent_at: string;
}

export interface AnnouncementListResponse {
  rows: AnnouncementRow[];
  total: number;
}

export function useAnnouncements() {
  const identity = getCurrentIdentity();
  return useQuery<AnnouncementListResponse>({
    enabled: identity?.role === "superadmin",
    queryKey: ["announcements", "list", identity?.user_id],
    queryFn: () =>
      api<AnnouncementListResponse>("/api/v2/announcements"),
  });
}

export interface CreateAnnouncementBody {
  message: string;
  level?: "info" | "warning" | "error" | "success";
  expires_days?: number;
  broadcast?: boolean;
  /** Optional ISO-8601 datetime (UTC) when the banner should go
   *  live. Empty / omitted = start immediately. expires_days is
   *  measured from start_at_iso when scheduled — a 7-day banner
   *  set to start next Monday is visible Mon-Sun, not 7 days from
   *  create time. */
  start_at_iso?: string;
}

export async function createAnnouncement(
  body: CreateAnnouncementBody,
): Promise<{ announcement: AnnouncementRow }> {
  return api<{ announcement: AnnouncementRow }>(
    "/api/v2/announcements",
    { method: "POST", json: body },
  );
}

export async function toggleAnnouncement(
  id: number, isActive: boolean,
): Promise<{ announcement: AnnouncementRow }> {
  return api<{ announcement: AnnouncementRow }>(
    `/api/v2/announcements/${id}/toggle`,
    { method: "POST", json: { is_active: isActive } },
  );
}

export async function deleteAnnouncement(id: number): Promise<void> {
  await api<void>(`/api/v2/announcements/${id}`, { method: "DELETE" });
}
