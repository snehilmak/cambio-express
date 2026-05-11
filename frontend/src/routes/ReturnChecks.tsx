import { Link, useSearchParams } from "react-router-dom";

import { useReturnChecks, type ReturnCheckRow } from "../api/returnChecks";
import { getCurrentIdentity } from "../lib/auth";
import { EmptyState, ErrorState, TableSkeleton } from "../components/ui";

// Bounced-check workflow list at /app/return-checks. Filter by
// status pill, click any row to edit. Status transitions
// (Mark loss / Mark fraud / Reopen) live on the edit page.

const STATUSES: Array<{ slug: string; label: string }> = [
  { slug: "",          label: "All"       },
  { slug: "pending",   label: "Pending"   },
  { slug: "recovered", label: "Recovered" },
  { slug: "loss",      label: "Loss"      },
  { slug: "fraud",     label: "Fraud"     },
];

export default function ReturnChecks() {
  const identity = getCurrentIdentity();
  const [sp, setSP] = useSearchParams();
  const status = sp.get("status") ?? "";
  const { data, isLoading, isError, error, refetch } = useReturnChecks(status);

  function setStatus(next: string) {
    const params = new URLSearchParams(sp);
    if (next) params.set("status", next);
    else params.delete("status");
    setSP(params, { replace: true });
  }

  if (identity?.store_id == null) {
    return (
      <main style={pageStyle}>
        <h1 style={titleStyle}>Return checks</h1>
        <p style={emptyStyle}>
          Sign in as a store admin to view return checks.
        </p>
      </main>
    );
  }

  return (
    <main style={pageStyle}>
      <header
        style={{
          marginBottom: "1.5rem",
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "1rem",
        }}
      >
        <div>
          <h1 style={titleStyle}>Return checks</h1>
          <p
            style={{
              margin: "0.35rem 0 0",
              color: "var(--db-text-muted, #a3a3a3)",
            }}
          >
            {data
              ? `${data.rows.length.toLocaleString()} ${
                  status || "total"
                } check${data.rows.length === 1 ? "" : "s"}`
              : "—"}
          </p>
        </div>
        <Link to="/return-checks/new" style={primaryBtn}>
          + New return check
        </Link>
      </header>

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}>
        {STATUSES.map((s) => {
          const active = status === s.slug;
          return (
            <button
              key={s.slug}
              type="button"
              onClick={() => setStatus(s.slug)}
              style={{
                ...filterBtn,
                background: active
                  ? "var(--db-accent, #3fff00)"
                  : "transparent",
                color: active
                  ? "var(--db-on-accent, #0a0a0a)"
                  : "var(--db-text, #f5f5f5)",
                borderColor: active
                  ? "var(--db-accent, #3fff00)"
                  : "var(--db-border, #262626)",
              }}
            >
              {s.label}
            </button>
          );
        })}
      </div>

      <section style={cardStyle}>
        {isLoading && <TableSkeleton rows={5} cols={5} />}
        {isError && (
          <ErrorState
            message={error instanceof Error ? error.message : "Could not load"}
            onRetry={() => { void refetch(); }}
          />
        )}
        {data && data.rows.length === 0 && !isLoading && (
          <EmptyState
            title={`No return checks ${status ? `with status ${status}` : "yet"}.`}
          />
        )}
        {data && data.rows.length > 0 && <Table rows={data.rows} />}
      </section>
    </main>
  );
}

