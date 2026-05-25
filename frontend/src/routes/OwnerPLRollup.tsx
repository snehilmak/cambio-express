import { useSearchParams } from "react-router-dom";

import {
  useOwnerPLRollup,
  type OwnerPLRollupRow,
} from "../api/owner";
import {
  Breadcrumbs,
  Button, Card, Empty, EmptyState, ErrorState, monoStyle, PageHeader,
  PageShell, Select, Table, TableSkeleton, tdStyle, thStyle,
} from "../components/ui";
import { getCurrentIdentity } from "../lib/auth";
import styles from "./OwnerPLRollup.module.css";

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

  const { data, isLoading, isError, error, refetch } = useOwnerPLRollup(year, month);

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
    <PageShell>

      <Breadcrumbs crumbs={[{ label: "Owner" }, { label: "P&L rollup" }]} />

      <PageHeader
        title="P&L rollup"
        subtitle={
          data
            ? `${MONTHS[data.month - 1]} ${data.year} · ` +
              `${data.rows.length.toLocaleString()} stores`
            : "—"
        }
        actions={
          <div className={styles.nav}>
            <Button
              tone="secondary"
              size="sm"
              onClick={() => shiftMonth(-1)}
              aria-label="Previous month"
            >
              ←
            </Button>
            <Select
              value={month}
              onChange={(e) => setParam("month", e.target.value)}
              style={{ width: "auto" }}
            >
              {MONTHS.map((label, i) => (
                <option key={i + 1} value={i + 1}>{label}</option>
              ))}
            </Select>
            <Select
              value={year}
              onChange={(e) => setParam("year", e.target.value)}
              style={{ width: "auto" }}
            >
              {(data?.year_choices ?? [year]).map((y) => (
                <option key={y} value={y}>{y}</option>
              ))}
            </Select>
            <Button
              tone="secondary"
              size="sm"
              onClick={() => shiftMonth(1)}
              aria-label="Next month"
            >
              →
            </Button>
          </div>
        }
      />

      <Card>
        {isLoading && <TableSkeleton rows={5} cols={5} />}
        {isError && (
          <ErrorState
            message={error instanceof Error ? error.message : "Could not load"}
            onRetry={() => { void refetch(); }}
          />
        )}
        {data && data.rows.length === 0 && !isLoading && (
          <EmptyState
            title="No stores connected"
            body="Ask each store admin to redeem an owner-connect code."
          />
        )}
        {data && data.rows.length > 0 && (
          <RollupTable rows={data.rows} totals={data.totals} />
        )}
      </Card>
    </PageShell>
  );
}

function RollupTable({
  rows, totals,
}: {
  rows: OwnerPLRollupRow[];
  totals: { revenue: number; purchases: number; expenses: number;
            over_short: number; net: number };
}) {
  return (
    <Table>
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
            <td style={tdStyle}>
              <div className={styles.storeName}>{r.store_name}</div>
              <div className={styles.storeSlug}>
                {r.store_slug}
                {!r.has_pl && (
                  <>
                    {" · "}
                    <span className={styles.noPL}>no P&L on file</span>
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
          <td style={tdStyle} className={styles.totalsLabel}>Totals</td>
          <Money value={totals.revenue}   bold />
          <Money value={totals.purchases} bold />
          <Money value={totals.expenses}  bold />
          <Money value={totals.over_short} signed bold />
          <Money value={totals.net}        signed bold />
        </tr>
      </tfoot>
    </Table>
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
  const colorClass = signed
    ? value < 0
      ? styles.moneyNeg
      : value > 0
        ? styles.moneyPos
        : styles.moneyZero
    : styles.moneyDefault;
  return (
    <td style={{ ...tdStyle, textAlign: "right" }}>
      <span
        className={`${colorClass} ${bold ? styles.bold : ""}`}
        style={monoStyle}
      >
        {signed && value > 0 ? "+" : ""}${value.toFixed(2)}
      </span>
    </td>
  );
}
