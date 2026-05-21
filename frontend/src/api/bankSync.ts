// Bank-sync API hooks. Backed by /api/v2/bank/{transactions,accounts,rules}.
//
// Read-only for SPA-29 — connect/disconnect/sync flows still
// live on the legacy Flask /bank routes (Stripe Financial
// Connections session needs Stripe.js to drive the modal).

import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";

export interface BankAccountRow {
  id: number;
  institution_name: string;
  display_name: string;
  nickname: string;
  last4: string;
  label: string;
  category: string;
  subcategory: string;
  currency: string;
  last_balance_cents: number;
  last_balance: number;
  last_balance_as_of: string;
  enabled: boolean;
  connected_at: string;
  disconnected_at: string;
}

export interface BankRuleRow {
  id: number;
  enabled: boolean;
  priority: number;
  desc_match_type: string;
  desc_match_value: string;
  sign_filter: string;
  amount_min_cents: number | null;
  amount_max_cents: number | null;
  account_filter_id: number | null;
  account_filter_label: string;
  target_kind: string;
  auto_post: boolean;
  description: string;
  match_count: number;
  last_matched_at: string;
}

export interface BankTransactionRow {
  id: number;
  posted_at: string;
  description: string;
  amount_cents: number;
  amount: number;
  currency: string;
  status: string;
  category_slug: string;
  account_id: number;
  account_label: string;
}

