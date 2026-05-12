import { Link } from "react-router-dom";

import { getCurrentIdentity } from "../lib/auth";

// Catch-all for unknown SPA routes. Mounted twice in App.tsx — once
// inside AuthedShell (so the chrome stays put when an authed user
// hits a typo) and once at the top level (so unauthed visitors land
// on something other than a blank screen).
//
// Pick the "back to" destination based on whether we can read an
// identity from localStorage: authed users get bounced to their
// dashboard, anonymous ones to /login. Sending an authed user to /
// (the marketing landing) made them feel logged out and was the
// source of the "back went to login" UX bug.
export default function NotFound() {
  const identity = getCurrentIdentity();
  const target = identity ? "/dashboard" : "/login";
  const label = identity ? "← Back to dashboard" : "← Back to sign in";
  return (
    <main
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "1.25rem",
        padding: "2rem",
        textAlign: "center",
      }}
    >
      <h1
        style={{
          fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
          fontSize: "clamp(2rem, 5vw, 3rem)",
          margin: 0,
        }}
      >
        404
      </h1>
      <p style={{ color: "var(--db-text-muted, #a3a3a3)", margin: 0 }}>
        That page hasn't been built yet.
      </p>
      <Link
        to={target}
        style={{
          color: "var(--db-accent, #3fff00)",
          fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
        }}
      >
        {label}
      </Link>
    </main>
  );
}
