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
    enabled: identity?.role === "superadmin",
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
