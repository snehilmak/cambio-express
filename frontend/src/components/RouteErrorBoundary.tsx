import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

import { captureException } from "../lib/sentry";
import { ErrorState } from "./ui";

// React render-error boundary scoped to a single route.
//
// Wrapping the route output (rather than the whole SPA) means a
// component that throws during render takes down just that route
// — the sidebar / topbar / RequireAuth keep working, and the user
// can navigate elsewhere with a single tap. Sentry captures the
// error via `captureException` (no-op when SENTRY_DSN is unset).
//
// We hand-roll a tiny class component here rather than reach for
// `Sentry.ErrorBoundary` because:
//   - we want the fallback to use the design-system `<ErrorState>`
//   - the user must be able to retry without a full reload, so the
//     fallback wires an onReset that clears the captured error
//   - keeping the boundary independent of Sentry's runtime means
//     it still works if Sentry is later swapped out
//
// Async data-fetch errors (TanStack Query) don't reach this boundary
// — those are surfaced via `isError` + `<ErrorState onRetry={...} />`
// inside each route already. This boundary catches the synchronous
// render-side ones: prop-shape mismatches, null-dereferences in
// formatter functions, "Object is not a function", etc.

interface Props {
  /** Optional label so Sentry events from different routes are
   *  distinguishable on the dashboard. Falls back to "route". */
  routeName?: string;
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class RouteErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Stale-chunk recovery safety net.  `main.tsx` already wires a
    // global `vite:preloadError` listener that reloads before the
    // error reaches React — this branch catches the (rare) case
    // where the error arrives via a different path (e.g. a
    // user-land `import()` that bypasses Vite's preloader).
    // Symptom is identical: the user's in-memory `index.js`
    // references a chunk hash that no longer exists on the server.
    // Only a full reload fetches the new `index.html` + the new
    // hashes, so we trigger it ourselves rather than offering a
    // Retry button that can't recover.
    if (isStaleChunkError(error)) {
      window.location.reload();
      return;
    }
    captureException(error, {
      tags: { boundary: this.props.routeName || "route" },
      extra: { componentStack: info.componentStack },
    });
  }

  reset = () => { this.setState({ error: null }); };

  render() {
    if (this.state.error) {
      return (
        <main style={fallbackStyle}>
          <ErrorState
            message={
              "This page hit an unexpected error. " +
              "The team has been notified — try again, or pick " +
              "another page from the sidebar."
            }
            onRetry={this.reset}
          />
        </main>
      );
    }
    return this.props.children;
  }
}

const fallbackStyle: React.CSSProperties = {
  flex: 1,
  padding: "2rem 1.5rem",
  maxWidth: "60rem",
  width: "100%",
  margin: "0 auto",
  boxSizing: "border-box",
};

// Recognise the family of errors that mean "the chunk hash this
// build remembers no longer exists on the server" — i.e. a deploy
// happened while the tab was open.  Different browsers + bundler
// versions phrase it differently; we match all the common ones
// rather than try to pin a specific message.
function isStaleChunkError(error: Error): boolean {
  const name = error.name || "";
  const message = error.message || "";
  return (
    name === "ChunkLoadError"
    || /Failed to fetch dynamically imported module/i.test(message)
    || /Loading chunk \d+ failed/i.test(message)
    || /Importing a module script failed/i.test(message)
  );
}
