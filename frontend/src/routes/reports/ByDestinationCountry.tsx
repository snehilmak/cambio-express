import { useLocation } from "react-router-dom";

import { ReportDrilldown } from "../../components/ReportDrilldown";
import { fmtMoney2 } from "../../lib/formatters";

export default function ByDestinationCountry() {
  const isOwner = useLocation().pathname.startsWith("/owner/");
  const baseRoute = isOwner ? "/owner/reports" : "/reports";
  return (
    <ReportDrilldown
      apiSlug="by-destination-country"
      title="By Destination Country"
      resultUnit={["country", "countries"]}
      backTo={baseRoute}
      csvUrl={`/api/v2/reports/by-destination-country.csv`}
      kpis={[
        { label: "Total Sent",     tone: "primary", value: t => fmtMoney2(Number(t.sent ?? 0)) },
        { label: "Country Count",  tone: "neon",
          value: () => "" /* rows.length is shown in the result-unit chip already */ },
        { label: "Transfer Count", tone: "muted",   value: t => Number(t.count ?? 0).toLocaleString() },
        { label: "Total Fees",     tone: "muted",   value: t => fmtMoney2(Number(t.fees ?? 0)) },
      ]}
      columns={[
        { label: "Country",     field: "country" },
        { label: "Count",       field: r => Number(r.count).toLocaleString(), align: "right", mono: true },
        { label: "Total Sent",  field: r => fmtMoney2(Number(r.sent)),         align: "right", mono: true },
        { label: "Fees",        field: r => fmtMoney2(Number(r.fees)),         align: "right", mono: true },
        { label: "Federal Tax", field: r => fmtMoney2(Number(r.tax)),          align: "right", mono: true },
        { label: "Average",         field: r => fmtMoney2(Number(r.avg)),          align: "right", mono: true },
      ]}
    />
  );
}
