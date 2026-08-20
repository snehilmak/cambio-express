import { describe, it, expect } from "vitest";

import { filterNavForRole, sectionSlug } from "./navConfig";

describe("sectionSlug", () => {
  it("lowercases and hyphenates", () => {
    expect(sectionSlug("Daily")).toBe("daily");
    expect(sectionSlug("Sub Department")).toBe("sub-department");
  });

  it("strips leading/trailing separators and collapses runs", () => {
    expect(sectionSlug("  Reports & P&L  ")).toBe("reports-p-l");
  });
});

describe("filterNavForRole → section-hub resolution", () => {
  // The /hub/:key route resolves a section by matching sectionSlug on
  // the current role's filtered groups. That only works if the slugs
  // are unique per role — this is the guard against a future rename
  // that collides two sections and makes a hub ambiguous.
  for (const role of ["admin", "employee", "owner", "superadmin"]) {
    it(`produces unique section slugs for ${role}`, () => {
      const groups = filterNavForRole(role, []);
      const slugs = groups.map((g) => sectionSlug(g.title));
      expect(new Set(slugs).size).toBe(slugs.length);
    });

    it(`drops empty groups for ${role} (no blank hubs)`, () => {
      const groups = filterNavForRole(role, []);
      // Every surviving group is either a real menu (has items) or a
      // direct-link group (has `to`, e.g. Reports → Report Center).
      // What we never want is a group with neither — a blank hub.
      for (const g of groups) {
        expect(g.items.length > 0 || !!g.to).toBe(true);
      }
    });
  }

  it("admin Reports is a direct link to the Report Center (no submenu)", () => {
    const groups = filterNavForRole("admin", ["reports.read"]);
    const reports = groups.find((g) => g.title === "Reports");
    expect(reports).toBeDefined();
    expect(reports!.to).toBe("/reports");
    expect(reports!.items).toHaveLength(0);
  });

  it("admin can resolve the Daily hub to its destinations", () => {
    // Admin has every Daily permission by default in this context
    // (perms filter is role==='superadmin' OR listed) — pass the
    // perms the Daily items require so the group resolves fully.
    const perms = [
      "transfers.read", "customers.read",
      "daily_book.read", "return_checks.read",
    ];
    const groups = filterNavForRole("admin", perms);
    const daily = groups.find((g) => sectionSlug(g.title) === "daily");
    expect(daily).toBeDefined();
    const labels = daily!.items.map((i) => i.label);
    expect(labels).toContain("Dashboard");
    expect(labels).toContain("Returned checks");
  });
});
