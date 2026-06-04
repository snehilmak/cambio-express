import { useLocation } from "react-router-dom";

import { ReportDrilldown } from "../../components/ReportDrilldown";
import { fmtMoney2 } from "../../lib/formatters";
import { fmtDateCompact } from "../../lib/formatters";

export default function CheckDeposits() {
  const isOwner = useLocation().pathname.startsWith("/owner/");
  const baseRoute = isOwner ? "/owner/reports" : "/reports";
  return (
    <ReportDrilldown
      apiSlug="check-deposits"
      title="Check Deposits"
      resultUnit={["day", "days"]}
      backTo={baseRoute}
      csvUrl={`/api/v2/reports/check-deposits.csv`}
      kpis={[
        { label: "Total Amount", tone: "primary",
          value: t => fmtMoney2(Number(t.amount ?? 0)) },
        { label: "Deposit Count", tone: "neon",
          value: t => Number(t.count ?? 0).toLocaleString() },
        { label: "Avg / Day",    tone: "muted",
          value: t => fmtMoney2(Number(t.avg_per_day ?? 0)) },
      ]}
      columns={[
        { label: "Date",   field: r => fmtDateCompact(r.date as string) },
        { label: "Count",  field: r => Number(r.count).toLocaleString(), align: "right", mono: true },
        { label: "Amount", field: r => fmtMoney2(Number(r.amount)),       align: "right", mono: true },
      ]}
    />
  );
}

