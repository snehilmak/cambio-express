import { Link } from "react-router-dom";

// Catch-all for unknown SPA routes. Any URL under /app/ that React
// Router can't match renders this — not a Flask 404, because the
// SPA's catch-all serves index.html for every /app/* path.
export default function NotFound() {
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
        to="/"
        style={{
          color: "var(--db-accent, #3fff00)",
          fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
        }}
      >
        ← Back to home
      </Link>
    </main>
  );
}
