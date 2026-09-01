import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PeriodRollup } from "./PeriodRollup";
import type {
  PurchasesBlock, SalesBlock, TransfersRollup,
} from "../api/dashboard";

const sales: SalesBlock = {
  today: 100, yesterday: 90, month_to_date: 3000,
  d7: 700, d15: 1500, d30: 3000, trend: [], hourly: null,
};
const purchases: PurchasesBlock = {
  today: 10, d7: 70, d15: 150, d30: 300,
  open_count: 0, open_total: 0,
};
const transfers: TransfersRollup = {
  today: 5, d7: 35, d15: 75, d30: 150,
};

describe("PeriodRollup", () => {
  it("shows one column per module that is on", () => {
    render(
      <PeriodRollup
        sales={sales} purchases={purchases} transfers={transfers}
      />,
    );
    for (const h of ["Sales", "Purchases", "Transfers"]) {
      expect(screen.getByRole("columnheader", { name: h }))
        .toBeInTheDocument();
    }
    for (const w of ["Last 24 hrs", "7 days", "15 days", "30 days"]) {
      expect(screen.getByText(w)).toBeInTheDocument();
    }
  });

  it("omits a column whose module is off", () => {
    // A c-store with no money services must not see an empty
    // Transfers column full of $0.00.
    render(
      <PeriodRollup
        sales={sales} purchases={purchases} transfers={null}
      />,
    );
    expect(
      screen.queryByRole("columnheader", { name: "Transfers" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: "Sales" }),
    ).toBeInTheDocument();
  });

  it("renders nothing at all when no module qualifies", () => {
    const { container } = render(
      <PeriodRollup sales={null} purchases={null} transfers={null} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("puts each window's figure in its own row", () => {
    render(
      <PeriodRollup sales={sales} purchases={null} transfers={null} />,
    );
    expect(screen.getByText("$700.00")).toBeInTheDocument();
    expect(screen.getByText("$1,500.00")).toBeInTheDocument();
  });
});
