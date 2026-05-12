import { Link, useSearchParams } from "react-router-dom";

import {
  useBatches,
  type BatchDir,
  type BatchRow,
  type BatchSort,
} from "../api/batches";
import { getCurrentIdentity } from "../lib/auth";
import {
  ButtonLink, Card, Empty, EmptyState, ErrorState, PageHeader, PageShell,
  TableSkeleton, tokens,
} from "../components/ui";

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
  const { data, isLoading, isError, error, refetch } = useBatches(sort, direction);

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
      <PageShell>
        <PageHeader title="ACH batches" />
        <Empty>Sign in as a store admin to view ACH batches.</Empty>
      </PageShell>
    );
  }

  return (
    <PageShell>
      <PageHeader
        title="ACH batches"
        subtitle={data ? `${data.rows.length.toLocaleString()} batches` : "—"}
        actions={(
          <ButtonLink href="/batches/new" tone="primary">
            + New batch
          </ButtonLink>
        )}
      />

      <Card>
        {isLoading && <TableSkeleton rows={5} cols={5} />}
        {isError && (
          <ErrorState
            message={error instanceof Error ? error.message : "Could not load"}
            onRetry={() => { void refetch(); }}
          />
        )}
        {data && data.rows.length === 0 && !isLoading && (
          <EmptyState title="No ACH batches yet." />
        )}
        {data && data.rows.length > 0 && (
          <BatchesTable
            rows={data.rows}
            sort={sort}
            direction={direction}
            onSort={setSort}
          />
        )}
      </Card>
    </PageShell>
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
                    color: tokens.textMuted,
                    fontWeight: 500,
                    fontSize: "0.78rem",
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                    borderBottom: `1px solid ${tokens.border}`,
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
                e.currentTarget.style.background = tokens.surface;
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
                    color: tokens.textMuted,
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
                    color: r.variance < 0 ? tokens.negative : tokens.accent,
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

const cellStyle: React.CSSProperties = {
  padding: "0.7rem 0.75rem",
  borderBottom: `1px solid ${tokens.borderSubtle}`,
};

const mono: React.CSSProperties = {
  fontFamily: tokens.fontMono,
};

const monoMuted: React.CSSProperties = {
  ...mono,
  fontSize: "0.85rem",
  color: tokens.textMuted,
};
