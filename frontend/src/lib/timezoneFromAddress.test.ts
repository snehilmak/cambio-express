import { describe, it, expect } from "vitest";

import {
  timezoneFromAddress,
  usStateFromAddress,
} from "./timezoneFromAddress";

describe("timezoneFromAddress", () => {
  it("maps a State+ZIP address to the state's timezone", () => {
    expect(timezoneFromAddress("Austin, TX 78701")).toBe("America/Chicago");
    expect(timezoneFromAddress("Brooklyn, NY 11201")).toBe("America/New_York");
    expect(timezoneFromAddress("Phoenix, AZ 85001")).toBe("America/Phoenix");
    expect(timezoneFromAddress("Honolulu, HI 96801")).toBe("Pacific/Honolulu");
  });

  it("disambiguates same-city-name states by the ZIP-adjacent code", () => {
    expect(timezoneFromAddress("Portland, OR 97201")).toBe(
      "America/Los_Angeles",
    );
    expect(timezoneFromAddress("Portland, ME 04101")).toBe("America/New_York");
  });

  it("accepts a ZIP+4 and lowercased state code", () => {
    expect(timezoneFromAddress("123 Main St, denver co 80202-1234")).toBe(
      "America/Denver",
    );
  });

  it("falls back to a spelled-out state name", () => {
    expect(timezoneFromAddress("123 Beach Blvd, California")).toBe(
      "America/Los_Angeles",
    );
    expect(timezoneFromAddress("100 Center St, New York")).toBe(
      "America/New_York",
    );
  });

  it("prefers the ST+ZIP signal over a stray state word", () => {
    // "Oregon Trail" is a street, but the real state is Idaho (ID 83701).
    expect(usStateFromAddress("1 Oregon Trail, Boise, ID 83701")).toBe("ID");
    expect(timezoneFromAddress("1 Oregon Trail, Boise, ID 83701")).toBe(
      "America/Denver",
    );
  });

  it("does not false-match a two-letter substring inside a word", () => {
    // "Thor" contains "or" but there's no ST+ZIP and no state *name*.
    expect(timezoneFromAddress("42 Thor Avenue")).toBeNull();
  });

  it("returns null when no state can be found", () => {
    expect(timezoneFromAddress("")).toBeNull();
    expect(timezoneFromAddress("123 Main Street")).toBeNull();
  });
});
