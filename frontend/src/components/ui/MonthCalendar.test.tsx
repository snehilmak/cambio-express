import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { MonthCalendar } from "./MonthCalendar";

function renderMonth(props: Partial<
  React.ComponentProps<typeof MonthCalendar>
> = {}) {
  return render(
    <MemoryRouter>
      <MonthCalendar
        year={2026}
        month={8}
        dayFor={() => undefined}
        hrefFor={(iso) => `/x?date=${iso}`}
        {...props}
      />
    </MemoryRouter>,
  );
}

describe("MonthCalendar", () => {
  it("renders one cell per day of the month", () => {
    renderMonth();
    // August 2026 has 31 days.
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("31")).toBeInTheDocument();
    expect(screen.queryByText("32")).not.toBeInTheDocument();
  });

  it("handles a month that is not 31 days", () => {
    renderMonth({ year: 2026, month: 2 });
    expect(screen.getByText("28")).toBeInTheDocument();
    expect(screen.queryByText("30")).not.toBeInTheDocument();
  });

  it("includes February 29 in a leap year", () => {
    renderMonth({ year: 2028, month: 2 });
    expect(screen.getByText("29")).toBeInTheDocument();
  });

  it("builds the day's href from the ISO date, not the day number", () => {
    // A one-digit day must still produce a zero-padded ISO date —
    // "2026-08-2" would 422 at the API.
    renderMonth({ hrefFor: (iso) => `/store-book/day?date=${iso}` });
    const link = screen.getByText("2").closest("a");
    expect(link).toHaveAttribute(
      "href", "/store-book/day?date=2026-08-02",
    );
  });

  it("shows the day's figure and variance when supplied", () => {
    renderMonth({
      dayFor: (iso) => iso === "2026-08-02"
        ? { hasData: true, primary: "$1,963", variance: 24.63 }
        : undefined,
    });
    expect(screen.getByText("$1,963")).toBeInTheDocument();
    expect(screen.getByText(/24\.63/)).toBeInTheDocument();
  });

  it("omits the variance pill when the day balanced", () => {
    renderMonth({
      dayFor: () => ({ hasData: true, primary: "$100", variance: 0 }),
    });
    expect(screen.queryByText(/\$0\.00/)).not.toBeInTheDocument();
  });

  it("marks a locked day", () => {
    renderMonth({
      dayFor: (iso) => iso === "2026-08-02"
        ? { hasData: true, locked: true, primary: "$1" }
        : undefined,
    });
    expect(screen.getAllByLabelText("Locked").length).toBe(1);
  });

  it("asks the caller for every day exactly once", () => {
    const dayFor = vi.fn(() => undefined);
    renderMonth({ dayFor });
    expect(dayFor).toHaveBeenCalledTimes(31);
  });
});
