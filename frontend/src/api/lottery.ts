import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import type { components } from "./openapi";

// Typed straight off the FastAPI OpenAPI spec (CLAUDE.md standard).
export type LotteryGame = components["schemas"]["GameRow"];
export type LotteryPack = components["schemas"]["PackRow"];
export type LotteryDayRow = components["schemas"]["DayCountRow"];
export type LotteryDaySummary = components["schemas"]["DaySummaryResponse"];

type GameListResponse = components["schemas"]["GameListResponse"];
type GameResponse = components["schemas"]["GameResponse"];
type PackListResponse = components["schemas"]["PackListResponse"];
type PackResponse = components["schemas"]["PackResponse"];

export function useLotteryGames(includeInactive = false) {
  const qs = includeInactive ? "?include_inactive=1" : "";
  return useQuery<GameListResponse>({
    queryKey: ["lottery", "games", includeInactive],
    queryFn: () => api<GameListResponse>(`/api/v2/lottery/games${qs}`),
  });
}

export function useLotteryPacks(status?: string) {
  const qs = status ? `?status=${status}` : "";
  return useQuery<PackListResponse>({
    queryKey: ["lottery", "packs", status ?? "all"],
    queryFn: () => api<PackListResponse>(`/api/v2/lottery/packs${qs}`),
  });
}

export function useLotteryDay(day: string) {
  return useQuery<LotteryDaySummary>({
    enabled: day.length === 10,
    queryKey: ["lottery", "day", day],
    queryFn: () => api<LotteryDaySummary>(`/api/v2/lottery/day/${day}`),
  });
}

export async function createLotteryGame(body: {
  game_number: string; name: string; ticket_price: number;
  tickets_per_pack: number;
}): Promise<GameResponse> {
  return api<GameResponse>("/api/v2/lottery/games", {
    method: "POST", json: body,
  });
}

export async function updateLotteryGame(
  id: number,
  body: {
    name?: string; ticket_price?: number; tickets_per_pack?: number;
    is_active?: boolean;
  },
): Promise<GameResponse> {
  return api<GameResponse>(`/api/v2/lottery/games/${id}`, {
    method: "PUT", json: body,
  });
}

export async function receiveLotteryPack(body: {
  game_id: number; pack_number: string; received_on: string;
}): Promise<PackResponse> {
  return api<PackResponse>("/api/v2/lottery/packs", {
    method: "POST", json: body,
  });
}

export async function activateLotteryPack(
  id: number,
  body: { activated_on: string; opening_ticket: number; bin_number: string },
): Promise<PackResponse> {
  return api<PackResponse>(`/api/v2/lottery/packs/${id}/activate`, {
    method: "POST", json: body,
  });
}

export async function settleLotteryPack(
  id: number, on: string,
): Promise<PackResponse> {
  return api<PackResponse>(`/api/v2/lottery/packs/${id}/settle`, {
    method: "POST", json: { on },
  });
}

export async function returnLotteryPack(
  id: number, on: string,
): Promise<PackResponse> {
  return api<PackResponse>(`/api/v2/lottery/packs/${id}/return`, {
    method: "POST", json: { on },
  });
}

export async function recordLotteryCount(
  day: string, body: { pack_id: number; closing_ticket: number },
): Promise<LotteryDaySummary> {
  return api<LotteryDaySummary>(`/api/v2/lottery/day/${day}/counts`, {
    method: "POST", json: body,
  });
}
