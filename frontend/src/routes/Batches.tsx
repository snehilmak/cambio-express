import { Link, useSearchParams } from "react-router-dom";

import {
  useBatches,
  type BatchDir,
  type BatchRow,
  type BatchSort,
} from "../api/batches";
import { getCurrentIdentity } from "../lib/auth";

// Read-only ACH batches list at /app/batches. Sort by clicking
// column headers (URL-driven). Variance cell colored red when
// the batch under-paid the transfer ledger, green when matched/
// over-paid.
//
// Create / edit / link-transfers stays on the legacy Jinja
// /batches/* routes until subsequent PRs migrate them.

const COLUMNS: Array<{ slug: BatchSort; label: string; align?: "right" }> = [
  { slug: "ach_date",   label: "Date" },
  { slug: "company",    label: "Company" },
  { slug: "batch_ref",  label: "Ref" },
  { slug: "ach_amount", label: "ACH amount", align: "right" },
  { slug: "",           label: "Transfers"   },
  { slug: "",           label: "Variance" },
  { slug: "status",     label: "Status" },
];

export default function Batches() {
  const identity = getCurrentIdentity();
  const [sp, setSP] = useSearchParams();
  const sort      = (sp.get("sort") as BatchSort) ?? "";
  const direction = ((sp.get("dir") as BatchDir) ?? "desc");
  const { data, isLoading, isError, error } = useBatches(sort, direction);

  function setSort(slug: BatchSort) {
    if (!slug) return;
    const params = new URLSearchParams(sp);
    if (sort === slug) {
      params.set("dir", direction === "asc" ? "desc" : "asc");
    } else {
      params.set("sort", slug);
      params.set("dir", "asc");
    }
    setSP(params, { replace: true });
  }

  if (identity?.store_id == null) {
    return (
      <main style={pageStyle}>
        <h1 style={titleStyle}>ACH batches</h1>
        <p style={emptyStyle}>
          Sign in as a store admin to view ACH batches.
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
          <h1 style={titleStyle}>ACH batches</h1>
          <p
            style={{
              margin: "0.35rem 0 0",
              color: "var(--db-text-muted, #a3a3a3)",
            }}
          >
            {data
              ? `${data.rows.length.toLocaleString()} batches`
              : "—"}
          </p>
        </div>
        <Link
          to="/batches/new"
          style={{
            background: "var(--db-accent, #3fff00)",
            color: "var(--db-on-accent, #0a0a0a)",
            borderRadius: "0.5rem",
            padding: "0.55rem 1rem",
            fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
            fontSize: "0.9rem",
            fontWeight: 600,
            textDecoration: "none",
          }}
        >
          + New batch
        </Link>
      </header>

      <section style={cardStyle}>
        {isLoading && <Empty>Loading…</Empty>}
        {isError && (
          <Empty error>
            {error instanceof Error ? error.message : "Could not load"}
          </Empty>
        )}
        {data && data.rows.length === 0 && !isLoading && (
          <Empty>No ACH batches yet.</Empty>
        )}
        {data && data.rows.length > 0 && (
          <BatchesTable
            rows={data.rows}
            sort={sort}
            direction={direction}
            onSort={setSort}
          />
        )}
      </section>
    </main>
  );
}

function BatchesTable({
  rows, sort, direction, onSort,
}: {
  rows: BatchRow[];
  sort: BatchSort;
  direction: BatchDir;
  onSort: (s: BatchSort) => void;
}) {
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
            {COLUMNS.map((c, i) => {
              const sortable = Boolean(c.slug);
              const arrow =
                sortable && c.slug === sort
                  ? direction === "asc" ? " ▲" : " ▼"
                  : "";
              return (
                <th
                  key={i}
                  onClick={sortable ? () => onSort(c.slug) : undefined}
                  style={{
                    textAlign: c.align === "right" ? "right" : "left",
                    padding: "0.6rem 0.75rem",
                    color: "var(--db-text-muted, #a3a3a3)",
                    fontWeight: 500,
                    fontSize: "0.78rem",
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                    borderBottom: "1px solid var(--db-border, #262626)",
                    cursor: sortable ? "pointer" : "default",
                    userSelect: "none",
                  }}
                >
                  {c.label}{arrow}
                </th>
              );
            })}
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
                <Link
                  to={`/batches/${r.id}/edit`}
                  style={{ color: "inherit", textDecoration: "none" }}
                >
                  <span style={monoMuted}>{r.ach_date}</span>
                </Link>
              </td>
              <td style={cellStyle}>{r.company}</td>
              <td style={cellStyle}>
                <Link
                  to={`/batches/${r.id}/edit`}
                  style={{ color: "inherit", textDecoration: "none" }}
                >
                  <span style={mono}>{r.batch_ref}</span>
                </Link>
              </td>
              <td style={{ ...cellStyle, textAlign: "right" }}>
                <span style={mono}>${r.ach_amount.toFixed(2)}</span>
              </td>
              <td style={cellStyle}>
                <span style={mono}>${r.transfers_total.toFixed(2)}</span>
                <span
                  style={{
                    color: "var(--db-text-muted, #a3a3a3)",
                    marginLeft: "0.5rem",
                  }}
                >
                  ({r.transfer_count})
                </span>
              </td>
              <td style={cellStyle}>
                <span
                  style={{
                    ...mono,
                    color: r.variance < 0
                      ? "var(--db-negative, #ff3b30)"
                      : "var(--db-accent, #3fff00)",
                  }}
                >
                  {r.variance >= 0 ? "+" : ""}${r.variance.toFixed(2)}
                </span>
              </td>
              <td style={cellStyle}>{r.status}</td>
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

const emptyStyle: React.CSSProperties = {
  margin: 0,
  padding: "2rem 0",
  textAlign: "center",
  color: "var(--db-text-muted, #a3a3a3)",
};
