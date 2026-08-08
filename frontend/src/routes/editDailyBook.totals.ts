// Pure helpers extracted from EditDailyBook.tsx so the route file can
// export only its component (the `react-refresh/only-export-components`
// lint rule). `computeTotals` is unit-tested in
// EditDailyBook.totals.test.tsx.
import type { DailyReportRow } from "../api/dailybook";

export interface FormState {
  taxable_sales: number;
  non_taxable: number;
  sales_tax: number;
  bill_payment_charge: number;
  phone_recargas: number;
  boost_mobile: number;
  money_order: number;
  money_order_fees: number;
  check_cashing_fees: number;
  return_check_hold_fees: number;
  forward_balance: number;
  rebates_commissions: number;
  cash_deposit: number;
  safe_balance: number;
  payroll_expense: number;
  over_short: number;
  notes: string;
}

export function computeTotals(
  form: FormState | null,
  report: DailyReportRow | null | undefined,
) {
  const receiptsEditable = form ? (
    form.taxable_sales + form.non_taxable + form.sales_tax +
    form.bill_payment_charge + form.phone_recargas + form.boost_mobile +
    form.money_order + form.money_order_fees +
    form.check_cashing_fees + form.return_check_hold_fees +
    form.forward_balance + form.rebates_commissions
  ) : 0;
  // `money_transfer` is Category-3 (derived from the mt_summary
  // per-company breakdown, mirrored onto the report). It is NOT an
  // editable form field — reading it from the report row is what
  // keeps Money In in sync with the saved breakdown instead of an
  // unpersisted input.
  const receiptsDerived =
    (report?.money_transfer ?? 0) + (report?.from_bank ?? 0) +
    (report?.other_cash_in ?? 0) + (report?.return_check_paid_back ?? 0);
  const receipts = receiptsEditable + receiptsDerived;

  // NOTE: `safe_balance` is deliberately NOT summed here. The server's
  // DailyReport.total_disbursements excludes it (see
  // api/Modules/DailyBook/INVARIANTS.md) because safe balance is cash
  // RETAINED overnight — it becomes the next day's opening
  // `forward_balance` (carry = prior.outside_cash_drops +
  // prior.safe_balance). Counting it as a disbursement here overstated
  // "Out" and understated the day's position, so the editor disagreed
  // with the calendar/period views (which use the server's net).
  const disbursementsEditable = form ? (
    form.cash_deposit + form.payroll_expense
  ) : 0;
  const disbursementsDerived =
    (report?.cash_purchases ?? 0) + (report?.cash_expense ?? 0) +
    (report?.check_purchases ?? 0) + (report?.check_expense ?? 0) +
    (report?.outside_cash_drops ?? 0) + (report?.checks_deposit ?? 0) +
    (report?.other_cash_out ?? 0);
  const disbursements = disbursementsEditable + disbursementsDerived;

  const overShort = form?.over_short ?? 0;
  const net = receipts - disbursements + overShort;
  return { receipts, disbursements, net };
}
