// Return-checks API hooks. Backed by /api/v2/return-checks.

import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";

export interface ReturnCheckRow {
  id: number;
  bounced_on: string;
  customer_name: string;
  check_number: string;
  payer_bank: string;
  amount: number;
  status: string;
  status_changed_on: string;
  notes: string;
  recovered_total: number;
  payment_count: number;
}

export function useReturnChecks(status: string = "") {
  const identity = getCurrentIdentity();
  return useQuery<{ rows: ReturnCheckRow[] }>({
    enabled: identity?.store_id != null,
    queryKey: ["return-checks", "list", identity?.store_id, status],
    queryFn: () => {
      const qs = status ? `?status=${encodeURIComponent(status)}` : "";
      return api<{ rows: ReturnCheckRow[] }>(
        `/api/v2/return-checks${qs}`,
      );
    },
  });
}

export function useReturnCheck(rcId: number | undefined) {
  const identity = getCurrentIdentity();
  return useQuery<{ return_check: ReturnCheckRow }>({
    enabled:
      Number.isFinite(rcId) && identity?.store_id != null,
    queryKey: ["return-checks", "detail", identity?.store_id, rcId],
    queryFn: () =>
      api<{ return_check: ReturnCheckRow }>(
        `/api/v2/return-checks/${rcId}`,
      ),
  });
}

export interface ReturnCheckWriteBody {
  bounced_on: string;
  customer_name: string;
  check_number?: string;
  payer_bank?: string;
  amount: number;
  notes?: string;
}

export async function createReturnCheck(
  body: ReturnCheckWriteBody,
): Promise<{ return_check: ReturnCheckRow }> {
  return api<{ return_check: ReturnCheckRow }>(
    "/api/v2/return-checks",
    { method: "POST", json: body },
  );
}

export async function updateReturnCheck(
  rcId: number, body: ReturnCheckWriteBody,
): Promise<{ return_check: ReturnCheckRow }> {
  return api<{ return_check: ReturnCheckRow }>(
    `/api/v2/return-checks/${rcId}`,
    { method: "PUT", json: body },
  );
}

export async function markLoss(
  rcId: number,
): Promise<{ return_check: ReturnCheckRow }> {
  return api<{ return_check: ReturnCheckRow }>(
    `/api/v2/return-checks/${rcId}/mark-loss`,
    { method: "POST", json: {} },
  );
}

export async function markFraud(
  rcId: number,
): Promise<{ return_check: ReturnCheckRow }> {
  return api<{ return_check: ReturnCheckRow }>(
    `/api/v2/return-checks/${rcId}/mark-fraud`,
    { method: "POST", json: {} },
  );
}

export async function reopenReturnCheck(
  rcId: number,
): Promise<{ return_check: ReturnCheckRow }> {
  return api<{ return_check: ReturnCheckRow }>(
    `/api/v2/return-checks/${rcId}/reopen`,
    { method: "POST", json: {} },
  );
}

export interface ReturnCheckPaymentRow {
  id: number;
  return_check_id: number;
  amount: number;
  paid_on: string;
  method: string;
  notes: string;
}

export function useReturnCheckPayments(rcId: number | undefined) {
  const identity = getCurrentIdentity();
  return useQuery<{ payments: ReturnCheckPaymentRow[] }>({
    enabled:
      Number.isFinite(rcId) && identity?.store_id != null,
    queryKey: ["return-checks", "payments", identity?.store_id, rcId],
    queryFn: () =>
      api<{ payments: ReturnCheckPaymentRow[] }>(
        `/api/v2/return-checks/${rcId}/payments`,
      ),
  });
}
