import { describe, expect, it } from "vitest";

import { ApiError } from "../lib/api";
import { readStoreChoices } from "./loginStoreChoices";

function ambiguous(stores: unknown) {
  return new ApiError(409, "Choose which store to sign in to", {
    detail: { code: "store_ambiguous", message: "…", stores },
  });
}

describe("readStoreChoices", () => {
  it("returns the stores from an ambiguous-login 409", () => {
    const choices = readStoreChoices(ambiguous([
      { store_id: 1, store_name: "Store A", role: "employee" },
      { store_id: 2, store_name: "Store B", role: "admin" },
    ]));
    expect(choices).toHaveLength(2);
    expect(choices?.[0].store_name).toBe("Store A");
  });

  it("ignores the TOTP-enrollment 409, which is a plain message", () => {
    // Same status code, different meaning — must fall through to the
    // normal error banner instead of rendering an empty picker.
    const err = new ApiError(409, "Enroll a 2FA factor", {
      detail: "Enroll a 2FA factor",
    });
    expect(readStoreChoices(err)).toBeNull();
  });

  it("ignores a bad password", () => {
    const err = new ApiError(401, "Invalid username or password", {
      detail: "Invalid username or password",
    });
    expect(readStoreChoices(err)).toBeNull();
  });

  it("ignores non-API failures", () => {
    expect(readStoreChoices(new Error("network"))).toBeNull();
    expect(readStoreChoices(null)).toBeNull();
    expect(readStoreChoices(undefined)).toBeNull();
  });

  it("treats an empty or malformed store list as not-a-picker", () => {
    // Rendering a picker with nothing to pick would strand the user.
    expect(readStoreChoices(ambiguous([]))).toBeNull();
    expect(readStoreChoices(ambiguous("nope"))).toBeNull();
    expect(readStoreChoices(ambiguous(undefined))).toBeNull();
  });
});
