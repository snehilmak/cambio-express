import { useReportList } from "../api/reports";
import ReportCenter from "../components/ReportCenter";
import { ErrorState, Loading } from "../components/ui";
import { ApiError } from "../lib/api";

// /app/reports — store-scoped report center index.
//
// Mirrors the legacy Jinja `_report_center.html` partial: an
// accordion of categories, each with a list of report rows. Live-
// search filters the visible rows + auto-opens categories that have
// hits. Drilldown URLs still point at Flask paths (/reports/<slug>)
// — each individual report's per-page render migrates separately.

export default function Reports() {
  const { data, isLoading, isError, error, refetch } = useReportList();

  if (isLoading) {
    return (
      <main style={pageStyle}>
        <h1 style={titleStyle}>Reports</h1>
        <Loading />
      </main>
    );
  }
  if (isError || !data) {
    const status = error instanceof ApiError ? error.status : 0;
    return (
      <main style={pageStyle}>
        <h1 style={titleStyle}>Reports</h1>
        <ErrorState
          message={
            status === 403
              ? "Sign in as a store user to view reports."
              : `Couldn't load the report list. ${error instanceof Error ? error.message : ""}`
          }
          onRetry={status === 403 ? undefined : () => { void refetch(); }}
        />
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
