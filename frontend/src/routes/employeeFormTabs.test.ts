import { describe, expect, it } from "vitest";

import {
  EMPLOYEE_TABS, isEmployeeTabKey, resolveEmployeeTab,
  visibleEmployeeTabs,
} from "./employeeFormTabs";

describe("employee form tabs", () => {
  it("exposes Profile, Payroll and Login in order", () => {
    expect(EMPLOYEE_TABS.map((t) => t.key))
      .toEqual(["profile", "payroll", "login"]);
  });

  it("hides the Login tab until the employee exists", () => {
    expect(visibleEmployeeTabs(false).map((t) => t.key))
      .toEqual(["profile", "payroll"]);
    expect(visibleEmployeeTabs(true).map((t) => t.key))
      .toEqual(["profile", "payroll", "login"]);
  });

  describe("resolveEmployeeTab", () => {
    it("defaults to profile when ?tab= is absent", () => {
      expect(resolveEmployeeTab(null, true)).toBe("profile");
    });

    it("falls back to profile for an unknown value", () => {
      expect(resolveEmployeeTab("payrol", true)).toBe("profile");
      expect(resolveEmployeeTab("", true)).toBe("profile");
    });

    it("honours a valid deep link", () => {
      expect(resolveEmployeeTab("payroll", true)).toBe("payroll");
      // The Employees list links straight here from "Manage access".
      expect(resolveEmployeeTab("login", true)).toBe("login");
    });

    it("never renders the Login tab on an unsaved employee", () => {
      expect(resolveEmployeeTab("login", false)).toBe("profile");
      // ...but the other tabs still work while creating.
      expect(resolveEmployeeTab("payroll", false)).toBe("payroll");
    });
  });

  it("type-guards tab keys", () => {
    expect(isEmployeeTabKey("login")).toBe(true);
    expect(isEmployeeTabKey("nope")).toBe(false);
    expect(isEmployeeTabKey(null)).toBe(false);
  });
});
