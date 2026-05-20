import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "./App";
import { registerServiceWorker } from "./lib/installPrompt";
import { initSentry } from "./lib/sentry";
import "./styles.css";

// No-op when VITE_SENTRY_DSN is empty (CI, local dev). Activates and
// hooks browserTracing + ErrorBoundary integrations otherwise.
initSentry();

// Wire the PWA service worker. Idempotent — the browser dedups
// the registration if a logged-out Jinja page already kicked
// it off. Required for the install prompt to fire on Chrome /
// Edge (the SPA shell needs an active SW + manifest before
// ``beforeinstallprompt`` is dispatched).
registerServiceWorker();

// Stale-chunk recovery after a deploy.
//
// Vite splits every lazy-loaded route into its own content-hashed
// chunk (e.g. `Transfers-AbCd1234.js`).  When a new build ships,
// the old chunks are deleted from the server — but a tab that's
// already loaded `index.js` is still holding references to the
// old hashes in memory.  Clicking a NavLink that triggers
// `import('./routes/Transfers')` then 404s with a `ChunkLoadError`
// / "Failed to fetch dynamically imported module", and the error
// boundary's Retry button only resets React state (it can't fix
// the in-memory references), so the user is stuck until they
// close + reopen the tab.
//
// Vite emits `vite:preloadError` on the window the instant a
// chunk preload fails.  Catching it here forces a full reload
// before the error ever reaches React — the user gets a brief
// flash and the new build comes up working.  The `RouteErrorBoundary`
// has a matching safety net for the (rare) cases where this event
// doesn't fire (e.g. error came from a non-preload dynamic import).
window.addEventListener("vite:preloadError", () => {
  window.location.reload();
});

// Single QueryClient for the SPA. Defaults are conservative: we don't
// auto-refetch on window focus (financial data is rarely stale enough
// to warrant the extra calls) and a 30s staleTime keeps the
// dashboards from re-running heavy aggregators on every navigation.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

const rootEl = document.getElementById("root");
if (!rootEl) throw new Error("Missing #root");

// Routes live under /app/ in production (see vite.config.ts `base`),
// so React Router's `basename` matches.
createRoot(rootEl).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename="/app">
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
