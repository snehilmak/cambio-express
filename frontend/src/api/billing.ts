// Billing API hooks. Backed by /api/v2/billing/*.
//
// Two write endpoints — both return a Stripe-hosted URL the SPA
// redirects to. The Stripe webhook (`/webhooks/stripe`) is what
// actually flips the store onto the new plan.

import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";

export interface CheckoutResponse {
  url: string;
}

export interface PortalResponse {
  url: string;
}

export async function startCheckout(plan: string): Promise<CheckoutResponse> {
  return api<CheckoutResponse>("/api/v2/billing/checkout", {
    method: "POST",
    json: { plan },
  });
}

export async function openBillingPortal(): Promise<PortalResponse> {
  return api<PortalResponse>("/api/v2/billing/portal", {
    method: "POST",
    json: {},
  });
}

export interface SubscriptionStore {
  id: number;
  name: string | null;
  email: string | null;
  plan: string | null;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
  data_retention_until: string | null;
}

export interface SubscriptionAddon {
  key: string;
  name: string;
  price_label: string;
  tagline: string;
  description: string;
  status: string;
  is_active: boolean;
}

export interface SubscriptionSummary {
  store: SubscriptionStore;
  plan_label: string;
  plan_price: string;
  has_paid_plan: boolean;
  trial_status: string | null;
  trial_days_left: number | null;
  retention_days_left: number | null;
  retention_total_days: number;
  addons: SubscriptionAddon[];
  active_addon_count: number;
  cancel_at_period_end: boolean;
  cancel_at: string | null;
  referral_code: string | null;
}

export async function fetchSubscriptionSummary(): Promise<SubscriptionSummary> {
  return api<SubscriptionSummary>("/api/v2/admin/subscription");
}

export interface AddonToggleResponse {
  is_active: boolean;
}

export async function toggleAddon(
  addonKey: string,
): Promise<AddonToggleResponse> {
  return api<AddonToggleResponse>(
    `/api/v2/admin/addons/${encodeURIComponent(addonKey)}/toggle`,
    { method: "POST", json: {} },
  );
}


// ── Public pricing (W-1) ────────────────────────────────────
//
// The landing page renders before anyone has an account, so this is
// unauthenticated. It reads PLAN_CATALOG server-side rather than
// letting the marketing page keep its own copy of the prices — it
// had one and it drifted, advertising Pro yearly at $420 while
// checkout charged $450.

export interface PublicPlan {
  key: string;
  label: string;
  monthly_cents: number;
  yearly_cents: number;
  /** Whole months of the monthly price the yearly price saves. */
  months_free: number;
}

export function usePublicPricing() {
  return useQuery<{ plans: PublicPlan[] }>({
    queryKey: ["billing", "public-pricing"],
    queryFn: () => api<{ plans: PublicPlan[] }>("/api/v2/billing/pricing"),
    // Prices change about never; don't refetch on every mount.
    staleTime: 60 * 60 * 1000,
  });
}
