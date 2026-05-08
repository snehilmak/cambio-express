// Billing API hooks. Backed by /api/v2/billing/*.
//
// Two write endpoints — both return a Stripe-hosted URL the SPA
// redirects to. The Stripe webhook (`/webhooks/stripe`) is what
// actually flips the store onto the new plan.

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
