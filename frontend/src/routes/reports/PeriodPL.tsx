import { useLocation } from "react-router-dom";

import { ReportDrilldown, fmtMoney } from "../../components/ReportDrilldown";

export default function PeriodPL() {
  const isOwner = useLocation().pathname.startsWith("/owner/");
  const baseRoute = isOwner ? "/owner/reports" : "/reports";
  return (
    <ReportDrilldown
      apiSlug="period-pl"
      title="Period P&L"
      resultUnit={["line", "lines"]}
      backTo={baseRoute}
      csvUrl={`${baseRoute}/period-pl.csv`}
      kpis={[
        { label: "Revenue",   tone: "primary",
          value: t => fmtMoney(Number(t.revenue ?? 0)) },
        { label: "Expenses",  tone: "muted",
          value: t => fmtMoney(Number(t.expenses ?? 0)) },
        { label: "Net Income", tone: "neon",
          value: t => fmtMoney(Number(t.net_income ?? 0)) },
      ]}
      columns={[
        { label: "Line",   field: "label" },
        { label: "Amount", field: r => fmtMoney(Number(r.amount ?? 0)), align: "right", mono: true },
        { label: "Note",   field: r => (r.note as string) || "" },
      ]}
    />
  );
}
