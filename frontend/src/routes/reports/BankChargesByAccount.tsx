import { useLocation } from "react-router-dom";

import { ReportDrilldown } from "../../components/ReportDrilldown";
import { fmtMoney2 } from "../../lib/formatters";

export default function BankChargesByAccount() {
  const isOwner = useLocation().pathname.startsWith("/owner/");
  const baseRoute = isOwner ? "/owner/reports" : "/reports";
  return (
    <ReportDrilldown
      apiSlug="bank-charges-by-account"
      title="Bank Charges by Account"
      resultUnit={["account", "accounts"]}
      backTo={baseRoute}
      csvUrl={`/api/v2/reports/bank-charges-by-account.csv`}
      kpis={[
        { label: "Total Charges", tone: "primary",
          value: t => fmtMoney2(Number(t.amount ?? 0)) },
        { label: "Charge Count",  tone: "neon",
          value: t => Number(t.count ?? 0).toLocaleString() },
      ]}
      columns={[
        { label: "Account", field: r =>
          `${r.account}${r.last4 ? ` ••${r.last4}` : ""}` },
        { label: "Count",   field: r => Number(r.count).toLocaleString(), align: "right", mono: true },
        { label: "Amount",  field: r => fmtMoney2(Number(r.amount)),       align: "right", mono: true },
        { label: "Avg",     field: r => fmtMoney2(Number(r.avg)),          align: "right", mono: true },
      ]}
    />
  );
}
