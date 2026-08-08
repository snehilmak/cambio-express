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
  ButtonLink, Card, Empty, PageHeader, PageShell, Pill,
  Table, TableStates, tdStyle, thStyle, type PillTone,
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

// Batch status → shared Pill tone, matching the palette every other
// status surface in the SPA uses (return-check pills, audit badges).
// Statuses come from BatchForm's STATUSES list.
function statusTone(status: string): PillTone {
  const toneByStatus: Record<string, PillTone> = {
    Pending:  "warning",
    Cleared:  "success",
    Returned: "negative",
    Held:     "info",
  };
  return toneByStatus[status] ?? "neutral";
}

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

      <Breadcrumbs crumbs={[{ label: "ACH Batches" }]} />

      <PageHeader
        title="ACH batches"
        subtitle={data ? `${data.rows.length.toLocaleString()} batches` : "—"}
        actions={(
          <ButtonLink href="/batches/new" tone="primary" size="sm"> 
            + New batch
          </ButtonLink>
        )}
      />

      <Card>
        <TableStates
          isLoading={isLoading} isError={isError} error={error}
          isEmpty={!data || data.rows.length === 0}
          onRetry={() => { void refetch(); }}
          emptyTitle="No ACH batches yet."
        />
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
            const active = sortable && c.slug === sort;
            const arrow = active ? (direction === "asc" ? " ▲" : " ▼") : "";
            const align = c.align === "right" ? "right" : "left";
            if (!sortable) {
              return (
                <th key={i} style={{ ...thStyle, textAlign: align }}>
                  {c.label}
                </th>
              );
            }
            // aria-sort on the header cell + a real <button> inside
            // so the column is sortable by keyboard and announced by
            // screen readers, not just mouse-clickable.
            const ariaSort = active
              ? direction === "asc" ? "ascending" : "descending"
              : "none";
            return (
              <th
                key={i}
                aria-sort={ariaSort}
                style={{ ...thStyle, textAlign: align, padding: 0 }}
              >
                <button
                  type="button"
                  onClick={() => onSort(c.slug)}
                  className={styles.sortBtn}
                  style={{ justifyContent: align === "right" ? "flex-end" : "flex-start" }}
                >
                  {c.label}{arrow}
                </button>
              </th>
            );
          })}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const open = () => navigate(`/batches/${r.id}/edit`);
          return (
            <tr
              key={r.id}
              className={styles.row}
              role="button"
              tabIndex={0}
              aria-label={`Open batch ${r.batch_ref}`}
              onClick={open}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  open();
                }
              }}
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
              <td style={tdStyle}>
                <Pill tone={statusTone(r.status)}>{r.status}</Pill>
              </td>
            </tr>
          );
        })}
      </tbody>
    </Table>
  );
}
