import { describe, it, expect } from "vitest";

import { computeTotals, type FormState } from "./editDailyBook.totals";
import type { DailyReportRow } from "../api/dailybook";

// Regression test for the daily-book totals: `safe_balance` must NOT be
// counted as a disbursement. The server's DailyReport.total_disbursements
// excludes it (safe balance is retained cash that becomes the next day's
// opening forward_balance), so counting it here overstated "Out" and made
// the editor disagree with the calendar/period views.

function makeForm(over: Partial<FormState> = {}): FormState {
  return {
    taxable_sales: 0, non_taxable: 0, sales_tax: 0,
    bill_payment_charge: 0, phone_recargas: 0, boost_mobile: 0,
    money_order: 0, money_order_fees: 0,
    check_cashing_fees: 0, return_check_hold_fees: 0,
    forward_balance: 0, rebates_commissions: 0,
    cash_deposit: 0, safe_balance: 0, payroll_expense: 0,
    over_short: 0, notes: "",
    ...over,
  };
}

function makeReport(over: Partial<DailyReportRow> = {}): DailyReportRow {
  // Only the report-derived fields computeTotals reads matter here; the
  // rest can be zero-filled.
  return {
    money_transfer: 0, from_bank: 0, other_cash_in: 0,
    return_check_paid_back: 0,
    cash_purchases: 0, cash_expense: 0, check_purchases: 0,
    check_expense: 0, outside_cash_drops: 0, checks_deposit: 0,
    other_cash_out: 0,
    ...over,
  } as DailyReportRow;
}

describe("computeTotals", () => {
  it("excludes safe_balance from disbursements", () => {
    const form = makeForm({
      cash_deposit: 100,
      payroll_expense: 50,
      safe_balance: 2000, // retained cash — must not count as Out
    });
    const { disbursements } = computeTotals(form, makeReport());
    // Only cash_deposit + payroll_expense — NOT safe_balance.
    expect(disbursements).toBe(150);
  });

  it("keeps other editable + derived disbursements", () => {
    const form = makeForm({ cash_deposit: 100, payroll_expense: 50 });
    const report = makeReport({ cash_purchases: 30, outside_cash_drops: 20 });
    const { disbursements } = computeTotals(form, report);
    expect(disbursements).toBe(200); // 100 + 50 + 30 + 20
  });

  it("net reflects receipts minus disbursements plus over_short (drawer position)", () => {
    const form = makeForm({
      taxable_sales: 500,
      cash_deposit: 100,
      safe_balance: 999, // still excluded from Out
      over_short: -5,
    });
    const { receipts, disbursements, net } = computeTotals(form, makeReport());
    expect(receipts).toBe(500);
    expect(disbursements).toBe(100);
    expect(net).toBe(395); // 500 - 100 + (-5)
  });
});
