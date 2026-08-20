import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import type { PillTone } from "../components/ui";

export const TICKET_STATUS_TONES: Record<string, PillTone> = {
  open: "accent",
  in_progress: "warning",
  resolved: "success",
  closed: "neutral",
};

export interface TicketRow {
  id: number;
  store_id: number;
  user_id: number;
  submitted_by: string;
  category: string;
  priority: string | null;
  subject: string;
  body: string;
  status: string;
  admin_reply: string | null;
  replied_at: string | null;
  replied_by: string | null;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
  store_name: string | null;
  assigned_to_user_id: number | null;
  assigned_to_name: string | null;
}

interface TicketListResponse {
  tickets: TicketRow[];
  total: number;
}

interface TicketResponse {
  ticket: TicketRow;
}

export function useMyTickets(status?: string) {
  const identity = getCurrentIdentity();
  const qs = status ? `?status=${status}` : "";
  return useQuery<TicketListResponse>({
    enabled: identity != null,
    queryKey: ["tickets", "mine", status],
    queryFn: () => api<TicketListResponse>(`/api/v2/tickets${qs}`),
  });
}

export function useAllTickets(status?: string, category?: string) {
  const identity = getCurrentIdentity();
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (category) params.set("category", category);
  const qs = params.toString() ? `?${params}` : "";
  return useQuery<TicketListResponse>({
    enabled:
      identity != null &&
      ["superadmin", "support"].includes(identity.role),
    queryKey: ["tickets", "all", status, category],
    queryFn: () => api<TicketListResponse>(`/api/v2/tickets/all${qs}`),
  });
}

export async function createTicket(body: {
  category: string;
  subject: string;
  body: string;
}): Promise<TicketResponse> {
  return api<TicketResponse>("/api/v2/tickets", {
    method: "POST",
    json: body,
  });
}

export async function updateTicket(
  id: number,
  body: {
    status?: string;
    priority?: string;
    admin_reply?: string;
  },
): Promise<TicketResponse> {
  return api<TicketResponse>(`/api/v2/tickets/${id}`, {
    method: "PUT",
    json: body,
  });
}

// ── Conversation thread ──────────────────────────────────────

/** One reply in a ticket's thread. `author_kind` is "user" (store
 *  side) or "staff" (platform side) — drives the bubble side. */
export interface TicketMessageRow {
  id: number;
  ticket_id: number;
  author_name: string;
  author_kind: string;
  body: string;
  created_at: string;
}

interface MessageListResponse {
  messages: TicketMessageRow[];
  total: number;
}

/** The ticket's thread, oldest first. `enabled` gates the fetch so
 *  collapsed rows don't fan out requests. */
export function useTicketMessages(ticketId: number, enabled: boolean) {
  return useQuery<MessageListResponse>({
    enabled,
    queryKey: ["tickets", "thread", ticketId],
    queryFn: () =>
      api<MessageListResponse>(`/api/v2/tickets/${ticketId}/messages`),
  });
}

/** Reply into the thread. Returns the ticket — a store-side reply to
 *  a resolved ticket auto-reopens it, so the status may have changed. */
export async function postTicketMessage(
  id: number, body: string,
): Promise<TicketResponse> {
  return api<TicketResponse>(`/api/v2/tickets/${id}/messages`, {
    method: "POST",
    json: { body },
  });
}

/** Reopen a CLOSED ticket (409 otherwise). */
export async function reopenTicket(id: number): Promise<TicketResponse> {
  return api<TicketResponse>(`/api/v2/tickets/${id}/reopen`, {
    method: "POST",
  });
}

/** Claim a ticket (platform staff): marks who is working it. 409 when
 *  a support person tries to take over someone else's claim. */
export async function claimTicket(id: number): Promise<TicketResponse> {
  return api<TicketResponse>(`/api/v2/tickets/${id}/claim`, {
    method: "POST",
  });
}

/** Release a claim (own claim for support; any for superadmin). */
export async function releaseTicket(id: number): Promise<TicketResponse> {
  return api<TicketResponse>(`/api/v2/tickets/${id}/release`, {
    method: "POST",
  });
}
