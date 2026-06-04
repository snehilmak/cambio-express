import { useLocation } from "react-router-dom";

import { ReportDrilldown } from "../../components/ReportDrilldown";
import { fmtMoney2 } from "../../lib/formatters";

export default function ReturnedCheckStatus() {
  const isOwner = useLocation().pathname.startsWith("/owner/");
  const baseRoute = isOwner ? "/owner/reports" : "/reports";
  return (
    <ReportDrilldown
      apiSlug="returned-check-status"
      title="Returned Check Status"
      resultUnit={["status", "statuses"]}
      backTo={baseRoute}
      csvUrl={`/api/v2/reports/returned-check-status.csv`}
      kpis={[
        { label: "Total Bounces", tone: "primary",
          value: t => Number(t.count ?? 0).toLocaleString() },
        { label: "Total Amount",  tone: "neon",
          value: t => fmtMoney2(Number(t.amount ?? 0)) },
        { label: "Recovered",     tone: "muted",
          value: t => fmtMoney2(Number(t.recovered ?? 0)) },
        { label: "Net G/L",       tone: "muted",
          value: t => fmtMoney2(Number(t.net_gl ?? 0)) },
      ]}
      columns={[
        { label: "Status",    field: "status" },
        { label: "Count",     field: r => Number(r.count).toLocaleString(),     align: "right", mono: true },
        { label: "Amount",    field: r => fmtMoney2(Number(r.amount)),           align: "right", mono: true },
        { label: "Recovered", field: r => fmtMoney2(Number(r.recovered)),        align: "right", mono: true },
      ]}
    />
  );
}
