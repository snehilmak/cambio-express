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

  it("admin Reports is a fly-out with the two separate centers", () => {
    const groups = filterNavForRole(
      "admin", ["reports.read"], ["module_day_close"],
    );
    const reports = groups.find((g) => g.title === "Reports");
    expect(reports).toBeDefined();
    expect(reports!.to).toBeUndefined();
    expect(reports!.items.map((i) => i.label))
      .toEqual(["MSB Reports", "Store Reports"]);
    // Store Reports is flag-gated — an MSB-profile store (no
    // module_day_close) sees only the MSB center.
    const msbOnly = filterNavForRole("admin", ["reports.read"], [])
      .find((g) => g.title === "Reports");
    expect(msbOnly!.items.map((i) => i.label)).toEqual(["MSB Reports"]);
  });

  it("Dashboard is its own direct-link entry above Daily", () => {
    const groups = filterNavForRole("admin", ["daily_book.read"]);
    const titles = groups.map((g) => g.title);
    expect(titles.indexOf("Dashboard"))
      .toBeLessThan(titles.indexOf("Daily"));
    const dash = groups.find((g) => g.title === "Dashboard");
    expect(dash!.to).toBe("/dashboard");
    const owner = filterNavForRole("owner", [])
      .find((g) => g.title === "Dashboard");
    expect(owner!.to).toBe("/owner/dashboard");
  });

  it("admin can resolve the Daily hub to its destinations", () => {
    const perms = [
      "transfers.read", "customers.read",
      "daily_book.read", "return_checks.read",
    ];
    const groups = filterNavForRole("admin", perms);
    const daily = groups.find((g) => sectionSlug(g.title) === "daily");
    expect(daily).toBeDefined();
    const labels = daily!.items.map((i) => i.label);
    expect(labels).toContain("MSB Daily book");
    // Dashboard + Returned checks moved out of Daily (own entry /
    // Money services respectively).
    expect(labels).not.toContain("Dashboard");
    expect(labels).not.toContain("Returned checks");
  });

  it("Returned checks lives in Money services; TV display in Displays", () => {
    const groups = filterNavForRole(
      "admin", ["return_checks.read"], ["module_check_cashing"],
    );
    const ms = groups.find((g) => g.title === "Money services");
    expect(ms!.items.map((i) => i.label)).toContain("Returned checks");
    const displays = groups.find((g) => g.title === "Displays");
    expect(displays!.items.map((i) => i.label)).toEqual(["TV display"]);
  });

  it("superadmin nav carries no store-level modules", () => {
    const labels = filterNavForRole("superadmin", [])
      .flatMap((g) => g.items.map((i) => i.label));
    for (const storeOnly of [
      "MSB Daily book", "Store Daily book", "Transactions", "Lottery",
      "Price book", "Purchases",
    ]) {
      expect(labels).not.toContain(storeOnly);
    }
  });

  it("Purchases follows the price-book flag, admin only", () => {
    const on = filterNavForRole(
      "admin", ["catalog.read"], ["module_price_book"],
    ).flatMap((g) => g.items.map((i) => i.label));
    expect(on).toContain("Purchases");
    const off = filterNavForRole(
      "admin", ["catalog.read"], [],
    ).flatMap((g) => g.items.map((i) => i.label));
    expect(off).not.toContain("Purchases");
    const employee = filterNavForRole(
      "employee", ["catalog.read"], ["module_price_book"],
    ).flatMap((g) => g.items.map((i) => i.label));
    expect(employee).not.toContain("Purchases");
    expect(employee).toContain("Price book");
  });
});

describe("module-flag gating (business-type bundles)", () => {
  const perms = [
    "transfers.read", "customers.read", "batches.read",
    "daily_book.read", "return_checks.read",
  ];

  it("hides money-services items when the module flag is off", () => {
    // module_check_cashing is bundled ON for every business type,
    // so a realistic features list carries it even when money
    // services is off (P1-11).
    const groups = filterNavForRole(
      "admin", perms, ["module_check_cashing"],
    );
    const labels = groups.flatMap((g) => g.items.map((i) => i.label));
    expect(labels).not.toContain("Transfers");
    expect(labels).not.toContain("Customers");
    expect(labels).not.toContain("ACH batches");
    expect(labels).toContain("Returned checks");
    expect(labels).toContain("MSB Daily book");
  });

  it("hides Returned checks when check cashing is switched off", () => {
    const groups = filterNavForRole("admin", perms, []);
    const labels = groups.flatMap((g) => g.items.map((i) => i.label));
    expect(labels).not.toContain("Returned checks");
    expect(labels).toContain("MSB Daily book");
  });

  it("shows them when module_money_services is on", () => {
    const groups = filterNavForRole(
      "admin", perms, ["module_money_services"],
    );
    const labels = groups.flatMap((g) => g.items.map((i) => i.label));
    expect(labels).toContain("Transfers");
    expect(labels).toContain("ACH batches");
  });

  it("gates Price book on module_price_book + catalog.read", () => {
    const withFlag = filterNavForRole(
      "admin", [...perms, "catalog.read"], ["module_price_book"],
    );
    expect(withFlag.flatMap((g) => g.items.map((i) => i.label)))
      .toContain("Price book");
    // Flag off (msb_hybrid bundle) → hidden.
    const withoutFlag = filterNavForRole(
      "admin", [...perms, "catalog.read"], [],
    );
    expect(withoutFlag.flatMap((g) => g.items.map((i) => i.label)))
      .not.toContain("Price book");
    // Flag on but no catalog permission → hidden.
    const withoutPerm = filterNavForRole(
      "admin", perms, ["module_price_book"],
    );
    expect(withoutPerm.flatMap((g) => g.items.map((i) => i.label)))
      .not.toContain("Price book");
  });

  it("shows everything while features are still loading (undefined)", () => {
    const groups = filterNavForRole("admin", perms, undefined);
    const labels = groups.flatMap((g) => g.items.map((i) => i.label));
    expect(labels).toContain("Transfers");
  });

  it("superadmin nav is identical with or without module flags", () => {
    const withFlags = filterNavForRole("superadmin", [], []);
    const without = filterNavForRole("superadmin", [], undefined);
    expect(withFlags.map((g) => g.items.map((i) => i.label)))
      .toEqual(without.map((g) => g.items.map((i) => i.label)));
  });
});
