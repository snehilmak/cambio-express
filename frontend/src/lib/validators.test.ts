import { describe, it, expect } from "vitest";

import {
  firstError,
  isValidPhone,
  zDigitsOnly,
  zEmailOptional,
  zEmailRequired,
  zFraction,
  zPhoneOptional,
  zPhoneRequired,
  zPositiveInt,
  zRequiredSelect,
  zRequiredString,
} from "./validators";

describe("string validators", () => {
  it("zRequiredString rejects empty / whitespace, keeps a label", () => {
    expect(firstError(zRequiredString("Name"), "")).toBe("Name is required");
    expect(firstError(zRequiredString("Name"), "   ")).toBe("Name is required");
    expect(firstError(zRequiredString("Name"), "Ada")).toBeNull();
  });
});

describe("email validators", () => {
  it("zEmailOptional allows empty but rejects malformed", () => {
    expect(firstError(zEmailOptional, "")).toBeNull();
    expect(firstError(zEmailOptional, "ada@example.com")).toBeNull();
    expect(firstError(zEmailOptional, "not-an-email")).toBe(
      "Enter a valid email address",
    );
    expect(firstError(zEmailOptional, "a@b")).toBe("Enter a valid email address");
  });

  it("zEmailRequired rejects empty", () => {
    expect(firstError(zEmailRequired, "")).toBe("Enter a valid email address");
    expect(firstError(zEmailRequired, "ada@example.com")).toBeNull();
  });
});

describe("number validators", () => {
  it("zDigitsOnly enforces digits and optional exact length", () => {
    expect(firstError(zDigitsOnly(), "12345")).toBeNull();
    expect(firstError(zDigitsOnly(), "12a45")).toBe("Numbers only");
    expect(firstError(zDigitsOnly(5), "123")).toBe("Enter exactly 5 digits");
    expect(firstError(zDigitsOnly(5), "12345")).toBeNull();
    expect(firstError(zDigitsOnly(5), "")).toBeNull(); // empty passes; wrap w/ required
  });

  it("zPositiveInt coerces and enforces > 0 whole numbers", () => {
    expect(firstError(zPositiveInt, "5")).toBeNull();
    expect(firstError(zPositiveInt, "0")).toBe("Must be greater than 0");
    expect(firstError(zPositiveInt, "2.5")).toBe("Must be a whole number");
  });

  it("zFraction bounds a 0..1 rate", () => {
    expect(firstError(zFraction, "0.01")).toBeNull();
    expect(firstError(zFraction, "1")).toBeNull();
    expect(firstError(zFraction, "1.5")).toBe("Must be 1.0 (100%) or less");
    expect(firstError(zFraction, "-0.1")).toBe("Must be 0 or more");
  });
});

describe("select validator", () => {
  it("zRequiredSelect needs a non-empty choice", () => {
    expect(firstError(zRequiredSelect("Company"), "")).toBe(
      "Company is required",
    );
    expect(firstError(zRequiredSelect("Company"), "Intermex")).toBeNull();
  });
});

describe("phone validators", () => {
  it("isValidPhone enforces per-country rules (US = 10 digits)", () => {
    // Valid US number in E.164 + national forms.
    expect(isValidPhone("+13105551234")).toBe(true);
    expect(isValidPhone("3105551234", "US")).toBe(true);
    // Too short for the US.
    expect(isValidPhone("555", "US")).toBe(false);
    expect(isValidPhone("+1555")).toBe(false);
    // A valid Mexican number under MX rules.
    expect(isValidPhone("+525555555555")).toBe(true);
    expect(isValidPhone("")).toBe(false);
  });

  it("zPhoneOptional allows empty, rejects invalid, accepts valid E.164", () => {
    expect(firstError(zPhoneOptional, "")).toBeNull();
    expect(firstError(zPhoneOptional, "+13105551234")).toBeNull();
    expect(firstError(zPhoneOptional, "+1555")).toBe(
      "Enter a valid phone number",
    );
  });

  it("zPhoneRequired rejects empty", () => {
    expect(firstError(zPhoneRequired, "")).toBe("Enter a valid phone number");
    expect(firstError(zPhoneRequired, "+13105551234")).toBeNull();
  });
});
