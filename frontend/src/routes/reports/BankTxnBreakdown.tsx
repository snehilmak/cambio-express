import { useLocation } from "react-router-dom";

import { ReportDrilldown, fmtMoney } from "../../components/ReportDrilldown";

export default function BankTxnBreakdown() {
  const isOwner = useLocation().pathname.startsWith("/owner/");
  const baseRoute = isOwner ? "/owner/reports" : "/reports";
  return (
    <ReportDrilldown
      apiSlug="bank-transactions-breakdown"
      title="Bank Transactions Breakdown"
      resultUnit={["category", "categories"]}
      backTo={baseRoute}
      csvUrl={`/api/v2/reports/bank-transactions-breakdown.csv`}
      kpis={[
        { label: "Inflows",          tone: "primary",
          value: t => fmtMoney(Number(t.inflow ?? 0)) },
        { label: "Outflows",         tone: "neon",
          value: t => fmtMoney(Number(t.outflow ?? 0)) },
        { label: "Net",              tone: "muted",
          value: t => fmtMoney(Number(t.amount ?? 0)) },
        { label: "Transaction Count", tone: "muted",
          value: t => Number(t.count ?? 0).toLocaleString() },
      ]}
      columns={[
        { label: "Category", field: "label" },
        { label: "Count",    field: r => Number(r.count).toLocaleString(), align: "right", mono: true },
        { label: "Signed",   field: r => fmtMoney(Number(r.signed)),       align: "right", mono: true },
        { label: "Amount",   field: r => fmtMoney(Number(r.amount)),       align: "right", mono: true },
      ]}
    />
  );
}
