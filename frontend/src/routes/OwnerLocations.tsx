import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  useOwnerLocations,
  type OwnerPeriod,
  type OwnerStoreRow,
} from "../api/owner";
import { getCurrentIdentity } from "../lib/auth";

// Owner umbrella: per-store stats grid at /app/owner/locations.
// Period selector (today/month/year) drives the date window for
// transfers, volume, over/short. Free-text search filters by
// store name (case-insensitive).
//
// Subsequent PRs add /app/owner (dashboard with KPI cards),
// /app/owner/pl-rollup, and the connect/unlink flow.

const PERIODS: Array<{ slug: OwnerPeriod; label: string }> = [
  { slug: "today", label: "Today"      },
  { slug: "month", label: "This month" },
  { slug: "year",  label: "This year"  },
];

export default function OwnerLocations() {
  const identity = getCurrentIdentity();
  const [sp, setSP] = useSearchParams();
  const period = (sp.get("period") as OwnerPeriod) ?? "month";
  const q      = sp.get("q") ?? "";
  const [qDraft, setQDraft] = useState(q);

  const { data, isLoading, isError, error } = useOwnerLocations(period, q);

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(sp);
    if (value) next.set(key, value);
    else       next.delete(key);
    setSP(next, { replace: true });
  }

  const isOwner =
    identity?.role === "owner" || identity?.role === "superadmin";
  if (!isOwner) {
    return (
      <main style={pageStyle}>
        <h1 style={titleStyle}>Owner locations</h1>
        <p style={emptyStyle}>
          Sign in as an owner to view the multi-store umbrella.
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
          flexWrap: "wrap",
        }}
      >
        <div>
          <h1 style={titleStyle}>Locations</h1>
          <p style={{ margin: "0.35rem 0 0", color: "var(--db-text-muted, #a3a3a3)" }}>
            {data
              ? `${data.matched.toLocaleString()} of ${data.total.toLocaleString()} stores`
              : "—"}
          </p>
        </div>
      </header>

      <div
        style={{
          display: "flex",
          gap: "1rem",
          marginBottom: "1rem",
          flexWrap: "wrap",
          alignItems: "flex-end",
        }}
      >
        <div style={{ display: "flex", gap: "0.5rem" }}>
          {PERIODS.map((p) => {
            const active = period === p.slug;
            return (
              <button
                key={p.slug}
                type="button"
                onClick={() => setParam("period", p.slug)}
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
                {p.label}
              </button>
            );
          })}
        </div>
        <input
          type="search"
          value={qDraft}
          placeholder="Search stores…"
          onChange={(e) => setQDraft(e.target.value)}
          onBlur={() => setParam("q", qDraft.trim())}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              setParam("q", qDraft.trim());
            }
          }}
          style={{ ...inputStyle, maxWidth: "20rem" }}
        />
      </div>

      <section style={cardStyle}>
        {isLoading && <Empty>Loading…</Empty>}
        {isError && (
          <Empty error>
            {error instanceof Error ? error.message : "Could not load"}
          </Empty>
        )}
        {data && data.matched === 0 && !isLoading && data.total === 0 && (
          <Empty>
            No stores connected yet — ask each store admin to redeem an
            owner-connect code.
          </Empty>
        )}
        {data && data.matched === 0 && !isLoading && data.total > 0 && (
          <Empty>No stores match "{q}".</Empty>
        )}
        {data && data.matched > 0 && <Table rows={data.rows} />}
      </section>
    </main>
  );
}

function Table({ rows }: { rows: OwnerStoreRow[] }) {
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
              ["Store",      "left"],
              ["Transfers",  "right"],
              ["Volume",     "right"],
              ["Over/Short", "right"],
              ["Companies",  "left"],
            ].map(([label, align], i) => (
              <th
                key={i}
                style={{
                  textAlign: align as "left" | "right",
                  padding: "0.6rem 0.75rem",
                  color: "var(--db-text-muted, #a3a3a3)",
                  fontWeight: 500,
                  fontSize: "0.78rem",
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                  borderBottom: "1px solid var(--db-border, #262626)",
                }}
              >
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.store_id}>
              <td style={cellStyle}>
                <div style={{ fontWeight: 500 }}>{r.store_name}</div>
                <div
                  style={{
                    color: "var(--db-text-muted, #a3a3a3)",
                    fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
                    fontSize: "0.78rem",
                  }}
                >
                  {r.store_slug}
                </div>
              </td>
              <td style={{ ...cellStyle, textAlign: "right" }}>
                <span style={mono}>{r.transfer_count.toLocaleString()}</span>
              </td>
              <td style={{ ...cellStyle, textAlign: "right" }}>
                <span style={mono}>${r.volume.toFixed(2)}</span>
              </td>
              <td style={{ ...cellStyle, textAlign: "right" }}>
                <span
                  style={{
                    ...mono,
                    color:
                      r.over_short < 0
                        ? "var(--db-negative, #ff3b30)"
                        : r.over_short > 0
                          ? "var(--db-accent, #3fff00)"
                          : "var(--db-text-muted, #a3a3a3)",
                  }}
                >
                  {r.over_short >= 0 ? "+" : ""}${r.over_short.toFixed(2)}
                </span>
              </td>
              <td style={cellStyle}>
                <div
                  style={{
                    display: "flex",
                    gap: "0.35rem",
                    flexWrap: "wrap",
                  }}
                >
                  {r.companies.length === 0 ? (
                    <span style={{ color: "var(--db-text-muted, #a3a3a3)" }}>—</span>
                  ) : (
                    r.companies.slice(0, 5).map((c) => (
                      <span key={c.company} style={chipStyle}>
                        {c.company} · {c.count}
                      </span>
                    ))
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Empty({
  children, error,
}: { children: React.ReactNode; error?: boolean }) {
  return (
    <p
      style={{
        margin: 0,
        padding: "2rem 0",
        textAlign: "center",
        color: error
          ? "var(--db-negative, #ff3b30)"
          : "var(--db-text-muted, #a3a3a3)",
      }}
    >
      {children}
    </p>
  );
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

const filterBtn: React.CSSProperties = {
  border: "1px solid",
  borderRadius: "999px",
  padding: "0.4rem 0.9rem",
  fontSize: "0.85rem",
  fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
  cursor: "pointer",
};

const chipStyle: React.CSSProperties = {
  display: "inline-block",
  background: "rgba(255,255,255,0.06)",
  color: "var(--db-text, #f5f5f5)",
  borderRadius: "999px",
  padding: "0.15rem 0.55rem",
  fontSize: "0.78rem",
  fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
};

const emptyStyle: React.CSSProperties = {
  margin: 0,
  padding: "2rem 0",
  textAlign: "center",
  color: "var(--db-text-muted, #a3a3a3)",
};
