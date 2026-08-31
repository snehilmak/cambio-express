import type {
  PurchasesBlock, SalesBlock, TransfersRollup,
} from "../api/dashboard";
import {
  Card, Section, Table, tdStyle, thStyle, tokens,
} from "./ui";
import { fmtMoney2 } from "../lib/formatters";

// The at-a-glance period table (D-5): the same four windows down
// the side, one column per thing the store measures.
//
// Columns appear only when their module is on, so an MSB-only
// store sees Transfers alone and a c-store without money services
// never sees an empty Transfers column. If nothing qualifies the
// whole section is absent rather than an empty table.
//
// The windows are the ones the blocks already compute — no second
// definition of "last 7 days" that could drift from the first.

const WINDOWS = [
  { key: "today", label: "Last 24 hrs" },
  { key: "d7", label: "7 days" },
  { key: "d15", label: "15 days" },
  { key: "d30", label: "30 days" },
] as const;

type WindowKey = (typeof WINDOWS)[number]["key"];

export function PeriodRollup({
  sales, purchases, transfers,
}: {
  sales: SalesBlock | null;
  purchases: PurchasesBlock | null;
  transfers: TransfersRollup | null;
}) {
  const columns: Array<{
    label: string;
    values: Record<WindowKey, number>;
  }> = [];
  if (sales) {
    columns.push({
      label: "Sales",
      values: {
        today: sales.today, d7: sales.d7, d15: sales.d15, d30: sales.d30,
      },
    });
  }
  if (purchases) {
    columns.push({
      label: "Purchases",
      values: {
        today: purchases.today, d7: purchases.d7,
        d15: purchases.d15, d30: purchases.d30,
      },
    });
  }
  if (transfers) {
    columns.push({
      label: "Transfers",
      values: {
        today: transfers.today, d7: transfers.d7,
        d15: transfers.d15, d30: transfers.d30,
      },
    });
  }
  if (columns.length === 0) return null;

  return (
    <Section title="By period">
      <Card>
        <Table>
          <thead>
            <tr>
              <th style={thStyle}>Days</th>
              {columns.map((c) => (
                <th key={c.label} style={thStyle}>{c.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {WINDOWS.map((w) => (
              <tr key={w.key}>
                <td style={tdStyle}>{w.label}</td>
                {columns.map((c) => (
                  <td
                    key={c.label}
                    style={{ ...tdStyle, fontFamily: tokens.fontMono }}
                  >
                    {fmtMoney2(c.values[w.key])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
    </Section>
  );
}
