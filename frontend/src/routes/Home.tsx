import { Link } from "react-router-dom";

// Scaffolding placeholder. Confirms the SPA pipeline is alive:
// Vite builds, Flask serves /app/, design tokens load. Replaced
// in SPA-3 with the real login → dashboard flow.
export default function Home() {
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
          fontSize: "clamp(2.5rem, 6vw, 4rem)",
          fontWeight: 600,
          letterSpacing: "-0.02em",
          margin: 0,
        }}
      >
        DineroBook
      </h1>
      <p
        style={{
          color: "var(--db-text-muted, #a3a3a3)",
          maxWidth: "32rem",
          lineHeight: 1.6,
          margin: 0,
        }}
      >
        New experience preview. Sign-in and dashboards land here as
        each module migrates from the legacy interface.
      </p>
      <Link
        to="/health"
        style={{
          color: "var(--db-accent, #3fff00)",
          fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
          fontSize: "0.95rem",
        }}
      >
        /app/health →
      </Link>
    </main>
  );
}
