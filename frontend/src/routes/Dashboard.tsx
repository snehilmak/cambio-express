import { useNavigate } from "react-router-dom";

import { clearAccessToken, getCurrentIdentity } from "../lib/auth";

// Placeholder dashboard. Confirms the JWT round-trip works end to
// end — the user signs in, lands here, sees their identity claims
// pulled from the token. SPA-4 replaces the body with the real
// "what's happening today" cards (transfer count, pending ACH,
// trial-ending banner) wired to /api/v2/reports/* + /transfers.
export default function Dashboard() {
  const navigate = useNavigate();
  const identity = getCurrentIdentity();

  function onLogout() {
    clearAccessToken();
    navigate("/login", { replace: true });
  }

  return (
    <main
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        padding: "2.5rem 1.5rem",
        maxWidth: "60rem",
        margin: "0 auto",
        width: "100%",
        boxSizing: "border-box",
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "1rem",
          marginBottom: "2rem",
        }}
      >
        <div>
          <h1
            style={{
              fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
              fontSize: "clamp(1.75rem, 4vw, 2.5rem)",
              fontWeight: 600,
              margin: 0,
            }}
          >
            Dashboard
          </h1>
          <p
            style={{
              margin: "0.35rem 0 0",
              color: "var(--db-text-muted, #a3a3a3)",
            }}
          >
            Signed in as{" "}
            <strong style={{ color: "var(--db-text, #f5f5f5)" }}>
              {identity?.username || "—"}
            </strong>
            {identity?.role && (
              <>
                {" "}· role{" "}
                <code
                  style={{
                    fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
                  }}
                >
                  {identity.role}
                </code>
              </>
            )}
          </p>
        </div>
        <button onClick={onLogout} style={logoutBtnStyle}>
          Sign out
        </button>
      </header>

      <section
        style={{
          background: "var(--db-surface-2, #141414)",
          border: "1px solid var(--db-border, #262626)",
          borderRadius: "0.75rem",
          padding: "1.5rem",
        }}
      >
        <h2
          style={{
            fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
            fontSize: "1.1rem",
            margin: "0 0 0.5rem",
          }}
        >
          New experience preview
        </h2>
        <p
          style={{
            margin: 0,
            color: "var(--db-text-muted, #a3a3a3)",
            lineHeight: 1.6,
          }}
        >
          The legacy dashboard is still your source of truth for now. Each
          screen migrates here one PR at a time — transfer list, daily book,
          and reports first. The legacy site at <code>/dashboard</code> is
          unaffected and will keep working until the cutover is complete.
        </p>
      </section>
    </main>
  );
}

const logoutBtnStyle: React.CSSProperties = {
  background: "transparent",
  color: "var(--db-text, #f5f5f5)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem",
  padding: "0.5rem 1rem",
  fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
  fontSize: "0.9rem",
  cursor: "pointer",
  transition: "border-color 120ms ease, background 120ms ease",
};
