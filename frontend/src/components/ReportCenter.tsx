import { useMemo, useState } from "react";

import { ButtonLink } from "./ui";
import styles from "./ReportCenter.module.css";

// Shared report-center accordion used by /app/reports,
// /app/owner/reports, and /app/superadmin/reports.
//
// Mirrors the legacy Jinja `_report_center.html` partial: a search
// box on top, then one expandable section per category. Live-search
// filters the visible rows and auto-opens categories that have
// hits. Drilldown URLs render as <a> tags with `reloadDocument`
// behavior — each individual report still renders Jinja today, so
// clicking a row navigates out of the SPA and into the legacy page.
//
// Strings "Report Center" and "Search reports…" are referenced by
// tests for parity with the legacy markup. Keep them.

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

  // Filter visible rows in a memoised pass so typing stays cheap
  // even with 30+ reports across 6 categories.
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
      <header className={styles.head}>
        <div>
          <h1 className={styles.title}>Report Center</h1>
          <p className={styles.subtitle}>
            Browse every report by category. Use search to jump straight
            to the report you need.
          </p>
        </div>
        <div className={styles.searchBox}>
          <span className={styles.searchIcon} aria-hidden="true">
            <svg viewBox="0 0 24 24" stroke="currentColor" fill="none"
                 strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                 width="16" height="16">
              <circle cx="11" cy="11" r="7"/>
              <line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
          </span>
          <input
            type="search"
            placeholder="Search reports…"
            autoComplete="off"
            aria-label="Search reports"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className={styles.searchInput}
          />
        </div>
      </header>

      {!anyVisible && (
        <div className={styles.empty}>No reports match that search.</div>
      )}

      {filtered.map((cat) => (
        <CategoryAccordion
          key={cat.key} cat={cat}
          forceOpen={!!query.trim() && cat.hits > 0}
        />
      ))}
    </section>
  );
}


function CategoryAccordion({
  cat, forceOpen,
}: {
  cat: ReportCategoryRow & { hits?: number };
  forceOpen: boolean;
}) {
  return (
    <details open={forceOpen} className={styles.cat}>
      <summary className={styles.summary}>
        <span className={styles.caret} aria-hidden="true">
          <svg viewBox="0 0 24 24" stroke="currentColor" fill="none"
               strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
               width="14" height="14">
            <polyline points="9 18 15 12 9 6"/>
          </svg>
        </span>
        <span className={styles.icon}
              dangerouslySetInnerHTML={{ __html: cat.icon }} />
        <span className={styles.catLabel}>{cat.label}</span>
        <span className={styles.count}>{cat.reports.length}</span>
      </summary>
      <div className={styles.catBody}>
        {cat.reports.map((r) => <ReportRowView key={r.key} report={r} />)}
      </div>
    </details>
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
          : <span className={styles.pill}>Coming soon</span>}
      </div>
    </div>
  );
}
