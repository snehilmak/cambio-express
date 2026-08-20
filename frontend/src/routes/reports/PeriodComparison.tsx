import { useLocation } from "react-router-dom";

import { ReportDrilldown } from "../../components/ReportDrilldown";

// Period vs prior-period delta. Row shape: `label`, `current`,
// `prior`, `delta`, `pct`, `is_money`. KPIs surface the headline
// metrics (income / net / transfers) but the page's value is the
// row-by-row delta table.
export default function PeriodComparison() {
  const isOwner = useLocation().pathname.startsWith("/owner/");
  const baseRoute = isOwner ? "/owner/reports" : "/reports";
  return (
    <ReportDrilldown
      apiSlug="period-comparison"
      title="Period vs Prior Period"
      resultUnit={["metric", "metrics"]}
      backTo={baseRoute}
      csvUrl={`/api/v2/reports/period-comparison.csv`}
      kpis={[
        { label: "Current Period", tone: "primary",
          value: t => (t.current_label as string) || "—" },
        { label: "Prior Period",   tone: "muted",
          value: t => (t.prior_label as string) || "—" },
      ]}
      columns={[
        { label: "Metric",     field: "label" },
        { label: "Current",    field: r => fmtCell(r), align: "right", mono: true },
        { label: "Prior",      field: r => fmtCell(r, "prior"), align: "right", mono: true },
        { label: "Change",          field: r => fmtCell(r, "delta"),
          align: "right", mono: true },
        { label: "% Change",   field: r => `${(Number(r.pct ?? 0) * 100).toFixed(1)}%`,
          align: "right", mono: true },
      ]}
    />
  );
}

function fmtCell(row: Record<string, unknown>, key: string = "current"): string {
  const v = Number(row[key] ?? 0);
  if (row.is_money) {
    return `$${v.toLocaleString(undefined, {
      minimumFractionDigits: 2, maximumFractionDigits: 2,
    })}`;
  }
  return v.toLocaleString();
}
