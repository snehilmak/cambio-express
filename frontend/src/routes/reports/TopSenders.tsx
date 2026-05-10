import { useLocation } from "react-router-dom";

import { ReportDrilldown, fmtMoney } from "../../components/ReportDrilldown";

export default function TopSenders() {
  // Same shape as Top Customers but sorted by transfer count rather
  // than total sent. Shares the API endpoint with sort_by=count.
  const isOwner = useLocation().pathname.startsWith("/owner/");
  const baseRoute = isOwner ? "/owner/reports" : "/reports";
  return (
    <ReportDrilldown
      apiSlug="top-customers"
      title="Top Senders"
      resultUnit={["sender", "senders"]}
      backTo={baseRoute}
      csvUrl={`${baseRoute}/top-senders.csv`}
      extraParams={{ sort_by: "count" }}
      kpis={[
        { label: "Total Sent",     tone: "primary", value: t => fmtMoney(t.sent) },
        { label: "Transfer Count", tone: "neon",    value: t => t.count.toLocaleString() },
        { label: "Total Fees",     tone: "muted",   value: t => fmtMoney(t.fees) },
      ]}
      columns={[
        { label: "Customer",    field: "customer" },
        { label: "Phone",       field: "phone",                       mono: true },
        { label: "Count",       field: r => r.count.toLocaleString(), align: "right", mono: true },
        { label: "Total Sent",  field: r => fmtMoney(Number(r.sent)), align: "right", mono: true },
        { label: "Fees",        field: r => fmtMoney(Number(r.fees)), align: "right", mono: true },
        { label: "Federal Tax", field: r => fmtMoney(Number(r.tax)),  align: "right", mono: true },
        { label: "Avg",         field: r => fmtMoney(Number(r.avg)),  align: "right", mono: true },
      ]}
    />
  );
}
