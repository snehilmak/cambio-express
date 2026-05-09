import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";

// Per-store admin endpoints — distinct from `account.ts` (store-info,
// team, passkeys) and `superadmin.ts` (platform-wide). New admin
// Controllers belong here too.

export interface AdminAuditRow {
  ts:           string;
  user_name:    string;
  user_role:    string;
  action:       string;
  target_type:  string;
  target_id:    string;
  target_label: string;
  summary:      string;
  source:       string;
}

export interface AdminAuditUserOption {
  id:    number;
  label: string;
  role:  string;
}

export interface AdminAuditLogResponse {
  rows:           AdminAuditRow[];
  total:          number;
  page:           number;
  per_page:       number;
  total_pages:    number;
  store_users:    AdminAuditUserOption[];
  target_filter:  string;
  action_filter:  string;
  user_filter:    string;
}

export function useAdminAuditLog(
  page: number, target: string, action: string, user: string,
) {
  return useQuery<AdminAuditLogResponse>({
    queryKey: ["admin", "audit-log", page, target, action, user],
    queryFn: () => {
      const p = new URLSearchParams();
      p.set("page", String(page));
      if (target) p.set("target", target);
      if (action) p.set("action", action);
      if (user)   p.set("user", user);
      return api<AdminAuditLogResponse>(
        `/api/v2/admin/audit-log?${p.toString()}`,
      );
    },
  });
}


export interface ReferralRedemptionRow {
  redeemed_at:            string;
  referee_store_id:       number;
  self_credit_applied:    boolean;
  referee_credit_applied: boolean;
  stripe_self_txn_id:     string;
}

export interface ReferralCodeResponse {
  code:                  string;
  is_active:             boolean;
  reward_self_cents:     number;
  reward_referee_cents:  number;
  redeemed_count:        number;
  credits_earned_cents:  number;
  share_url:             string;
  redemptions:           ReferralRedemptionRow[];
}

export function useReferralCode() {
  return useQuery<ReferralCodeResponse>({
    queryKey: ["admin", "referrals"],
    queryFn: () => api<ReferralCodeResponse>("/api/v2/admin/referrals"),
  });
}
