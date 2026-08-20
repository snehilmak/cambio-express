import { useLocation } from "react-router-dom";

import { ReportDrilldown } from "../../components/ReportDrilldown";
import { fmtMoney2 } from "../../lib/formatters";

export default function TopRecipients() {
  const isOwner = useLocation().pathname.startsWith("/owner/");
  const baseRoute = isOwner ? "/owner/reports" : "/reports";
  return (
    <ReportDrilldown
      apiSlug="top-recipients"
      title="Top Recipients"
      resultUnit={["recipient", "recipients"]}
      backTo={baseRoute}
      csvUrl={`/api/v2/reports/top-recipients.csv`}
      kpis={[
        { label: "Total Sent",      tone: "primary", value: t => fmtMoney2(Number(t.sent ?? 0)) },
        { label: "Transfer Count",  tone: "neon",    value: t => Number(t.count ?? 0).toLocaleString() },
        { label: "Total Fees",      tone: "muted",   value: t => fmtMoney2(Number(t.fees ?? 0)) },
      ]}
      columns={[
        { label: "Recipient",   field: "recipient" },
        { label: "Count",       field: r => r.count.toLocaleString(), align: "right", mono: true },
        { label: "Total Sent",  field: r => fmtMoney2(Number(r.sent)), align: "right", mono: true },
        { label: "Fees",        field: r => fmtMoney2(Number(r.fees)), align: "right", mono: true },
        { label: "Federal Tax", field: r => fmtMoney2(Number(r.tax)),  align: "right", mono: true },
        { label: "Average",         field: r => fmtMoney2(Number(r.avg)),  align: "right", mono: true },
      ]}
    />
  );
}
