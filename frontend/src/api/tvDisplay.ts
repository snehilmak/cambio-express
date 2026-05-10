// TV Display API hooks. Backed by /api/v2/tv-display/*.
//
// Read: overview (settings + countries + active pairing).
// Write: settings save, public-token rotate, Fire TV claim/revoke,
//        country create/delete. The country *editor* (bank+rate
//        matrix) still POSTs to legacy Flask at
//        /tv-display/countries/<id> until the next migration slice.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../lib/api";

export interface TVDisplayCountryStat {
  id: number;
  country_code: string;
  country_name: string;
  sort_order: number;
  mt_companies: string;
  bank_count: number;
  rate_count: number;
}

export interface TVPairingSummary {
  id: number;
  device_label: string;
  paired_at: string;
  last_seen_at: string;
}

export interface TVDisplayOverviewResponse {
  display_id: number;
  title: string;
  subtitle: string;
  orientation: string;
  theme: string;
  public_token: string;
  public_url: string;
  last_updated_at: string;
  countries: TVDisplayCountryStat[];
  active_pairing: TVPairingSummary | null;
}

export function useTVDisplayOverview() {
  return useQuery<TVDisplayOverviewResponse>({
    queryKey: ["tv-display", "overview"],
    queryFn: () => api<TVDisplayOverviewResponse>("/api/v2/tv-display/overview"),
  });
}

export interface TVDisplaySettingsUpdate {
  title: string;
  subtitle: string;
  orientation: string;
  theme: string;
}

export function useSaveTVDisplaySettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: TVDisplaySettingsUpdate) =>
      api("/api/v2/tv-display/settings", { method: "POST", json: payload }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tv-display"] }),
  });
}

export interface TVDisplayRegenerateTokenResponse {
  public_token: string;
  public_url: string;
}

export function useRegenerateTVDisplayToken() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api<TVDisplayRegenerateTokenResponse>(
        "/api/v2/tv-display/regenerate-token",
        { method: "POST", json: {} },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tv-display"] }),
  });
}

export function useClaimTVPairCode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (code: string) =>
      api("/api/v2/tv-display/claim", {
        method: "POST",
        json: { code },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tv-display"] }),
  });
}

export function useRevokeTVPairing() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (pairingId: number) =>
      api(`/api/v2/tv-display/pairings/${pairingId}/revoke`, {
        method: "POST",
        json: {},
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tv-display"] }),
  });
}

export interface TVDisplayCreateCountryRequest {
  country_name: string;
  country_code: string;
  mt_companies?: string;
}

export interface TVDisplayCreateCountryResponse {
  id: number;
  country_name: string;
  country_code: string;
}

export function useCreateTVDisplayCountry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: TVDisplayCreateCountryRequest) =>
      api<TVDisplayCreateCountryResponse>("/api/v2/tv-display/countries", {
        method: "POST",
        json: payload,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tv-display"] }),
  });
}

export function useDeleteTVDisplayCountry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (countryId: number) =>
      api(`/api/v2/tv-display/countries/${countryId}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tv-display"] }),
  });
}


// ── Country detail (banks + rate matrix) ───────────────────

export interface TVDisplayBankRow {
  id: number;
  bank_name: string;
  sort_order: number;
  rates: Record<string, number>;
}

export interface TVDisplayCountryDetailResponse {
  id: number;
  country_code: string;
  country_name: string;
  sort_order: number;
  mt_companies: string[];
  banks: TVDisplayBankRow[];
}

export function useTVDisplayCountryDetail(countryId: number) {
  return useQuery<TVDisplayCountryDetailResponse>({
    queryKey: ["tv-display", "country", countryId],
    queryFn: () =>
      api<TVDisplayCountryDetailResponse>(
        `/api/v2/tv-display/countries/${countryId}`,
      ),
    enabled: countryId > 0,
  });
}
