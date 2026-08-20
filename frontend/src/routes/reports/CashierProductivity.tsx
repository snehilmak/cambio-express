import { useLocation } from "react-router-dom";

import { ReportDrilldown } from "../../components/ReportDrilldown";
import { fmtMoney2 } from "../../lib/formatters";
import { fontSize, tokens } from "../../components/ui";

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
        { label: "Total Sent",     tone: "primary", value: t => fmtMoney2(Number(t.sent ?? 0)) },
        { label: "Total Fees",     tone: "neon",    value: t => fmtMoney2(Number(t.fees ?? 0)) },
        { label: "Total federal tax",  tone: "muted",   value: t => fmtMoney2(Number(t.tax ?? 0)) },
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
                  fontSize: fontSize.xs,
                  color: tokens.textMuted,
                }}>
                  (inactive)
                </span>
              )}
            </span>
          ),
        },
        { label: "Count",       field: r => r.count.toLocaleString(), align: "right", mono: true },
        { label: "Total Sent",  field: r => fmtMoney2(Number(r.sent)), align: "right", mono: true },
        { label: "Fees",        field: r => fmtMoney2(Number(r.fees)), align: "right", mono: true },
        { label: "Federal Tax", field: r => fmtMoney2(Number(r.tax)),  align: "right", mono: true },
        { label: "Average",         field: r => fmtMoney2(Number(r.avg)),  align: "right", mono: true },
      ]}
    />
  );
}
