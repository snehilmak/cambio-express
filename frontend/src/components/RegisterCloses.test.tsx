import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import RegisterCloses from "./RegisterCloses";
import { ToastProvider } from "./ui";

// The section reads through the dayclose hooks; stub them so the
// test is about what the section renders, not about fetching.
const summary = {
  date: "2026-08-31",
  closes: [
    {
      id: 1,
      register_label: "Register 1",
      shift_label: "Morning",
      gross_sales: 1234.5,
      sales_tax: 98.76,
      cash_total: 800,
      card_total: 533.26,
      other_total: 0,
      cash_counted: 795,
      over_short: -5,
      tender_variance: 0,
      notes: "",
      source: "manual",
      department_sales: [],
    },
  ],
  department_totals: [
    { department_id: 7, department_name: "Tobacco", amount: 410.25 },
  ],
  gross_sales: 1234.5,
  sales_tax: 98.76,
  cash_total: 800,
  card_total: 533.26,
  other_total: 0,
  over_short: -5,
  tender_variance: 0,
  uncounted_drawers: 0,
};

vi.mock("../api/dayclose", () => ({
  useDayClose: () => ({ data: summary, isLoading: false, isError: false }),
  useDepartments: () => ({ data: { departments: [] } }),
  upsertRegisterClose: vi.fn(),
  deleteRegisterClose: vi.fn(),
}));

function renderSection(canEdit: boolean) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ToastProvider>
          <RegisterCloses day="2026-08-31" canEdit={canEdit} />
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("RegisterCloses", () => {
  it("renders the day's closes and the department rollup", () => {
    renderSection(true);
    expect(screen.getByText("Register 1 / Morning")).toBeInTheDocument();
    expect(screen.getByText("Tobacco")).toBeInTheDocument();
    expect(screen.getByText("$410.25")).toBeInTheDocument();
  });

  it("offers editing controls when the day is unlocked", () => {
    renderSection(true);
    expect(screen.getByText("+ Add close")).toBeInTheDocument();
    // RowActions renders "Actions" itself, so pin the assertion to
    // the column header rather than any element carrying the word.
    expect(
      screen.getByRole("columnheader", { name: "Actions" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Edit")).toBeInTheDocument();
  });

  it("hides every write control when the day is locked", () => {
    // A locked sheet shows its register detail read-only — the same
    // rule the money fields above it follow.
    renderSection(false);
    expect(screen.queryByText("+ Add close")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("columnheader", { name: "Actions" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Edit")).not.toBeInTheDocument();
    expect(screen.queryByText("Delete")).not.toBeInTheDocument();
    // …but the numbers are still there to read.
    expect(screen.getByText("Register 1 / Morning")).toBeInTheDocument();
  });
});
