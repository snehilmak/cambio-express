import { useLocation } from "react-router-dom";

import { ReportDrilldown } from "../../components/ReportDrilldown";
import { fmtMoney2 } from "../../lib/formatters";

export default function NewVsReturning() {
  const isOwner = useLocation().pathname.startsWith("/owner/");
  const baseRoute = isOwner ? "/owner/reports" : "/reports";
  return (
    <ReportDrilldown
      apiSlug="new-vs-returning"
      title="New vs Returning Senders"
      resultUnit={["bucket", "buckets"]}
      backTo={baseRoute}
      csvUrl={`/api/v2/reports/new-vs-returning.csv`}
      kpis={[
        { label: "Total Senders", tone: "primary",
          value: t => (Number(t.customers ?? 0)).toLocaleString() },
        { label: "New",           tone: "neon",
          value: t => (Number(t.new_count ?? 0)).toLocaleString() },
        { label: "Returning",     tone: "muted",
          value: t => (Number(t.returning_count ?? 0)).toLocaleString() },
        { label: "Total Sent",    tone: "muted",
          value: t => fmtMoney2(Number(t.sent ?? 0)) },
      ]}
      columns={[
        { label: "Bucket",     field: "bucket" },
        { label: "Customers",  field: r => Number(r.customers).toLocaleString(), align: "right", mono: true },
        { label: "Transfers",  field: r => Number(r.txns).toLocaleString(),      align: "right", mono: true },
        { label: "Total Sent", field: r => fmtMoney2(Number(r.sent)),             align: "right", mono: true },
      ]}
    />
  );
}
