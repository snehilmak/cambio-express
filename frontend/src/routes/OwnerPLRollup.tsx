import { useSearchParams } from "react-router-dom";

import {
  useOwnerPLRollup,
  type OwnerPLRollupRow,
} from "../api/owner";
import {
  Card, Empty, inputStyle, monoStyle, PageHeader, PageShell, tokens,
} from "../components/ui";
import { getCurrentIdentity } from "../lib/auth";

// /app/owner/pl-rollup — side-by-side monthly P&L for every store
// in the owner umbrella. Mirrors the legacy /owner/pl-rollup view.

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

export default function OwnerPLRollup() {
  const identity = getCurrentIdentity();
  const [sp, setSP] = useSearchParams();

  const today = new Date();
  const year  = Number(sp.get("year")  ?? today.getFullYear());
  const month = Number(sp.get("month") ?? today.getMonth() + 1);

  const { data, isLoading, isError, error } = useOwnerPLRollup(year, month);

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(sp);
    if (value) next.set(key, value);
    else       next.delete(key);
    setSP(next, { replace: true });
  }

  function shiftMonth(delta: number) {
    let y = year; let m = month + delta;
    while (m > 12) { y += 1; m -= 12; }
    while (m < 1)  { y -= 1; m += 12; }
    const next = new URLSearchParams(sp);
    next.set("year", String(y));
    next.set("month", String(m));
    setSP(next, { replace: true });
  }

  const isOwner =
    identity?.role === "owner" || identity?.role === "superadmin";
  if (!isOwner) {
    return (
      <PageShell>
        <PageHeader title="P&L rollup" />
        <Empty>Sign in as an owner to view per-store P&L.</Empty>
      </PageShell>
    );
  }

  return (
    <PageShell maxWidth="82rem">
      <PageHeader
        title="P&L rollup"
        subtitle={
          data
            ? `${MONTHS[data.month - 1]} ${data.year} · ` +
              `${data.rows.length.toLocaleString()} stores`
            : "—"
        }
        actions={
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            <button
              type="button"
              onClick={() => shiftMonth(-1)}
              style={navBtn}
              aria-label="Previous month"
            >
              ←
            </button>
            <select
              value={month}
              onChange={(e) => setParam("month", e.target.value)}
              style={{ ...inputStyle, width: "auto" }}
            >
              {MONTHS.map((label, i) => (
                <option key={i + 1} value={i + 1}>{label}</option>
              ))}
            </select>
            <select
              value={year}
              onChange={(e) => setParam("year", e.target.value)}
              style={{ ...inputStyle, width: "auto" }}
            >
              {(data?.year_choices ?? [year]).map((y) => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => shiftMonth(1)}
              style={navBtn}
              aria-label="Next month"
            >
              →
            </button>
          </div>
        }
      />

      <Card>
        {isLoading && <Empty>Loading…</Empty>}
        {isError && (
          <Empty error>
            {error instanceof Error ? error.message : "Could not load"}
          </Empty>
        )}
        {data && data.rows.length === 0 && !isLoading && (
          <Empty>
            No stores connected — ask each store admin to redeem an
            owner-connect code.
          </Empty>
        )}
        {data && data.rows.length > 0 && (
          <Table rows={data.rows} totals={data.totals} />
        )}
      </Card>
    </PageShell>
  );
}

function Table({
  rows, totals,
}: {
  rows: OwnerPLRollupRow[];
  totals: { revenue: number; purchases: number; expenses: number;
            over_short: number; net: number };
}) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table
        style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.92rem" }}
      >
        <thead>
          <tr>
            {[
              ["Store",      "left"],
              ["Revenue",    "right"],
              ["Purchases",  "right"],
              ["Expenses",   "right"],
              ["Over/Short", "right"],
              ["Net",        "right"],
            ].map(([label, align], i) => (
              <th
                key={i}
                style={{ ...thStyle, textAlign: align as "left" | "right" }}
              >
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.store_id}>
              <td style={cellStyle}>
                <div style={{ fontWeight: 500 }}>{r.store_name}</div>
                <div
                  style={{
                    color: tokens.textMuted,
                    fontFamily: tokens.fontMono,
                    fontSize: "0.78rem",
                  }}
                >
                  {r.store_slug}
                  {!r.has_pl && (
                    <>
                      {" · "}
                      <span style={{ color: tokens.warning }}>
                        no P&L on file
                      </span>
                    </>
                  )}
                </div>
              </td>
              <Money value={r.revenue} />
              <Money value={r.purchases} />
              <Money value={r.expenses} />
              <Money value={r.over_short} signed />
              <Money value={r.net} signed bold />
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td style={{ ...cellStyle, fontWeight: 600 }}>Totals</td>
            <Money value={totals.revenue}   bold />
            <Money value={totals.purchases} bold />
            <Money value={totals.expenses}  bold />
            <Money value={totals.over_short} signed bold />
            <Money value={totals.net}        signed bold />
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function Money({
  value, signed, bold,
}: {
  value: number;
  /** Tint negative red, positive green. Used for over/short + net. */
  signed?: boolean;
  bold?: boolean;
}) {
  const color = signed
    ? value < 0
      ? tokens.negative
      : value > 0
        ? tokens.accent
        : tokens.textMuted
    : tokens.text;
  return (
    <td style={{ ...cellStyle, textAlign: "right" }}>
      <span
        style={{
          ...monoStyle,
          color,
          fontWeight: bold ? 600 : 400,
        }}
      >
        {signed && value > 0 ? "+" : ""}${value.toFixed(2)}
      </span>
    </td>
  );
}

const cellStyle: React.CSSProperties = {
  padding: "0.7rem 0.75rem",
  borderBottom: `1px solid ${tokens.borderSubtle}`,
};

const thStyle: React.CSSProperties = {
  padding: "0.6rem 0.75rem",
  color: tokens.textMuted,
  fontWeight: 500,
  fontSize: "0.78rem",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  borderBottom: `1px solid ${tokens.border}`,
};

const navBtn: React.CSSProperties = {
  background: "transparent",
  color: tokens.text,
  border: `1px solid ${tokens.border}`,
  borderRadius: "0.5rem",
  padding: "0.4rem 0.75rem",
  fontFamily: tokens.fontBody,
  fontSize: "1rem",
  cursor: "pointer",
};
