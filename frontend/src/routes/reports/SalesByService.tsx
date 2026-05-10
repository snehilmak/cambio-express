import { useLocation } from "react-router-dom";

import { ReportDrilldown, fmtMoney } from "../../components/ReportDrilldown";

export default function SalesByService() {
  // Flask slug: sales-by-service-type. API endpoint: sales-by-service.
  const isOwner = useLocation().pathname.startsWith("/owner/");
  const baseRoute = isOwner ? "/owner/reports" : "/reports";
  return (
    <ReportDrilldown
      apiSlug="sales-by-service"
      title="Sales by Service Type"
      resultUnit={["service type", "service types"]}
      backTo={baseRoute}
      csvUrl={`${baseRoute}/sales-by-service-type.csv`}
      kpis={[
        { label: "Total Sent",     tone: "primary", value: t => fmtMoney(Number(t.sent ?? 0)) },
        { label: "Total Fees",     tone: "neon",    value: t => fmtMoney(Number(t.fees ?? 0)) },
        { label: "Total Fed Tax",  tone: "muted",   value: t => fmtMoney(Number(t.tax ?? 0)) },
        { label: "Transfer Count", tone: "muted",   value: t => Number(t.count ?? 0).toLocaleString() },
      ]}
      columns={[
        { label: "Service Type", field: "service_type" },
        { label: "Count",        field: r => r.count.toLocaleString(), align: "right", mono: true },
        { label: "Total Sent",   field: r => fmtMoney(Number(r.sent)), align: "right", mono: true },
        { label: "Fees",         field: r => fmtMoney(Number(r.fees)), align: "right", mono: true },
        { label: "Federal Tax",  field: r => fmtMoney(Number(r.tax)),  align: "right", mono: true },
        { label: "Avg",          field: r => fmtMoney(Number(r.avg)),  align: "right", mono: true },
      ]}
    />
  );
}
