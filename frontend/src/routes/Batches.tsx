import { useNavigate, useSearchParams } from "react-router-dom";

import {
  useBatches,
  type BatchDir,
  type BatchRow,
  type BatchSort,
} from "../api/batches";
import { getCurrentIdentity } from "../lib/auth";
import {
  Breadcrumbs,
  ButtonLink, Card, Empty, EmptyState, ErrorState, PageHeader, PageShell,
  Table, TableSkeleton, tdStyle, thStyle,
} from "../components/ui";
import styles from "./Batches.module.css";

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
      <PageShell maxWidth="80rem">
        <PageHeader title="ACH batches" />
        <Empty>Sign in as a store admin to view ACH batches.</Empty>
      </PageShell>
    );
  }

  return (
    <PageShell maxWidth="80rem">

      <Breadcrumbs crumbs={[{ label: "ACH Batches" }]} />

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
  const navigate = useNavigate();
  return (
    <Table>
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
                style={{ ...thStyle, textAlign: c.align === "right" ? "right" : "left" }}
                className={sortable ? styles.sortableTh : undefined}
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
            className={styles.row}
            style={{ cursor: "pointer" }}
            onClick={() => navigate(`/batches/${r.id}/edit`)}
          >
            <td style={tdStyle}>
              <span className={styles.monoMuted}>{r.ach_date}</span>
            </td>
            <td style={tdStyle}>{r.company}</td>
            <td style={tdStyle}>
              <span className={styles.mono}>{r.batch_ref}</span>
            </td>
            <td style={{ ...tdStyle, textAlign: "right" }}>
              <span className={styles.mono}>${r.ach_amount.toFixed(2)}</span>
            </td>
            <td style={tdStyle}>
              <span className={styles.mono}>${r.transfers_total.toFixed(2)}</span>
              <span className={styles.transferCount}>({r.transfer_count})</span>
            </td>
            <td style={tdStyle}>
              <span className={r.variance < 0 ? styles.varianceNeg : styles.variancePos}>
                {r.variance >= 0 ? "+" : ""}${r.variance.toFixed(2)}
              </span>
            </td>
            <td style={tdStyle}>{r.status}</td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