function Table({ rows }: { rows: ReturnCheckRow[] }) {
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
            {[
              "Bounced",
              "Customer",
              "Check #",
              "Bank",
              "Amount",
              "Recovered",
              "Status",
            ].map((h, i) => (
              <th
                key={i}
                style={{
                  textAlign: i >= 4 && i <= 5 ? "right" : "left",
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
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.id}
              style={{ transition: "background 120ms ease" }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background =
                  "var(--db-surface, #0a0a0a)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "transparent";
              }}
            >
              <td style={cellStyle}>
                <Link to={`/return-checks/${r.id}/edit`} style={rowLink}>
                  <span style={monoMuted}>{r.bounced_on}</span>
                </Link>
              </td>
              <td style={cellStyle}>{r.customer_name}</td>
              <td style={cellStyle}>
                <span style={mono}>{r.check_number || "—"}</span>
              </td>
              <td style={cellStyle}>{r.payer_bank || "—"}</td>
              <td style={{ ...cellStyle, textAlign: "right" }}>
                <span style={mono}>${r.amount.toFixed(2)}</span>
              </td>
              <td style={{ ...cellStyle, textAlign: "right" }}>
                <span
                  style={{
                    ...mono,
                    color:
                      r.recovered_total >= r.amount
                        ? "var(--db-accent, #3fff00)"
                        : "var(--db-text, #f5f5f5)",
                  }}
                >
                  ${r.recovered_total.toFixed(2)}
                </span>
                {r.payment_count > 0 && (
                  <span
                    style={{
                      color: "var(--db-text-muted, #a3a3a3)",
                      marginLeft: "0.4rem",
                      fontSize: "0.85rem",
                    }}
                  >
                    ({r.payment_count})
                  </span>
                )}
              </td>
              <td style={cellStyle}>
                <StatusPill status={r.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const palette: Record<string, { bg: string; fg: string }> = {
    pending:   { bg: "rgba(255,184,0,0.15)",  fg: "#ffb800" },
    recovered: { bg: "rgba(63,255,0,0.15)",   fg: "#3fff00" },
    loss:      { bg: "rgba(255,59,48,0.15)",  fg: "#ff3b30" },
    fraud:     { bg: "rgba(255,59,48,0.20)",  fg: "#ff6b60" },
  };
  const c = palette[status] ?? { bg: "transparent", fg: "#a3a3a3" };
  return (
    <span
      style={{
        display: "inline-block",
        background: c.bg,
        color: c.fg,
        borderRadius: "999px",
        padding: "0.2rem 0.6rem",
        fontSize: "0.78rem",
        fontWeight: 600,
        textTransform: "capitalize",
      }}
    >
      {status}
    </span>
  );
}

const pageStyle: React.CSSProperties = {
  flex: 1,
  display: "flex",
  flexDirection: "column",
  padding: "2rem 1.5rem",
  maxWidth: "78rem",
  margin: "0 auto",
  width: "100%",
  boxSizing: "border-box",
};

const titleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "clamp(1.5rem, 3.5vw, 2rem)",
  fontWeight: 600,
  margin: 0,
};

const cardStyle: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem",
  padding: "1.25rem",
};

const cellStyle: React.CSSProperties = {
  padding: "0.7rem 0.75rem",
  borderBottom: "1px solid var(--db-border-subtle, #1f1f1f)",
};

const mono: React.CSSProperties = {
  fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
};

const monoMuted: React.CSSProperties = {
  ...mono,
  fontSize: "0.85rem",
  color: "var(--db-text-muted, #a3a3a3)",
};

const rowLink: React.CSSProperties = {
  color: "inherit",
  textDecoration: "none",
};

const emptyStyle: React.CSSProperties = {
  margin: 0,
  padding: "2rem 0",
  textAlign: "center",
  color: "var(--db-text-muted, #a3a3a3)",
};

const primaryBtn: React.CSSProperties = {
  background: "var(--db-accent, #3fff00)",
  color: "var(--db-on-accent, #0a0a0a)",
  borderRadius: "0.5rem",
  padding: "0.55rem 1rem",
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "0.9rem",
  fontWeight: 600,
  textDecoration: "none",
};

const filterBtn: React.CSSProperties = {
  border: "1px solid",
  borderRadius: "999px",
  padding: "0.4rem 0.9rem",
  fontSize: "0.85rem",
  fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
  cursor: "pointer",
};
