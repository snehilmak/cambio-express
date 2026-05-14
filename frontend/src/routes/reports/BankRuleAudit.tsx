import { useLocation } from "react-router-dom";

import { ReportDrilldown, fmtMoney } from "../../components/ReportDrilldown";

export default function BankRuleAudit() {
  const isOwner = useLocation().pathname.startsWith("/owner/");
  const baseRoute = isOwner ? "/owner/reports" : "/reports";
  return (
    <ReportDrilldown
      apiSlug="bank-rule-audit"
      title="Bank Rule Audit"
      resultUnit={["rule", "rules"]}
      backTo={baseRoute}
      csvUrl={`/api/v2/reports/bank-rule-audit.csv`}
      kpis={[
        { label: "Active Rules",  tone: "primary",
          value: t => Number(t.rules ?? 0).toLocaleString() },
        { label: "Auto-tagged",   tone: "neon",
          value: t => Number(t.count ?? 0).toLocaleString() },
        { label: "Total Amount",  tone: "muted",
          value: t => fmtMoney(Number(t.amount ?? 0)) },
      ]}
      columns={[
        { label: "Rule",   field: "label" },
        { label: "Target", field: "target" },
        { label: "Match",  field: "match",                                  mono: true },
        { label: "Count",  field: r => Number(r.count).toLocaleString(),    align: "right", mono: true },
        { label: "Amount", field: r => fmtMoney(Number(r.amount)),          align: "right", mono: true },
      ]}
    />
  );
}
