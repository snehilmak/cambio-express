import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "./App";
import { initSentry } from "./lib/sentry";
import "./styles.css";

// No-op when VITE_SENTRY_DSN is empty (CI, local dev). Activates and
// hooks browserTracing + ErrorBoundary integrations otherwise.
initSentry();

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
