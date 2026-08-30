import { describe, expect, it } from "vitest";

import { formatDate } from "./datetime";
import { fmtMoney2 } from "./formatters";

describe("formatDate", () => {
  it("renders a bare YYYY-MM-DD as that calendar day (no tz shift)", () => {
    // The C-3 regression this guards: parsing "2026-08-30" as UTC
    // midnight and converting to a US timezone displayed Aug 29.
    expect(formatDate("2026-08-30")).toContain("Aug");
    expect(formatDate("2026-08-30")).toContain("30");
    expect(formatDate("2026-01-01")).toContain("1");
    expect(formatDate("2026-01-01")).not.toContain("Dec");
  });

  it("formats a full timestamp as a date", () => {
    const out = formatDate("2026-05-09T17:42:00Z");
    expect(out).toContain("2026");
    expect(out).toContain("May");
  });

  it("handles empty and garbage input defensively", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate(undefined)).toBe("—");
    expect(formatDate("")).toBe("—");
    expect(formatDate("not-a-date")).toBe("not-a-date");
  });
});

describe("fmtMoney2", () => {
  it("keeps thousands separators (the toFixed(2) bypass lost them)", () => {
    expect(fmtMoney2(12345.67)).toBe("$12,345.67");
    expect(fmtMoney2(0)).toBe("$0.00");
    expect(fmtMoney2(null)).toBe("$0.00");
  });
});
