import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import TransactionDetail from "./TransactionDetail";

// A ticket where the cashier voided a $500 item and then rang a
// $12 one. The void must be VISIBLE (that is the point of the
// page) and must not appear in any total (that is the trap).
const detail = {
  transaction: {
    id: 42,
    business_date: "2025-12-08",
    source_file: "PJR340251209133139277539.xml",
    kind: "sale",
    register_id: "1",
    cashier_id: "3",
    till_id: "0318",
    transaction_no: "8946",
    event_sequence_id: "7",
    started_at: null,
    ended_at: null,
    receipt_at: null,
    outside: false,
    training_mode: false,
    offline: false,
    suspended: false,
    gross: 12,
    net: 12,
    tax: 0,
    grand_total: 12,
    has_voided_line: true,
    lines: [
      {
        line_seq: 1,
        status: "cancel",
        pos_code: "111111111111",
        description: "VOIDED PREMIUM ITEM",
        entry_method: "scan",
        merchandise_code: "10",
        quantity: 1,
        amount: 500,
        actual_price: 500,
        regular_price: 500,
        is_fuel: false,
        fuel_grade_id: "",
        fuel_position: "",
        gallons: 0,
      },
      {
        line_seq: 2,
        status: "normal",
        pos_code: "222222222222",
        description: "COFFEE LARGE",
        entry_method: "scan",
        merchandise_code: "10",
        quantity: 1,
        amount: 12,
        actual_price: 12,
        regular_price: 12,
        is_fuel: false,
        fuel_grade_id: "",
        fuel_position: "",
        gallons: 0,
      },
    ],
    tenders: [
      {
        code: "cash", sub_code: "generic", amount: 12,
        is_change: false, status: "normal",
      },
    ],
  },
};

vi.mock("../api/posimport", () => ({
  useTransaction: () => ({
    data: detail, isLoading: false, isError: false,
  }),
}));

function renderDetail() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <MemoryRouter initialEntries={["/transactions/42"]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/transactions/:id" element={<TransactionDetail />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("TransactionDetail", () => {
  it("shows the voided line rather than hiding it", () => {
    renderDetail();
    expect(screen.getByText("VOIDED PREMIUM ITEM")).toBeInTheDocument();
    // Price and amount columns both carry it.
    expect(screen.getAllByText("$500.00").length).toBe(2);
    expect(screen.getByText("voided")).toBeInTheDocument();
  });

  it("keeps the voided amount out of every total", () => {
    renderDetail();
    // Items subtotal and ticket total are both $12 — the $500 void
    // contributes to neither. If a regression summed cancelled
    // lines this would read $512.
    expect(screen.getAllByText("$12.00").length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText("$512.00")).not.toBeInTheDocument();
  });

  it("says plainly that a void is excluded", () => {
    renderDetail();
    expect(
      screen.getByText(/One item was voided on this ticket/),
    ).toBeInTheDocument();
  });

  it("shows the register provenance", () => {
    renderDetail();
    expect(screen.getByText("Till")).toBeInTheDocument();
    expect(screen.getByText("0318")).toBeInTheDocument();
    expect(
      screen.getByText("PJR340251209133139277539.xml"),
    ).toBeInTheDocument();
  });
});
