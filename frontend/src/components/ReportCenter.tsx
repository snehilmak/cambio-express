import { useMemo, useState } from "react";

import {
  ButtonLink, Card, Input, PageHeader, Pill,
} from "./ui";
import styles from "./ReportCenter.module.css";

// Shared report-center used by /app/reports, /app/owner/reports,
// and /app/superadmin/reports. Renders a search box in the
// PageHeader actions slot + one card per category with report rows
// inside.

export interface ReportRow {
  key: string;
  label: string;
  description: string;
  url: string | null;
  status: string;  // "ready" | "coming_soon"
}

export interface ReportCategoryRow {
  key: string;
  label: string;
  icon: string;  // inline stroke SVG
  reports: ReportRow[];
}

export default function ReportCenter({
  categories,
}: {
  categories: ReportCategoryRow[];
}) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) {
      return categories.map((c) => ({ ...c, hits: c.reports.length }));
    }
    return categories.map((c) => {
      const hits = c.reports.filter((r) =>
        r.label.toLowerCase().includes(q)
        || r.description.toLowerCase().includes(q),
      );
      return { ...c, reports: hits, hits: hits.length };
    }).filter((c) => c.hits > 0);
  }, [categories, query]);

  const anyVisible = filtered.length > 0;

  return (
    <section>
      <PageHeader
        title="Report Center"
        subtitle="Browse every report by category."
        actions={(
          <div className={styles.searchBox}>
            <Input
              type="search"
              placeholder="Search reports…"
              autoComplete="off"
              aria-label="Search reports"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
        )}
      />

      {!anyVisible && (
        <div className={styles.empty}>No reports match that search.</div>
      )}

      <div className={styles.catGrid}>
        {filtered.map((cat) => (
          <CategoryCard
            key={cat.key} cat={cat}
            forceOpen={!!query.trim() && cat.hits > 0}
          />
        ))}
      </div>
    </section>
  );
}


function CategoryCard({
  cat, forceOpen,
}: {
  cat: ReportCategoryRow & { hits?: number };
  forceOpen: boolean;
}) {
  return (
    <Card>
      <details open={forceOpen || undefined} className={styles.cat}>
        <summary className={styles.summary}>
          <span className={styles.icon}
                dangerouslySetInnerHTML={{ __html: cat.icon }} />
          <span className={styles.catLabel}>{cat.label}</span>
          <Pill tone="neutral">{cat.reports.length}</Pill>
          <span className={styles.caret} aria-hidden="true">
            <svg viewBox="0 0 24 24" stroke="currentColor" fill="none"
                 strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                 width="14" height="14">
              <polyline points="9 18 15 12 9 6"/>
            </svg>
          </span>
        </summary>
        <div className={styles.catBody}>
          {cat.reports.map((r) => <ReportRowView key={r.key} report={r} />)}
        </div>
      </details>
    </Card>
  );
}


function ReportRowView({ report }: { report: ReportRow }) {
  const ready = report.status === "ready" && !!report.url;
  return (
    <div className={styles.row}>
      <div className={styles.rowBody}>
        <div className={styles.rowName}>{report.label}</div>
        <div className={styles.rowDesc}>{report.description}</div>
      </div>
      <div>
        {ready
          ? <ButtonLink href={report.url ?? "#"} size="sm">View</ButtonLink>
          : <Pill tone="info">Coming soon</Pill>}
      </div>
    </div>
  );
}
