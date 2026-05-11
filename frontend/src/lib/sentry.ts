// Sentry init for the React SPA — no-op when VITE_SENTRY_DSN is empty.
//
// Two import.meta.env vars:
//   VITE_SENTRY_DSN          — project DSN. Empty (default) skips init.
//   VITE_SENTRY_ENVIRONMENT  — environment tag (development, staging,
//                              production). Falls back to import.meta
//                              .env.MODE.
//
// `init()` is idempotent — second calls are a no-op so reloading the
// SPA bundle during development doesn't double-init.
import * as Sentry from "@sentry/react";

let initialised = false;

export function initSentry(): boolean {
  if (initialised) return true;

  const dsn = import.meta.env.VITE_SENTRY_DSN;
  if (!dsn) return false;

  Sentry.init({
    dsn,
    environment:
      import.meta.env.VITE_SENTRY_ENVIRONMENT || import.meta.env.MODE,
    // Browser-side perf integration. tracesSampleRate is intentionally
    // conservative — 5% of transactions captured by default. Override
    // via VITE_SENTRY_TRACES_SAMPLE_RATE if you need higher fidelity.
    integrations: [Sentry.browserTracingIntegration()],
    tracesSampleRate: Number(
      import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE ?? "0.05",
    ),
    // Don't capture form input, headers, or cookies by default. Flip
    // in the Sentry project settings if you need richer context.
    sendDefaultPii: false,
  });

  initialised = true;
  return true;
}

// Re-export the bits the rest of the app cares about so callers
// import from one place. Lets us swap to a different reporter (or
// strip Sentry entirely) without rewriting consumers.
export const captureException = Sentry.captureException;
export const captureMessage = Sentry.captureMessage;
export const ErrorBoundary = Sentry.ErrorBoundary;
