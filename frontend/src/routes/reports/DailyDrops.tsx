import { useLocation } from "react-router-dom";

import { ReportDrilldown, fmtMoney } from "../../components/ReportDrilldown";

export default function DailyDrops() {
  const isOwner = useLocation().pathname.startsWith("/owner/");
  const baseRoute = isOwner ? "/owner/reports" : "/reports";
  return (
    <ReportDrilldown
      apiSlug="daily-drops"
      title="Daily Cash Drops"
      resultUnit={["day", "days"]}
      backTo={baseRoute}
      csvUrl={`/api/v2/reports/daily-drops.csv`}
      kpis={[
        { label: "Total Amount",  tone: "primary",
          value: t => fmtMoney(Number(t.amount ?? 0)) },
        { label: "Drop Count",    tone: "neon",
          value: t => Number(t.count ?? 0).toLocaleString() },
        { label: "Avg / Day",     tone: "muted",
          value: t => fmtMoney(Number(t.avg_per_day ?? 0)) },
      ]}
      columns={[
        { label: "Date",   field: r => fmtDate(r.date as string) },
        { label: "Count",  field: r => Number(r.count).toLocaleString(), align: "right", mono: true },
        { label: "Amount", field: r => fmtMoney(Number(r.amount)),       align: "right", mono: true },
      ]}
    />
  );
}

function fmtDate(iso: string): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString(undefined, {
    month: "2-digit", day: "2-digit", year: "2-digit",
  });
}
