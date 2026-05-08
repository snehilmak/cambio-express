// Reports API hooks. Backed by /api/v2/reports/* — every endpoint
// shares the same `(period, store_ids)` query shape and returns
// `{rows, totals}` envelopes. We expose a single hook factory that
// the routes use to keep the wiring consistent.

import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";

export interface AggregatedTotals {
  count: number;
  sent: number;
  fees: number;
  tax: number;
}

export interface AggregatedRowBase {
  count: number;
  sent: number;
  fees: number;
  tax: number;
  avg: number;
}

// Each report adds its own identity column on top of the
// AggregatedRowBase numeric envelope.
export interface CompanyRow      extends AggregatedRowBase { company: string; }
export interface ServiceTypeRow  extends AggregatedRowBase { service_type: string; }
export interface CountryRow      extends AggregatedRowBase { country: string; }
export interface RecipientRow    extends AggregatedRowBase { recipient: string; }

export interface ReportEnvelope<R> {
  rows: R[];
  totals: AggregatedTotals;
}

interface PeriodQuery {
  // Both YYYY-MM-DD. The hook is disabled until both are set
  // (avoids a 422 from the backend).
  from?: string;
  to?: string;
}

function useReport<R>(slug: string, p: PeriodQuery) {
  const identity = getCurrentIdentity();
  const storeId = identity?.store_id;
  const ready =
    storeId !== null &&
    storeId !== undefined &&
    Boolean(p.from) &&
    Boolean(p.to);

  return useQuery<ReportEnvelope<R>>({
    enabled: ready,
    queryKey: ["reports", slug, storeId, p.from, p.to],
    queryFn: async () => {
      const params = new URLSearchParams({
        store_ids: String(storeId),
        from: p.from!,
        to: p.to!,
      });
      return api<ReportEnvelope<R>>(
        `/api/v2/reports/${slug}?${params.toString()}`,
      );
    },
  });
}

export const useSalesByCompany = (p: PeriodQuery) =>
  useReport<CompanyRow>("sales-by-company", p);

export const useSalesByService = (p: PeriodQuery) =>
  useReport<ServiceTypeRow>("sales-by-service", p);

export const useByDestinationCountry = (p: PeriodQuery) =>
  useReport<CountryRow>("by-destination-country", p);

export const useTopRecipients = (p: PeriodQuery) =>
  useReport<RecipientRow>("top-recipients", p);
