import { useNavigate } from "react-router-dom";

import { useRecentTransfers, type TransferRow } from "../api/transfers";
import { clearAccessToken, getCurrentIdentity } from "../lib/auth";

// Authed landing page. Header shows identity + sign-out, the body
// renders one card per data source. Each card is independent —
// own query, own loading/error state — so a slow endpoint doesn't
// block the rest of the page.
//
// SPA-4 ships the first card (Recent transfers). Subsequent PRs
// add today's totals, pending ACH, and the trial-status banner.
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
        maxWidth: "70rem",
        margin: "0 auto",
        width: "100%",
        boxSizing: "border-box",
        gap: "1.5rem",
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "1rem",
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
                    fontFamily:
                      "var(--db-font-mono, 'JetBrains Mono', monospace)",
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

      <RecentTransfersCard />
    </main>
  );
}

function RecentTransfersCard() {
  const identity = getCurrentIdentity();
  const { data, isLoading, isError, error } = useRecentTransfers({ limit: 10 });

  // Superadmin / owners-without-a-pinned-store have store_id=null
  // in their JWT, so the query is disabled. Show a placeholder
  // instead of an empty table — the umbrella store-picker lands
  // in a follow-up PR.
  if (identity?.store_id == null) {
    return (
      <Card title="Recent transfers">
        <Empty>
          Sign in as a store admin to see this store's recent transfers.
          Owner umbrellas + superadmin store-picker land in a follow-up PR.
        </Empty>
      </Card>
    );
  }

  return (
    <Card
      title="Recent transfers"
      subtitle={
        data
          ? `${data.total.toLocaleString()} total · showing ${data.rows.length}`
          : undefined
      }
    >
      {isLoading && <Empty>Loading…</Empty>}
      {isError && (
        <Empty error>
          Couldn't load transfers — {error instanceof Error ? error.message : "unknown error"}
        </Empty>
      )}
      {data && data.rows.length === 0 && (
        <Empty>No transfers recorded yet for this store.</Empty>
      )}
      {data && data.rows.length > 0 && <TransfersTable rows={data.rows} />}
    </Card>
  );
}

function TransfersTable({ rows }: { rows: TransferRow[] }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: "0.92rem",
        }}
      >
        <thead>
          <tr>
            {["Date", "Company", "Sender", "Recipient", "Country", "Total"].map(
              (h, i) => (
                <th
                  key={h}
                  style={{
                    textAlign: i === 5 ? "right" : "left",
                    padding: "0.6rem 0.75rem",
                    color: "var(--db-text-muted, #a3a3a3)",
                    fontWeight: 500,
                    fontSize: "0.78rem",
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                    borderBottom: "1px solid var(--db-border, #262626)",
                  }}
                >
                  {h}
                </th>
              ),
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td style={cellStyle}>
                <span
                  style={{
                    fontFamily:
                      "var(--db-font-mono, 'JetBrains Mono', monospace)",
                    fontSize: "0.85rem",
                    color: "var(--db-text-muted, #a3a3a3)",
                  }}
                >
                  {r.send_date}
                </span>
              </td>
              <td style={cellStyle}>{r.company}</td>
              <td style={cellStyle}>{r.sender_name}</td>
              <td style={cellStyle}>{r.recipient_name || "—"}</td>
              <td style={cellStyle}>{r.country || "—"}</td>
              <td style={{ ...cellStyle, textAlign: "right" }}>
                <span
                  style={{
                    fontFamily:
                      "var(--db-font-mono, 'JetBrains Mono', monospace)",
                  }}
                >
                  ${r.total_collected.toFixed(2)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Card({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section
      style={{
        background: "var(--db-surface-2, #141414)",
        border: "1px solid var(--db-border, #262626)",
        borderRadius: "0.75rem",
        padding: "1.5rem",
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "1rem",
          marginBottom: "1rem",
        }}
      >
        <h2
          style={{
            fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
            fontSize: "1.1rem",
            margin: 0,
          }}
        >
          {title}
        </h2>
        {subtitle && (
          <span
            style={{
              fontSize: "0.85rem",
              color: "var(--db-text-muted, #a3a3a3)",
            }}
          >
            {subtitle}
          </span>
        )}
      </header>
      {children}
    </section>
  );
}

function Empty({
  children,
  error,
}: {
  children: React.ReactNode;
  error?: boolean;
}) {
  return (
    <p
      style={{
        margin: 0,
        padding: "1.25rem 0",
        textAlign: "center",
        color: error
          ? "var(--db-negative, #ff3b30)"
          : "var(--db-text-muted, #a3a3a3)",
        fontSize: "0.95rem",
      }}
    >
      {children}
    </p>
  );
}

const cellStyle: React.CSSProperties = {
  padding: "0.75rem",
  borderBottom: "1px solid var(--db-border-subtle, #1f1f1f)",
};

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
