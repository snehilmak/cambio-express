import { useOwnerReportList } from "../api/reports";
import ReportCenter from "../components/ReportCenter";
import { ApiError } from "../lib/api";

// /app/owner/reports — owner-scoped report center index.
//
// Same registry as the per-store /app/reports, but the drilldown
// URLs route through the owner-prefix mirrors registered by
// `_register_owner_report_mirrors` in app.py — each `report_<x>`
// admin endpoint has an `owner_report_<x>` mirror that filters to
// every store under the owner umbrella.

export default function OwnerReports() {
  const { data, isLoading, isError, error } = useOwnerReportList();

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
            ? "Owner scope required."
            : `Couldn't load the report list. ${error instanceof Error ? error.message : ""}`}
        </p>
      </main>
    );
  }

  return (
    <main style={pageStyle}>
      <ReportCenter categories={data.categories} />
    </main>
  );
}


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