export interface BankTransactionListResponse {
  rows: BankTransactionRow[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
  page_total_cents: number;
  uncategorized_count: number;
}

export interface BankTransactionFilters {
  posted_from?: string;
  posted_to?: string;
  account_id?: string;
  category_slug?: string;
  sign?: "" | "credit" | "debit";
  q?: string;
  uncategorized_only?: boolean;
  page?: number;
  per_page?: number;
}

export function useBankAccounts() {
  const identity = getCurrentIdentity();
  return useQuery<{ rows: BankAccountRow[]; total: number }>({
    enabled: identity?.store_id != null,
    queryKey: ["bank", "accounts", identity?.store_id],
    queryFn: () =>
      api<{ rows: BankAccountRow[]; total: number }>("/api/v2/bank/accounts"),
  });
}

export function useBankRules(enabledOnly = false) {
  const identity = getCurrentIdentity();
  return useQuery<{ rows: BankRuleRow[]; total: number }>({
    enabled: identity?.store_id != null,
    queryKey: ["bank", "rules", identity?.store_id, enabledOnly],
    queryFn: () => {
      const qs = enabledOnly ? "?enabled_only=true" : "";
      return api<{ rows: BankRuleRow[]; total: number }>(
        `/api/v2/bank/rules${qs}`,
      );
    },
  });
}

export function useBankTransactions(filters: BankTransactionFilters) {
  const identity = getCurrentIdentity();
  return useQuery<BankTransactionListResponse>({
    enabled: identity?.store_id != null,
    queryKey: ["bank", "transactions", identity?.store_id, filters],
    queryFn: () => {
      const p = new URLSearchParams();
      if (filters.posted_from)        p.set("posted_from",   filters.posted_from);
      if (filters.posted_to)          p.set("posted_to",     filters.posted_to);
      if (filters.account_id)         p.set("account_id",    filters.account_id);
      if (filters.category_slug)      p.set("category_slug", filters.category_slug);
      if (filters.sign)               p.set("sign",          filters.sign);
      if (filters.q)                  p.set("q",             filters.q);
      if (filters.uncategorized_only) p.set("uncategorized_only", "true");
      if (filters.page)               p.set("page",     String(filters.page));
      if (filters.per_page)           p.set("per_page", String(filters.per_page));
      const qs = p.toString();
      return api<BankTransactionListResponse>(
        `/api/v2/bank/transactions${qs ? `?${qs}` : ""}`,
      );
    },
    placeholderData: (prev) => prev,
  });
}


// Categories the operator can pick from when tagging a row. Mirrors
// the legacy `/bank/transactions` template's dropdown — the slug is
// what we POST, the label is what we render.
export const BANK_CATEGORY_OPTIONS: Array<{ slug: string; label: string }> = [
  { slug: "bank_charge_210",  label: "Bank charge — ••0210" },
  { slug: "bank_charge_230",  label: "Bank charge — ••0230" },
  { slug: "cash_deposit",     label: "Cash deposit"          },
  { slug: "cash_expense",     label: "Cash expense"          },
  { slug: "check_expense",    label: "Check expense"         },
  { slug: "check_deposit",    label: "Check deposit"         },
  { slug: "ach_deposit",      label: "ACH deposit"           },
  { slug: "ach_withdrawal",   label: "ACH withdrawal"        },
];

export interface CategorizeBody {
  target_kind: string;
  post_to_daily?: boolean;
}

export async function categorizeTransaction(
  txnId: number, body: CategorizeBody,
): Promise<{ transaction: BankTransactionRow }> {
  return api<{ transaction: BankTransactionRow }>(
    `/api/v2/bank/transactions/${txnId}/categorize`,
    { method: "POST", json: body },
  );
}

export async function uncategorizeTransaction(
  txnId: number,
): Promise<{ transaction: BankTransactionRow }> {
  return api<{ transaction: BankTransactionRow }>(
    `/api/v2/bank/transactions/${txnId}/uncategorize`,
    { method: "POST", json: {} },
  );
}


// ── Rule CRUD ──────────────────────────────────────────────

export interface BankRuleWriteBody {
  enabled: boolean;
  priority: number;
  desc_match_type: string;
  desc_match_value: string;
  sign_filter: string;
  amount_min_cents: number | null;
  amount_max_cents: number | null;
  account_filter_id: number | null;
  target_kind: string;
  auto_post: boolean;
  description: string;
}

export async function createRule(
  body: BankRuleWriteBody,
): Promise<{ rule: BankRuleRow }> {
  return api<{ rule: BankRuleRow }>("/api/v2/bank/rules", {
    method: "POST",
    json: body,
  });
}

export async function updateRule(
  ruleId: number, body: BankRuleWriteBody,
): Promise<{ rule: BankRuleRow }> {
  return api<{ rule: BankRuleRow }>(`/api/v2/bank/rules/${ruleId}`, {
    method: "PUT",
    json: body,
  });
}

export async function toggleRule(
  ruleId: number, enabled: boolean,
): Promise<{ rule: BankRuleRow }> {
  return api<{ rule: BankRuleRow }>(
    `/api/v2/bank/rules/${ruleId}/toggle`,
    { method: "POST", json: { enabled } },
  );
}

export async function deleteRule(ruleId: number): Promise<void> {
  await api<void>(`/api/v2/bank/rules/${ruleId}`, { method: "DELETE" });
}


// ── Stripe FC connect lifecycle ────────────────────────────
//
// 5 endpoints under /api/v2/bank/* drive the Stripe Financial
// Connections flow.  All admin-role gated; all audited.
//
//   POST /api/v2/bank/connect            — mint a new FC session
//   POST /api/v2/bank/connect/complete   — persist the linked
//                                          accounts (after Stripe.js)
//   POST /api/v2/bank/disconnect/{id}    — soft-disconnect an account
//   POST /api/v2/bank/refresh            — manual balance refresh
//   POST /api/v2/bank/sync-transactions  — pull recent txns
//
// Replaces the legacy /bank/stripe/* Flask form-POST endpoints
// that went away in PR #550.

export interface BankConnectResponse {
  clientSecret: string;
  sessionId: string;
  publishableKey: string;
}

export interface BankConnectCompleteResponse {
  accounts_added: number;
  accounts_total: number;
}

export interface BankRefreshResponse {
  accounts_refreshed: number;
  error: string;
}

export interface BankSyncTransactionsResponse {
  new_rows: number;
  total_seen: number;
  error: string;
}

export async function startStripeConnect(): Promise<BankConnectResponse> {
  return api<BankConnectResponse>("/api/v2/bank/connect", {
    method: "POST",
    json: {},
  });
}

export async function completeStripeConnect(
  sessionId: string,
): Promise<BankConnectCompleteResponse> {
  return api<BankConnectCompleteResponse>(
    "/api/v2/bank/connect/complete",
    { method: "POST", json: { sessionId } },
  );
}

export async function disconnectBankAccount(
  accountId: number,
): Promise<void> {
  await api<void>(
    `/api/v2/bank/disconnect/${accountId}`,
    { method: "POST", json: {} },
  );
}

export async function refreshBankBalances(): Promise<BankRefreshResponse> {
  return api<BankRefreshResponse>(
    "/api/v2/bank/refresh",
    { method: "POST", json: {} },
  );
}

export async function syncBankTransactions(): Promise<BankSyncTransactionsResponse> {
  return api<BankSyncTransactionsResponse>(
    "/api/v2/bank/sync-transactions",
    { method: "POST", json: {} },
  );
}

export async function setBankAccountNickname(
  accountId: number, nickname: string,
): Promise<BankAccountRow> {
  return api<BankAccountRow>(
    `/api/v2/bank/accounts/${accountId}/nickname`,
    { method: "PUT", json: { nickname } },
  );
}
