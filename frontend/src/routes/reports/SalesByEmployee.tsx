import { useLocation } from "react-router-dom";

import { ReportDrilldown } from "../../components/ReportDrilldown";
import { fmtMoney2 } from "../../lib/formatters";

export default function SalesByEmployee() {
  const isOwner = useLocation().pathname.startsWith("/owner/");
  const baseRoute = isOwner ? "/owner/reports" : "/reports";
  return (
    <ReportDrilldown
      apiSlug="sales-by-employee"
      title="Sales by Employee"
      resultUnit={["employee", "employees"]}
      backTo={baseRoute}
      csvUrl={`/api/v2/reports/sales-by-employee.csv`}
      kpis={[
        { label: "Total Sent",     tone: "primary", value: t => fmtMoney2(Number(t.sent ?? 0)) },
        { label: "Total Fees",     tone: "neon",    value: t => fmtMoney2(Number(t.fees ?? 0)) },
        { label: "Total federal tax",  tone: "muted",   value: t => fmtMoney2(Number(t.tax ?? 0)) },
        { label: "Transfer Count", tone: "muted",   value: t => Number(t.count ?? 0).toLocaleString() },
      ]}
      columns={[
        { label: "Employee",    field: "employee" },
        { label: "Count",       field: r => r.count.toLocaleString(), align: "right", mono: true },
        { label: "Total Sent",  field: r => fmtMoney2(Number(r.sent)), align: "right", mono: true },
        { label: "Fees",        field: r => fmtMoney2(Number(r.fees)), align: "right", mono: true },
        { label: "Federal Tax", field: r => fmtMoney2(Number(r.tax)),  align: "right", mono: true },
        { label: "Average",         field: r => fmtMoney2(Number(r.avg)),  align: "right", mono: true },
      ]}
    />
  );
}
