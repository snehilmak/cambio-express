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
    money_order_fees: 0,
    check_cashing_fees: 0, return_check_hold_fees: 0,
    forward_balance: 0,
  forward_balance_override: null, rebates_commissions: 0,
    cash_deposit: 0, safe_balance: 0,
    notes: "",
    ...over,
  };
}

function makeReport(over: Partial<DailyReportRow> = {}): DailyReportRow {
  // Only the report-derived fields computeTotals reads matter here; the
  // rest can be zero-filled.
  return {
    money_transfer: 0, money_order: 0, from_bank: 0, other_cash_in: 0,
    payroll_expense: 0, payroll_check: 0,
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
      safe_balance: 2000, // retained cash — must not count as Out
    });
    const { disbursements } = computeTotals(
      form, makeReport({ payroll_expense: 50 }),
    );
    // cash_deposit + report payroll — NOT safe_balance.
    expect(disbursements).toBe(150);
  });

  it("keeps other editable + derived disbursements", () => {
    const form = makeForm({ cash_deposit: 100 });
    const report = makeReport({
      payroll_expense: 50, cash_purchases: 30, outside_cash_drops: 20,
    });
    const { disbursements } = computeTotals(form, report);
    expect(disbursements).toBe(200); // 100 + 50 + 30 + 20
  });

  it("net is receipts minus disbursements (over_short is NOT folded in)", () => {
    const form = makeForm({
      taxable_sales: 500,
      cash_deposit: 100,
      safe_balance: 999, // still excluded from Out
    });
    const { receipts, disbursements, net } = computeTotals(form, makeReport());
    expect(receipts).toBe(500);
    expect(disbursements).toBe(100);
    expect(net).toBe(400); // 500 - 100 — matches the server's net
  });

  it("overShort is the cash reconciliation: out + safe - in, checks excluded", () => {
    // Balanced day: opened with 1000, kept 1000 in the safe, nothing
    // else → over_short 0.
    const balanced = computeTotals(
      makeForm({ forward_balance: 1000, safe_balance: 1000 }),
      makeReport(),
    );
    expect(balanced.overShort).toBe(0);

    // Check purchases/expenses are non-cash → they must cancel out of
    // the reconciliation (they're in disbursements, backed out here).
    const withChecks = computeTotals(
      makeForm({ forward_balance: 1000, safe_balance: 1000 }),
      makeReport({ check_purchases: 250, check_expense: 75 }),
    );
    expect(withChecks.overShort).toBe(0);

    // Opened with 1000, kept nothing, paid nothing → the books say
    // 1000 vanished: SHORT (negative).
    const short = computeTotals(
      makeForm({ forward_balance: 1000, safe_balance: 0 }),
      makeReport(),
    );
    expect(short.overShort).toBe(-1000);
  });
});


describe("money_order as a derived receipt", () => {
  it("reads money_order off the report row, not the form", () => {
    const { receipts } = computeTotals(
      makeForm(),
      makeReport({ money_order: 125 }),
    );
    expect(receipts).toBe(125);
  });
});
