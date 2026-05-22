import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Vitest config — kept separate from vite.config.ts so the SPA's
// dev/build pipeline isn't affected by test-only deps.
//
// jsdom for DOM APIs (createPortal, focus management, etc.).
// `setupFiles` loads @testing-library/jest-dom matchers globally
// so every test file gets `expect(el).toBeInTheDocument()` etc.
// without per-file imports.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    // No globals — tests explicitly `import { describe, it, expect }
    // from "vitest"`.  Keeps the lint config simple (no Vitest
    // globals to whitelist) and makes test-file dependencies
    // obvious at a glance.
    globals: false,
    setupFiles: ["./src/test/setup.ts"],
    css: true,
  },
});
