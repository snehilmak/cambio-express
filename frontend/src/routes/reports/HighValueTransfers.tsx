import { useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";

import { ReportDrilldown } from "../../components/ReportDrilldown";
import { fmtMoney2 } from "../../lib/formatters";
import { fontSize, tokens } from "../../components/ui";
import { fmtDateCompact } from "../../lib/formatters";

export default function HighValueTransfers() {
  const isOwner = useLocation().pathname.startsWith("/owner/");
  const baseRoute = isOwner ? "/owner/reports" : "/reports";
  const [params, setParams] = useSearchParams();
  const [threshold, setThreshold] = useState(() => params.get("threshold") || "1000");

  function commitThreshold(v: string) {
    setThreshold(v);
    const next = new URLSearchParams(params);
    next.set("threshold", v || "1000");
    setParams(next, { replace: true });
  }

  return (
    <>
      {/* Threshold control sits above the period filter on the
          underlying drilldown — for now a tiny extra-row affordance
          before the main drilldown body. */}
      <div style={{
        maxWidth: "75rem", margin: "1rem auto 0",
        padding: "0 1.5rem",
        display: "flex", gap: "0.5rem", alignItems: "flex-end",
      }}>
        <label style={{
          display: "flex", flexDirection: "column", gap: "0.15rem",
          fontSize: fontSize.xs,
          color: tokens.textMuted,
          textTransform: "uppercase", letterSpacing: "0.05em",
        }}>
          <span>Threshold ($)</span>
          <input
            type="number"
            min={0} step={100}
            value={threshold}
            onChange={e => commitThreshold(e.target.value)}
            style={{
              padding: "0.35rem 0.5rem",
              background: tokens.surface, color: "inherit",
              border: `1px solid ${tokens.border}`,
              borderRadius: "0.4rem", fontSize: "0.85rem",
            }}
          />
        </label>
      </div>

      <ReportDrilldown
        apiSlug="high-value-transfers"
        title="High Value Transfers"
        resultUnit={["transfer", "transfers"]}
        backTo={baseRoute}
        csvUrl={`/api/v2/reports/high-value-transfers.csv`}
        extraParams={{ threshold: threshold || "1000" }}
        kpis={[
          { label: `Above $${Number(threshold || 1000).toLocaleString()}`, tone: "primary",
            value: t => Number(t.count ?? 0).toLocaleString() },
          { label: "Total Volume", tone: "neon",
            value: t => fmtMoney2(Number(t.amount ?? 0)) },
          { label: "Total Fees", tone: "muted",
            value: t => fmtMoney2(Number(t.fees ?? 0)) },
          { label: "Federal Tax", tone: "muted",
            value: t => fmtMoney2(Number(t.tax ?? 0)) },
        ]}
        columns={[
          { label: "Date",        field: r => fmtDateCompact(r.send_date as string) },
          { label: "Sender",      field: "sender_name" },
          { label: "Recipient",   field: "recipient_name" },
          { label: "Country",     field: "country" },
          { label: "Company",     field: "company" },
          { label: "Send Amount", field: r => fmtMoney2(Number(r.amount)), align: "right", mono: true },
          { label: "Fee",         field: r => fmtMoney2(Number(r.fee)),    align: "right", mono: true },
          { label: "Federal Tax", field: r => fmtMoney2(Number(r.tax)),    align: "right", mono: true },
          { label: "Confirm #",   field: "confirm", mono: true },
        ]}
      />
    </>
  );
}

