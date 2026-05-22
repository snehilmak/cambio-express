// Test setup — loaded once before any test file runs.
//
// Adds @testing-library/jest-dom matchers (`toBeInTheDocument`,
// `toHaveTextContent`, etc.) to Vitest's `expect`.
//
// Also wires the React Testing Library auto-cleanup hook —
// RTL skips its own afterEach registration when Vitest is
// configured with `globals: false`, so we register it manually
// here.  Without this, components leak between tests and
// `screen.getByRole(...)` returns "multiple elements found"
// errors that look like real bugs.

import "@testing-library/jest-dom/vitest";

import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});
