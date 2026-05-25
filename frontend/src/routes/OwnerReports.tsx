import { useOwnerReportList } from "../api/reports";
import ReportCenter from "../components/ReportCenter";
import {
  Breadcrumbs, ErrorState, Loading, PageHeader, PageShell } from "../components/ui";
import { ApiError } from "../lib/api";

// /app/owner/reports — owner-scoped report center index.
//
// Same registry as the per-store /app/reports, but the drilldown
// URLs route through the owner-prefix mirrors registered by
// `_register_owner_report_mirrors` in app.py — each `report_<x>`
// admin endpoint has an `owner_report_<x>` mirror that filters to
// every store under the owner umbrella.

export default function OwnerReports() {
  const { data, isLoading, isError, error, refetch } = useOwnerReportList();

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

        <Breadcrumbs crumbs={[{ label: "Owner" }, { label: "Reports" }]} />

        <PageHeader title="Reports" />
        <ErrorState
          message={
            status === 403
              ? "Owner scope required."
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
