import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";

// Per-store admin endpoints — distinct from `account.ts` (store-info,
// team, passkeys) and `superadmin.ts` (platform-wide). Today: the
// merged operator audit log. New admin Controllers belong here too.

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
