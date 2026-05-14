import { useLocation } from "react-router-dom";

import { ReportDrilldown, fmtMoney } from "../../components/ReportDrilldown";

export default function CashierProductivity() {
  const isOwner = useLocation().pathname.startsWith("/owner/");
  const baseRoute = isOwner ? "/owner/reports" : "/reports";
  return (
    <ReportDrilldown
      apiSlug="cashier-productivity"
      title="Cashier Productivity"
      resultUnit={["cashier", "cashiers"]}
      backTo={baseRoute}
      csvUrl={`/api/v2/reports/cashier-productivity.csv`}
      kpis={[
        { label: "Total Sent",     tone: "primary", value: t => fmtMoney(Number(t.sent ?? 0)) },
        { label: "Total Fees",     tone: "neon",    value: t => fmtMoney(Number(t.fees ?? 0)) },
        { label: "Total Fed Tax",  tone: "muted",   value: t => fmtMoney(Number(t.tax ?? 0)) },
        { label: "Transfer Count", tone: "muted",   value: t => Number(t.count ?? 0).toLocaleString() },
      ]}
      columns={[
        {
          label: "Cashier",
          field: r => (
            <span>
              {r.cashier as string}
              {(r as unknown as { is_active: boolean }).is_active === false && (
                <span style={{
                  marginLeft: "0.5rem",
                  fontSize: "0.7rem",
                  color: "var(--db-text-muted, #a3a3a3)",
                }}>
                  (inactive)
                </span>
              )}
            </span>
          ),
        },
        { label: "Count",       field: r => r.count.toLocaleString(), align: "right", mono: true },
        { label: "Total Sent",  field: r => fmtMoney(Number(r.sent)), align: "right", mono: true },
        { label: "Fees",        field: r => fmtMoney(Number(r.fees)), align: "right", mono: true },
        { label: "Federal Tax", field: r => fmtMoney(Number(r.tax)),  align: "right", mono: true },
        { label: "Avg",         field: r => fmtMoney(Number(r.avg)),  align: "right", mono: true },
      ]}
    />
  );
}
