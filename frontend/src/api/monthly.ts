// Monthly P&L API hooks. Backed by /api/v2/monthly.

import { useQuery } from "@tanstack/react-query";

import { api, ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";

export interface MonthlyRow {
  id: number;
  store_id: number;
  year: number;
  month: number;
  taxable_sales: number;
  non_taxable: number;
  bill_payment_charge: number;
  phone_recargas: number;
  boost_mobile: number;
  check_cashing_fees: number;
  return_check_hold_fees: number;
  rebates_commissions: number;
  mt_commission_in_bank: number;
  other_income_1: number;
  other_income_2: number;
  other_income_3: number;
  cash_purchases: number;
  check_purchases: number;
  cash_expenses: number;
  check_expenses: number;
  cash_payroll: number;
  bank_charges_total: number;
  credit_card_fees: number;
  money_order_rent: number;
  emaginenet_tech: number;
  irs_payroll_tax: number;
  texas_workforce: number;
  other_taxes: number;
  accounting_charges: number;
  return_check_gl: number;
  other_expense_1: number;
  other_expense_2: number;
  other_expense_3: number;
  other_expense_4: number;
  other_expense_5: number;
  over_short: number;
  borrowed_money_return: number;
  profit_distributed: number;
  cash_carry_forward: number;
  notes: string;
  total_income: number;
  total_expenses: number;
  net_profit: number;
}

export function useMonthly(year: number | undefined, month: number | undefined) {
  const identity = getCurrentIdentity();
  const enabled =
    identity?.store_id != null &&
    Number.isFinite(year) &&
    Number.isFinite(month);
  return useQuery<MonthlyRow | null>({
    enabled,
    queryKey: ["monthly", "report", identity?.store_id, year, month],
    queryFn: async () => {
      try {
        const resp = await api<{ report: MonthlyRow }>(
          `/api/v2/monthly/${year}/${month}`,
        );
        return resp.report;
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return null;
        throw err;
      }
    },
  });
}

export interface MonthLogged {
  year: number;
  month: number;
}

export function useLoggedMonths() {
  const identity = getCurrentIdentity();
  return useQuery<{ months: MonthLogged[] }>({
    enabled: identity?.store_id != null,
    queryKey: ["monthly", "months", identity?.store_id],
    queryFn: () => api<{ months: MonthLogged[] }>(`/api/v2/monthly/months`),
    staleTime: 60_000,
  });
}
