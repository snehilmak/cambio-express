import { Link } from "react-router-dom";

import type {
  ReceiptRow, RegisterActivityBlock,
} from "../api/dashboard";
import {
  Card, KpiCard, KpiGrid, Pill, Section, tokens,
} from "./ui";
import { fmtMoney2 } from "../lib/formatters";
import { formatTimestamp } from "../lib/datetime";
import styles from "./RegisterActivity.module.css";

// What the register did (D-4) — the numbers a manager scans for
// trouble. Shared by the admin and employee dashboards; a cashier
// seeing the void count on their own shift should not have to ask.
//
// The block renders nothing at all when the store has never booked
// a day from a POS: an empty "0 receipts" panel would read as a
// broken register rather than as "you key your book by hand".

export function RegisterActivityTiles({
  register,
}: {
  register: RegisterActivityBlock | null;
}) {
  if (!register) return null;
  const hasFuel = register.fuel_gallons > 0 || register.fuel_sales > 0;
  return (
    <KpiGrid>
      <KpiCard
        label="Receipts"
        value={register.receipts.toLocaleString()}
        sub={
          <Link to="/transactions" className="ds-link"
            style={{ color: tokens.accent }}
          >
            {register.is_today ? "Today" : register.date} →
          </Link>
        }
      />
      <KpiCard
        label="Total rung"
        value={fmtMoney2(register.total_rung)}
        tone="positive"
      />
      <KpiCard
        label="Voided tickets"
        value={register.voided_tickets.toLocaleString()}
        sub={
          register.voided_tickets > 0 ? (
            <Link to="/transactions?voided=1" className="ds-link"
              style={{ color: tokens.accent }}
            >
              Review them →
            </Link>
          ) : "None"
        }
        tone={register.voided_tickets > 0 ? "warning" : "positive"}
      />
      <KpiCard
        label="Refunds"
        value={register.refunds.toLocaleString()}
        tone={register.refunds > 0 ? "warning" : "positive"}
      />
      {hasFuel && (
        <>
          <KpiCard
            label="Fuel gallons"
            value={register.fuel_gallons.toLocaleString(undefined, {
              maximumFractionDigits: 2,
            })}
          />
          <KpiCard
            label="Fuel sales"
            value={fmtMoney2(register.fuel_sales)}
            tone="positive"
          />
        </>
      )}
    </KpiGrid>
  );
}

export function RecentReceipts({ receipts }: { receipts: ReceiptRow[] }) {
  if (receipts.length === 0) return null;
  return (
    <Section
      title="Latest receipts"
      actions={
        <Link to="/transactions" className="ds-link"
          style={{ color: tokens.accent }}
        >
          All transactions →
        </Link>
      }
    >
      <div className={styles.grid}>
        {receipts.map((r) => (
          <Link
            key={r.id}
            to={`/transactions/${r.id}`}
            className={styles.receiptLink}
          >
            <Card className={styles.receipt}>
              <div className={styles.receiptHead}>
                <span className={styles.receiptNo}>
                  {r.transaction_no || `#${r.id}`}
                </span>
                {r.has_voided_line && <Pill tone="warning">void</Pill>}
              </div>
              <dl className={styles.receiptBody}>
                <div className={styles.receiptRow}>
                  <dt>Cashier</dt>
                  <dd>{r.cashier_id || "—"}</dd>
                </div>
                <div className={styles.receiptRow}>
                  <dt>Register</dt>
                  <dd>{r.register_id || "—"}</dd>
                </div>
                <div className={styles.receiptRow}>
                  <dt>Total</dt>
                  <dd className={styles.receiptTotal}>
                    {fmtMoney2(r.total)}
                  </dd>
                </div>
              </dl>
              <div className={styles.receiptFoot}>
                {r.receipt_at
                  ? formatTimestamp(r.receipt_at)
                  : r.business_date}
              </div>
            </Card>
          </Link>
        ))}
      </div>
    </Section>
  );
}
