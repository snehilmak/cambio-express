import { useLocation } from "react-router-dom";

import { ReportDrilldown, fmtMoney } from "../../components/ReportDrilldown";
import { fmtDateCompact } from "../../lib/formatters";

export default function CancelledTransfers() {
  const isOwner = useLocation().pathname.startsWith("/owner/");
  const baseRoute = isOwner ? "/owner/reports" : "/reports";
  return (
    <ReportDrilldown
      apiSlug="cancelled-transfers"
      title="Cancelled & Rejected Transfers"
      resultUnit={["transfer", "transfers"]}
      backTo={baseRoute}
      csvUrl={`/api/v2/reports/cancelled-transfers.csv`}
      kpis={[
        { label: "Total",        tone: "primary",
          value: t => Number(t.count ?? 0).toLocaleString() },
        { label: "Canceled",     tone: "muted",
          value: t => Number(t.canceled ?? 0).toLocaleString() },
        { label: "Rejected",     tone: "muted",
          value: t => Number(t.rejected ?? 0).toLocaleString() },
        { label: "Total Amount", tone: "muted",
          value: t => fmtMoney(Number(t.amount ?? 0)) },
      ]}
      columns={[
        { label: "Date",        field: r => fmtDateCompact(r.send_date as string) },
        { label: "Sender",      field: "sender_name" },
        { label: "Recipient",   field: "recipient_name" },
        { label: "Country",     field: "country" },
        { label: "Company",     field: "company" },
        { label: "Status",      field: "status" },
        { label: "Send Amount", field: r => fmtMoney(Number(r.amount)), align: "right", mono: true },
        { label: "Notes",       field: "status_notes" },
        { label: "Confirm #",   field: "confirm", mono: true },
      ]}
    />
  );
}

