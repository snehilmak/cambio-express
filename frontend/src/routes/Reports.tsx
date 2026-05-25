import { useReportList } from "../api/reports";
import ReportCenter from "../components/ReportCenter";
import { Breadcrumbs, ErrorState, Loading, PageShell } from "../components/ui";
import { ApiError } from "../lib/api";

export default function Reports() {
  const { data, isLoading, isError, error, refetch } = useReportList();

  if (isLoading) {
    return (
      <PageShell>
        <Breadcrumbs crumbs={[{ label: "Reports" }]} />
        <Loading />
      </PageShell>
    );
  }
  if (isError || !data) {
    const status = error instanceof ApiError ? error.status : 0;
    return (
      <PageShell>
        <Breadcrumbs crumbs={[{ label: "Reports" }]} />
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
      <Breadcrumbs crumbs={[{ label: "Reports" }]} />
      <ReportCenter categories={data.categories} />
    </PageShell>
  );
}
