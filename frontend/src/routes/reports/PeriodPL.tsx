import { useLocation } from "react-router-dom";

import { ReportDrilldown } from "../../components/ReportDrilldown";
import { fmtMoney2 } from "../../lib/formatters";

export default function PeriodPL() {
  const isOwner = useLocation().pathname.startsWith("/owner/");
  const baseRoute = isOwner ? "/owner/reports" : "/reports";
  return (
    <ReportDrilldown
      apiSlug="period-pl"
      title="Period P&L"
      resultUnit={["line", "lines"]}
      backTo={baseRoute}
      csvUrl={`/api/v2/reports/period-pl.csv`}
      kpis={[
        { label: "Revenue",   tone: "primary",
          value: t => fmtMoney2(Number(t.revenue ?? 0)) },
        { label: "Expenses",  tone: "muted",
          value: t => fmtMoney2(Number(t.expenses ?? 0)) },
        { label: "Net Income", tone: "neon",
          value: t => fmtMoney2(Number(t.net_income ?? 0)) },
      ]}
      columns={[
        { label: "Line",   field: "label" },
        { label: "Amount", field: r => fmtMoney2(Number(r.amount ?? 0)), align: "right", mono: true },
        { label: "Note",   field: r => (r.note as string) || "" },
      ]}
    />
  );
}
