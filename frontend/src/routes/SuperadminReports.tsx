import { useMemo, useState } from "react";

import {
  useSuperadminReports,
  type SuperadminReportCategory,
  type SuperadminReportRow,
} from "../api/superadmin";
import { ApiError } from "../lib/api";

// /app/superadmin/reports — platform-wide report center index.
//
// Mirrors the legacy Jinja `_report_center.html` partial: accordion
// of categories, each with a list of report rows. Live-search filters
// the visible rows + auto-opens categories that have hits. The
// drilldown URLs still point at Flask paths (/superadmin/reports/<slug>)
// — each report's per-page render migrates separately.
//
// Strings "Report Center" and "Search reports…" are referenced by
// tests (kept for parity with the legacy markup).

export default function SuperadminReports() {
  const { data, isLoading, isError, error } = useSuperadminReports();
  const [query, setQuery] = useState("");

  if (isLoading) {
    return (
      <main style={pageStyle}>
        <h1 style={titleStyle}>Reports</h1>
        <p style={mutedStyle}>Loading…</p>
      </main>
    );
  }
  if (isError || !data) {
    const status = error instanceof ApiError ? error.status : 0;
    return (
      <main style={pageStyle}>
        <h1 style={titleStyle}>Reports</h1>
        <p style={errorStyle}>
          {status === 403
            ? "Superadmin scope required."
            : `Couldn't load the report list. ${error instanceof Error ? error.message : ""}`}
        </p>
      </main>
    );
  }

  return (
    <main style={pageStyle}>
      <ReportCenter categories={data.categories} query={query} setQuery={setQuery} />
    </main>
  );
}


function ReportCenter({
  categories, query, setQuery,
}: {
  categories: SuperadminReportCategory[];
  query: string;
  setQuery: (q: string) => void;
}) {
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
    <section style={centerStyle}>
      <header style={headStyle}>
        <div>
          <h1 style={centerTitleStyle}>Report Center</h1>
          <p style={subtitleStyle}>
            Browse every report by category. Use search to jump straight
            to the report you need.
          </p>
        </div>
        <div style={searchBoxStyle}>
          <span style={searchIconStyle} aria-hidden="true">
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
            style={searchInputStyle}
          />
        </div>
      </header>

      {!anyVisible && (
        <div style={emptyStyle}>No reports match that search.</div>
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
  cat: SuperadminReportCategory & { hits?: number };
  forceOpen: boolean;
}) {
  // `details open` mirrors the legacy disclosure widget so the
  // browser tracks user-toggled state without us re-implementing it.
  // `forceOpen` overrides the user's collapse state during search
  // so hits aren't hidden behind a closed accordion.
  return (
    <details open={forceOpen} style={catStyle}>
      <summary style={summaryStyle}>
        <span style={caretStyle} aria-hidden="true">
          <svg viewBox="0 0 24 24" stroke="currentColor" fill="none"
               strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
               width="14" height="14">
            <polyline points="9 18 15 12 9 6"/>
          </svg>
        </span>
        <span style={iconStyle}
              dangerouslySetInnerHTML={{ __html: cat.icon }} />
        <span style={catLabelStyle}>{cat.label}</span>
        <span style={countStyle}>{cat.reports.length}</span>
      </summary>
      <div style={catBodyStyle}>
        {cat.reports.map((r) => <ReportRow key={r.key} report={r} />)}
      </div>
    </details>
  );
}


function ReportRow({ report }: { report: SuperadminReportRow }) {
  const ready = report.status === "ready" && !!report.url;
  return (
    <div style={rowStyle}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={rowNameStyle}>{report.label}</div>
        <div style={rowDescStyle}>{report.description}</div>
      </div>
      <div>
        {ready
          ? <a href={report.url ?? "#"} style={primaryButtonStyle}>View</a>
          : <span style={pillStyle}>Coming soon</span>}
      </div>
    </div>
  );
}


// ── Styles ──────────────────────────────────────────────────

const pageStyle: React.CSSProperties = {
  maxWidth: 1100, margin: "0 auto", padding: "1.5rem 1rem 3rem",
  fontFamily: "'Inter', system-ui, sans-serif",
};
const titleStyle: React.CSSProperties = {
  fontFamily: "'Space Grotesk', 'Inter', sans-serif",
  fontSize: 24, fontWeight: 700, margin: 0, color: "var(--text)",
};
const mutedStyle: React.CSSProperties = { color: "var(--text-muted)", fontSize: 14 };
const errorStyle: React.CSSProperties = { color: "var(--db-negative)", fontSize: 14 };

const centerStyle: React.CSSProperties = {};
const headStyle: React.CSSProperties = {
  display: "flex", justifyContent: "space-between", alignItems: "flex-end",
  gap: 18, flexWrap: "wrap", marginBottom: 18,
};
const centerTitleStyle: React.CSSProperties = {
  fontFamily: "'Space Grotesk', 'Inter', sans-serif",
  fontSize: 24, fontWeight: 700, margin: 0, color: "var(--text)",
};
const subtitleStyle: React.CSSProperties = {
  margin: "4px 0 0", fontSize: 13, color: "var(--text-muted)",
};
const searchBoxStyle: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: 8,
  padding: "8px 12px",
  background: "var(--surface-2)",
  border: "1px solid var(--border)", borderRadius: 8,
  minWidth: 240,
};
const searchIconStyle: React.CSSProperties = { color: "var(--text-muted)", display: "inline-flex" };
const searchInputStyle: React.CSSProperties = {
  flex: 1, border: 0, background: "transparent", outline: "none",
  fontSize: 13, color: "var(--text)",
  fontFamily: "'Inter', sans-serif",
};

