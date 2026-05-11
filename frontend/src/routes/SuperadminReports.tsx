import { useSuperadminReports } from "../api/superadmin";
import ReportCenter from "../components/ReportCenter";
import { ErrorState, Loading, PageHeader, PageShell } from "../components/ui";
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
      <PageShell>
        <PageHeader title="Reports" />
        <Loading />
      </PageShell>
    );
  }
  if (isError || !data) {
    const status = error instanceof ApiError ? error.status : 0;
    return (
      <PageShell>
        <PageHeader title="Reports" />
        <ErrorState
          message={
            status === 403
              ? "Superadmin scope required."
              : `Couldn't load the report list. ${error instanceof Error ? error.message : ""}`
          }
          onRetry={status === 403 ? undefined : () => { void refetch(); }}
        />
      </PageShell>
    );
  }

  return (
    <PageShell>
      <ReportCenter categories={data.categories} />
    </PageShell>
  );
}
