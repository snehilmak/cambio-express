import { useReportList } from "../api/reports";
import ReportCenter from "../components/ReportCenter";
import { ErrorState, Loading, PageHeader, PageShell } from "../components/ui";
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
              ? "Sign in as a store user to view reports."
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
