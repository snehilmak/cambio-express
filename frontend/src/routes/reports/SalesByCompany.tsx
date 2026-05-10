import { useLocation } from "react-router-dom";

import { ReportDrilldown, fmtMoney } from "../../components/ReportDrilldown";

export default function SalesByCompany() {
  const isOwner = useLocation().pathname.startsWith("/owner/");
  const baseRoute = isOwner ? "/owner/reports" : "/reports";
  return (
    <ReportDrilldown
      apiSlug="sales-by-company"
      title="Sales by Company"
      resultUnit={["company", "companies"]}
      backTo={baseRoute}
      csvUrl={`${baseRoute}/sales-by-company.csv`}
      kpis={[
        { label: "Total Sent",     tone: "primary", value: t => fmtMoney(t.sent) },
        { label: "Total Fees",     tone: "neon",    value: t => fmtMoney(t.fees) },
        { label: "Total Fed Tax",  tone: "muted",   value: t => fmtMoney(t.tax) },
        { label: "Transfer Count", tone: "muted",   value: t => t.count.toLocaleString() },
      ]}
      columns={[
        { label: "Company",     field: "company" },
        { label: "Count",       field: r => r.count.toLocaleString(), align: "right", mono: true },
        { label: "Total Sent",  field: r => fmtMoney(Number(r.sent)), align: "right", mono: true },
        { label: "Fees",        field: r => fmtMoney(Number(r.fees)), align: "right", mono: true },
        { label: "Federal Tax", field: r => fmtMoney(Number(r.tax)),  align: "right", mono: true },
        { label: "Avg",         field: r => fmtMoney(Number(r.avg)),  align: "right", mono: true },
      ]}
    />
  );
}
