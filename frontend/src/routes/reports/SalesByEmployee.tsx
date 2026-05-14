import { useLocation } from "react-router-dom";

import { ReportDrilldown, fmtMoney } from "../../components/ReportDrilldown";

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
        { label: "Total Sent",     tone: "primary", value: t => fmtMoney(Number(t.sent ?? 0)) },
        { label: "Total Fees",     tone: "neon",    value: t => fmtMoney(Number(t.fees ?? 0)) },
        { label: "Total Fed Tax",  tone: "muted",   value: t => fmtMoney(Number(t.tax ?? 0)) },
        { label: "Transfer Count", tone: "muted",   value: t => Number(t.count ?? 0).toLocaleString() },
      ]}
      columns={[
        { label: "Employee",    field: "employee" },
        { label: "Count",       field: r => r.count.toLocaleString(), align: "right", mono: true },
        { label: "Total Sent",  field: r => fmtMoney(Number(r.sent)), align: "right", mono: true },
        { label: "Fees",        field: r => fmtMoney(Number(r.fees)), align: "right", mono: true },
        { label: "Federal Tax", field: r => fmtMoney(Number(r.tax)),  align: "right", mono: true },
        { label: "Avg",         field: r => fmtMoney(Number(r.avg)),  align: "right", mono: true },
      ]}
    />
  );
}
