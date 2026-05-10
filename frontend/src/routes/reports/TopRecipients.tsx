import { useLocation } from "react-router-dom";

import { ReportDrilldown, fmtMoney } from "../../components/ReportDrilldown";

export default function TopRecipients() {
  const isOwner = useLocation().pathname.startsWith("/owner/");
  const baseRoute = isOwner ? "/owner/reports" : "/reports";
  return (
    <ReportDrilldown
      apiSlug="top-recipients"
      title="Top Recipients"
      resultUnit={["recipient", "recipients"]}
      backTo={baseRoute}
      csvUrl={`${baseRoute}/top-recipients.csv`}
      kpis={[
        { label: "Total Sent",      tone: "primary", value: t => fmtMoney(Number(t.sent ?? 0)) },
        { label: "Transfer Count",  tone: "neon",    value: t => Number(t.count ?? 0).toLocaleString() },
        { label: "Total Fees",      tone: "muted",   value: t => fmtMoney(Number(t.fees ?? 0)) },
      ]}
      columns={[
        { label: "Recipient",   field: "recipient" },
        { label: "Count",       field: r => r.count.toLocaleString(), align: "right", mono: true },
        { label: "Total Sent",  field: r => fmtMoney(Number(r.sent)), align: "right", mono: true },
        { label: "Fees",        field: r => fmtMoney(Number(r.fees)), align: "right", mono: true },
        { label: "Federal Tax", field: r => fmtMoney(Number(r.tax)),  align: "right", mono: true },
        { label: "Avg",         field: r => fmtMoney(Number(r.avg)),  align: "right", mono: true },
      ]}
    />
  );
}
