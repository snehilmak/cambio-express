import { useReportList } from "../api/reports";
import ReportCenter from "../components/ReportCenter";
import { Breadcrumbs, ErrorState, Loading, PageShell } from "../components/ui";
import { ApiError } from "../lib/api";

// Two report centers, kept fully separate (owner directive — MSB
// and back-office must not blur): /reports renders the MSB
// collection, /store-reports the retail back-office collection.
// Same component, same server registry endpoint, different
// ?collection= filter.

export default function Reports({
  collection = "msb",
}: {
  collection?: "msb" | "store";
}) {
  const title = collection === "store" ? "Store Reports" : "MSB Reports";
  const { data, isLoading, isError, error, refetch } =
    useReportList(collection);

  if (isLoading) {
    return (
      <PageShell>
        <Breadcrumbs crumbs={[{ label: title }]} />
        <Loading />
      </PageShell>
    );
  }
  if (isError || !data) {
    const status = error instanceof ApiError ? error.status : 0;
    return (
      <PageShell>
        <Breadcrumbs crumbs={[{ label: title }]} />
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
      <Breadcrumbs crumbs={[{ label: title }]} />
      <ReportCenter categories={data.categories} />
    </PageShell>
  );
}
