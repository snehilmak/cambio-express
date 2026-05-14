import { useLocation } from "react-router-dom";

import { ReportDrilldown, fmtMoney } from "../../components/ReportDrilldown";

export default function AchVolume() {
  const isOwner = useLocation().pathname.startsWith("/owner/");
  const baseRoute = isOwner ? "/owner/reports" : "/reports";
  return (
    <ReportDrilldown
      apiSlug="ach-volume"
      title="ACH Volume by Company"
      resultUnit={["company", "companies"]}
      backTo={baseRoute}
      csvUrl={`/api/v2/reports/ach-volume.csv`}
      kpis={[
        { label: "Total ACH",   tone: "primary",
          value: t => fmtMoney(Number(t.amount ?? 0)) },
        { label: "Batch Count", tone: "neon",
          value: t => Number(t.count ?? 0).toLocaleString() },
      ]}
      columns={[
        { label: "Company",     field: "company" },
        { label: "Batch Count", field: r => Number(r.count).toLocaleString(),  align: "right", mono: true },
        { label: "Total ACH",   field: r => fmtMoney(Number(r.amount)),        align: "right", mono: true },
        { label: "Avg / Batch", field: r => fmtMoney(Number(r.avg)),           align: "right", mono: true },
      ]}
    />
  );
}
