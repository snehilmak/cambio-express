import { useState } from "react";

import {
  useSuperadminStores,
  type SuperadminStoreRow,
} from "../api/superadmin";
import { getCurrentIdentity } from "../lib/auth";
import { EmptyState, ErrorState, TableSkeleton } from "../components/ui";

// Platform-wide stores list at /app/superadmin/stores. Mirrors
// the legacy `/superadmin/stores` table — superadmin's primary
// "what's going on across all customers?" view.
//
// Subsequent PRs add filters (plan, status), the controls
// dashboard, anomaly feed, audit log, and impersonation hooks.

export default function SuperadminStores() {
  const identity = getCurrentIdentity();
  const { data, isLoading, isError, error, refetch } = useSuperadminStores();
  const [q, setQ] = useState("");

  if (identity?.role !== "superadmin") {
    return (
      <main style={pageStyle}>
        <h1 style={titleStyle}>All stores</h1>
        <p style={emptyStyle}>Superadmin scope required.</p>
      </main>
    );
  }

  const filtered =
    data && q
      ? data.rows.filter((r) => {
          const needle = q.toLowerCase();
          return (
            r.name.toLowerCase().includes(needle) ||
            r.slug.toLowerCase().includes(needle) ||
            r.email.toLowerCase().includes(needle)
          );
        })
      : data?.rows;

  return (
    <main style={pageStyle}>
      <header
        style={{
          marginBottom: "1.5rem",
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "1rem",
          flexWrap: "wrap",
        }}
      >
        <div>
          <h1 style={titleStyle}>All stores</h1>
          <p style={{ margin: "0.35rem 0 0", color: "var(--db-text-muted, #a3a3a3)" }}>
            {data
              ? `${(filtered?.length ?? 0).toLocaleString()} of ${data.total.toLocaleString()}`
              : "—"}
          </p>
        </div>
        <input
          type="search"
          value={q}
          placeholder="Search name, slug, email…"
          onChange={(e) => setQ(e.target.value)}
          style={{ ...inputStyle, maxWidth: "22rem" }}
        />
      </header>

      <section style={cardStyle}>
        {isLoading && <TableSkeleton rows={5} cols={5} />}
        {isError && (
          <ErrorState
            message={error instanceof Error ? error.message : "Could not load"}
            onRetry={() => { void refetch(); }}
          />
        )}
        {filtered && filtered.length === 0 && !isLoading && (
          <EmptyState title="No stores match these filters." />
        )}
        {filtered && filtered.length > 0 && <Table rows={filtered} />}
      </section>
    </main>
  );
}

function Table({ rows }: { rows: SuperadminStoreRow[] }) {
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
              "Store",
              "Plan",
              "Status",
              "Trial / retention",
              "Stripe",
              "Created",
            ].map((h, i) => (
              <th
                key={i}
                style={{
                  textAlign: "left",
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
            <tr key={r.store_id}>
              <td style={cellStyle}>
                <div style={{ fontWeight: 500 }}>{r.name}</div>
                <div
                  style={{
                    color: "var(--db-text-muted, #a3a3a3)",
                    fontFamily:
                      "var(--db-font-mono, 'JetBrains Mono', monospace)",
                    fontSize: "0.78rem",
                  }}
                >
                  {r.slug}
                  {r.email ? ` · ${r.email}` : ""}
                </div>
              </td>
              <td style={cellStyle}>
                <PlanPill plan={r.plan} cycle={r.billing_cycle} />
              </td>
              <td style={cellStyle}>
                <StatusPill active={r.is_active} />
              </td>
              <td style={cellStyle}>
                <TrialCell row={r} />
              </td>
              <td style={cellStyle}>
                {r.stripe_customer_id ? (
                  <span
                    style={{
                      ...mono,
                      fontSize: "0.8rem",
                      color: "var(--db-text-muted, #a3a3a3)",
                    }}
                  >
                    {r.stripe_customer_id.slice(0, 14)}…
                  </span>
                ) : (
                  <span style={{ color: "var(--db-text-muted, #a3a3a3)" }}>—</span>
                )}
              </td>
              <td style={cellStyle}>
                <span style={monoMuted}>{r.created_at.slice(0, 10)}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PlanPill({ plan, cycle }: { plan: string; cycle: string }) {
  const palette: Record<string, { bg: string; fg: string }> = {
    trial:    { bg: "rgba(255,184,0,0.15)", fg: "#ffb800" },
    basic:    { bg: "rgba(63,255,0,0.12)",  fg: "#3fff00" },
    pro:      { bg: "rgba(63,255,0,0.20)",  fg: "#3fff00" },
    inactive: { bg: "rgba(255,59,48,0.15)", fg: "#ff3b30" },
  };
  const c = palette[plan] ?? { bg: "transparent", fg: "#a3a3a3" };
  return (
    <span
      style={{
        display: "inline-block",
        background: c.bg,
        color: c.fg,
        borderRadius: "999px",
        padding: "0.15rem 0.55rem",
        fontSize: "0.78rem",
        fontWeight: 600,
        textTransform: "capitalize",
      }}
    >
      {plan}{cycle ? ` · ${cycle}` : ""}
    </span>
  );
}

function StatusPill({ active }: { active: boolean }) {
  return (
    <span
      style={{
        display: "inline-block",
        background: active
          ? "rgba(63,255,0,0.12)"
          : "rgba(255,59,48,0.15)",
        color: active
          ? "var(--db-accent, #3fff00)"
          : "var(--db-negative, #ff3b30)",
        borderRadius: "999px",
        padding: "0.15rem 0.55rem",
        fontSize: "0.78rem",
        fontWeight: 600,
      }}
    >
      {active ? "active" : "disabled"}
    </span>
  );
}

function TrialCell({ row }: { row: SuperadminStoreRow }) {
  if (row.data_retention_until) {
    return (
      <span style={{ color: "var(--db-negative, #ff3b30)", fontSize: "0.85rem" }}>
        Purge {row.data_retention_until.slice(0, 10)}
      </span>
    );
  }
  if (row.plan === "trial" && row.trial_ends_at) {
    return (
      <span style={{ color: "var(--db-text-muted, #a3a3a3)", fontSize: "0.85rem" }}>
        Trial ends {row.trial_ends_at.slice(0, 10)}
      </span>
    );
  }
  return <span style={{ color: "var(--db-text-muted, #a3a3a3)" }}>—</span>;
}

const pageStyle: React.CSSProperties = {
  flex: 1,
  display: "flex",
  flexDirection: "column",
  padding: "2rem 1.5rem",
  maxWidth: "82rem",
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

const inputStyle: React.CSSProperties = {
  background: "var(--db-surface, #0a0a0a)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem",
  padding: "0.55rem 0.75rem",
  color: "var(--db-text, #f5f5f5)",
  fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
  fontSize: "0.95rem",
  outline: "none",
  width: "100%",
  boxSizing: "border-box",
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

const emptyStyle: React.CSSProperties = {
  margin: 0,
  padding: "2rem 0",
  textAlign: "center",
  color: "var(--db-text-muted, #a3a3a3)",
};
