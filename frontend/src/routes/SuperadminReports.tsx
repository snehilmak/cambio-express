import { useSuperadminReports } from "../api/superadmin";
import ReportCenter from "../components/ReportCenter";
import { ErrorState, Loading } from "../components/ui";
import { ApiError } from "../lib/api";

// /app/superadmin/reports — platform-wide report center index.
//
// Wires the shared ReportCenter component to the superadmin-scoped
// JSON envelope at /api/v2/superadmin/reports. Drilldown URLs still
// point at Flask paths (/superadmin/reports/<slug>) — each report's
// per-page render migrates separately.

export default function SuperadminReports() {
  const { data, isLoading, isError, error, refetch } = useSuperadminReports();

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
              ? "Superadmin scope required."
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
