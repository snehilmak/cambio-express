import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  defaultStoreIds, useReportDrilldown,
  type AggregatedRow, type AggregatedTotals,
} from "../api/reportDrilldown";
import { downloadCsv } from "../lib/api";
import {
  Breadcrumbs, Button, DateInput, EmptyState, ErrorState, KpiCard,
  KpiGrid, PageHeader, PageShell, TableSkeleton, tdStyle, thStyle,
} from "./ui";
import styles from "./ReportDrilldown.module.css";

export interface KpiSpec {
  label: string;
  tone?: "primary" | "neon" | "muted" | "warning" | "negative";
  // Extracted from totals.
  value: (totals: AggregatedTotals) => React.ReactNode;
}

export interface ColumnSpec {
  label: string;
  // Field name on the row OR a render function.
  field: keyof AggregatedRow | ((r: AggregatedRow) => React.ReactNode);
  align?: "left" | "right";
  mono?: boolean;
}

interface ReportDrilldownProps {
  // API path slug ("sales-by-company", "cashier-productivity", …).
  apiSlug: string;
  // Page title.
  title: string;
  // "company" / "companies", "row" / "rows" — used in the result count.
  resultUnit: [string, string];
  // KPI strip across the top.
  kpis: KpiSpec[];
  // Column config for the row table.
  columns: ColumnSpec[];
  // CSV export URL (Flask). Caller passes the resolved URL so each
  // drilldown can point at /reports/<slug>.csv or
  // /owner/reports/<slug>.csv.
  csvUrl: string;
  // Back link target — /app/reports or /app/owner/reports.
  backTo: string;
  // Extra query params for the API (e.g. `{sort_by: "count"}`).
  // The CSV link receives them too so the export matches the view.
  extraParams?: Record<string, string>;
}

const today = () => new Date().toISOString().slice(0, 10);
const monthStart = () => {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), 1)
    .toISOString().slice(0, 10);
};

export function ReportDrilldown({
  apiSlug, title, resultUnit, kpis, columns, csvUrl, backTo,
  extraParams,
}: ReportDrilldownProps) {
  const [params, setParams] = useSearchParams();
  const [from, setFrom] = useState(() => params.get("from") || monthStart());
  const [to, setTo] = useState(() => params.get("to") || today());

  // Sync `from`/`to` back into the URL so the report is shareable.
  useEffect(() => {
    const next = new URLSearchParams(params);
    next.set("from", from);
    next.set("to", to);
    setParams(next, { replace: true });
  }, [from, to]);  // eslint-disable-line react-hooks/exhaustive-deps

  const storeIds = defaultStoreIds();
  const { data, isLoading, isError, error, refetch } = useReportDrilldown({
    apiSlug, from, to, storeIds, extraParams,
  });

  const rowCount = data?.rows.length ?? 0;
  const unit = rowCount === 1 ? resultUnit[0] : resultUnit[1];

  // Append the period (+ store_ids + any extraParams) to the CSV
  // URL so the download matches the visible filter. The FastAPI
  // endpoint reads the same query params as the JSON drilldown.
  const csvParams = new URLSearchParams({ from, to, ...(extraParams ?? {}) });
  if (storeIds.length > 0) {
    csvParams.set("store_ids", storeIds.join(","));
  }
  const csvHref = `${csvUrl}?${csvParams.toString()}`;

  return (
    <PageShell gap="1.25rem">
      <Breadcrumbs crumbs={[
        { label: "Reports", to: backTo },
        { label: title },
      ]} />
      <div>
        <PageHeader
          title={title}
          actions={(
            <div className={styles.actionRow}>
              <form
                style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}
                onSubmit={(e) => {
                  e.preventDefault();
                  // useEffect already syncs to URL — submitting is a noop.
                }}
              >
                <label className={styles.inputLabel}>
                  <span>From</span>
                  <DateInput
                    value={from}
                    onChange={(e) => setFrom(e.target.value)}
                    className={styles.dateInput}
                  />
                </label>
                <label className={styles.inputLabel}>
                  <span>To</span>
                  <DateInput
                    value={to}
                    onChange={(e) => setTo(e.target.value)}
                    className={styles.dateInput}
                  />
                </label>
              </form>
              <Button
                tone="secondary" size="sm"
                onClick={() => {
                  void downloadCsv(csvHref, csvFilename(csvUrl, from, to));
                }}
              >
                Export CSV
              </Button>
              <Button
                tone="secondary" size="sm"
                onClick={() => window.print()}
              >
                Print / PDF
              </Button>
            </div>
          )}
        />
      </div>

      {storeIds.length === 0 && (
        <p className={styles.muted}>
          Sign in to a store to see this report.
        </p>
      )}

      {data && (
        <KpiGrid minWidth="180px">
          {kpis.map((k) => (
            <KpiCard
              key={k.label}
              label={k.label}
              value={k.value(data.totals)}
              tone={k.tone ?? "neutral"}
            />
          ))}
        </KpiGrid>
      )}

      <div className={styles.filterRow}>
        <span className={styles.muted}>
          {fmtDate(from)} – {fmtDate(to)}
        </span>
        {data && (
          <span className={styles.muted}>
            {rowCount.toLocaleString()} {unit}
          </span>
        )}
      </div>

      {isLoading && <TableSkeleton rows={5} cols={columns.length || 4} />}
      {isError && (
        <ErrorState
          message={`Couldn't load report — ${error instanceof Error ? error.message : "unknown error"}`}
          onRetry={() => { void refetch(); }}
        />
      )}

      {data && data.rows.length === 0 && (
        <EmptyState title="No data in this period." />
      )}

      {data && data.rows.length > 0 && (
        <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              {columns.map((c) => (
                <th
                  key={c.label}
                  style={{
                    ...thStyle,
                    textAlign: c.align ?? (c.mono ? "right" : "left"),
                  }}
                >
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r, i) => (
              <tr key={i}>
                {columns.map((c) => {
                  const value =
                    typeof c.field === "function"
                      ? c.field(r)
                      : r[c.field];
                  return (
                    <td
                      key={c.label}
                      style={{
                        ...tdStyle,
                        textAlign: c.align ?? (c.mono ? "right" : "left"),
                        fontFamily: c.mono ? "var(--db-font-mono, 'JetBrains Mono', monospace)" : undefined,
                      }}
                    >
                      {value as React.ReactNode}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
    </PageShell>
  );
}

// Derive a filename from the CSV URL slug + period. Mirrors the
// `fname_prefix_<from>_<to>.csv` shape the backend's
// `Content-Disposition` header produces, but we generate it on
// the client so a slow network doesn't block the download UX.
function csvFilename(url: string, from: string, to: string): string {
  const path = url.split("?")[0];
  const slug = path.split("/").pop()?.replace(/\.csv$/, "") || "report";
  return `${slug}_${from}_${to}.csv`;
}

function fmtDate(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, {
    month: "short", day: "numeric", year: "numeric",
  });
}

