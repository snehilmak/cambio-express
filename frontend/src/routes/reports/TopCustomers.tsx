import { useLocation } from "react-router-dom";

import { ReportDrilldown } from "../../components/ReportDrilldown";
import { fmtMoney2 } from "../../lib/formatters";
import { maskPhone } from "../../lib/format";

export default function TopCustomers() {
  const isOwner = useLocation().pathname.startsWith("/owner/");
  const baseRoute = isOwner ? "/owner/reports" : "/reports";
  return (
    <ReportDrilldown
      apiSlug="top-customers"
      title="Top Customers by Volume"
      resultUnit={["customer", "customers"]}
      backTo={baseRoute}
      csvUrl={`/api/v2/reports/top-customers.csv`}
      kpis={[
        { label: "Total Sent",     tone: "primary", value: t => fmtMoney2(Number(t.sent ?? 0)) },
        { label: "Total Fees",     tone: "neon",    value: t => fmtMoney2(Number(t.fees ?? 0)) },
        { label: "Transfer Count", tone: "muted",   value: t => Number(t.count ?? 0).toLocaleString() },
      ]}
      columns={[
        { label: "Customer",    field: "customer" },
        { label: "Phone",       field: r => maskPhone(String(r.phone ?? "")), mono: true },
        { label: "Count",       field: r => r.count.toLocaleString(), align: "right", mono: true },
        { label: "Total Sent",  field: r => fmtMoney2(Number(r.sent)), align: "right", mono: true },
        { label: "Fees",        field: r => fmtMoney2(Number(r.fees)), align: "right", mono: true },
        { label: "Federal Tax", field: r => fmtMoney2(Number(r.tax)),  align: "right", mono: true },
        { label: "Avg",         field: r => fmtMoney2(Number(r.avg)),  align: "right", mono: true },
      ]}
    />
  );
}