const catStyle: React.CSSProperties = {
  background: "var(--surface)",
  border: "1px solid var(--border)", borderRadius: 12,
  marginBottom: 10, overflow: "hidden",
};
const summaryStyle: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: 12,
  padding: "14px 18px", cursor: "pointer", userSelect: "none",
  listStyle: "none",
};
const caretStyle: React.CSSProperties = {
  color: "var(--text-muted)", display: "inline-flex",
};
const iconStyle: React.CSSProperties = {
  color: "var(--db-neon)", display: "inline-flex",
  width: 20, height: 20,
};
const catLabelStyle: React.CSSProperties = {
  flex: 1, fontFamily: "'Space Grotesk', 'Inter', sans-serif",
  fontSize: 15, fontWeight: 700, color: "var(--text)",
};
const countStyle: React.CSSProperties = {
  fontFamily: "'JetBrains Mono', monospace",
  fontSize: 12, fontWeight: 700, color: "var(--text-muted)",
  padding: "2px 8px",
  background: "var(--surface-2)",
  border: "1px solid var(--border)",
  borderRadius: 999,
};
const catBodyStyle: React.CSSProperties = {
  borderTop: "1px solid var(--border)",
  padding: "8px 18px 14px",
};
const rowStyle: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: 14,
  padding: "12px 0",
  borderBottom: "1px dashed var(--border)",
};
const rowNameStyle: React.CSSProperties = {
  fontFamily: "'Space Grotesk', 'Inter', sans-serif",
  fontSize: 14, fontWeight: 700, color: "var(--text)",
};
const rowDescStyle: React.CSSProperties = {
  fontSize: 12.5, color: "var(--text-muted)", marginTop: 2,
};
const primaryButtonStyle: React.CSSProperties = {
  display: "inline-flex", alignItems: "center",
  padding: "6px 14px",
  background: "var(--db-neon)", color: "#000",
  border: "1px solid var(--db-neon)", borderRadius: 6,
  fontSize: 12.5, fontWeight: 700, textDecoration: "none",
  fontFamily: "'Inter', sans-serif",
};
const pillStyle: React.CSSProperties = {
  display: "inline-flex", alignItems: "center",
  padding: "6px 12px",
  background: "var(--surface-2)", color: "var(--text-muted)",
  border: "1px solid var(--border)", borderRadius: 999,
  fontSize: 11, fontWeight: 700, textTransform: "uppercase",
  letterSpacing: "0.06em",
};
const emptyStyle: React.CSSProperties = {
  padding: "30px 20px", textAlign: "center",
  color: "var(--text-muted)", fontSize: 14,
  background: "var(--surface)",
  border: "1px dashed var(--border)", borderRadius: 12,
  marginBottom: 12,
};
