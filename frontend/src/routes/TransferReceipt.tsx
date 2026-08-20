import { useEffect } from "react";
import { useParams, Link } from "react-router-dom";

import { useTransferReceipt } from "../api/transfers";
import { Button, ErrorState, Loading } from "../components/ui";
import styles from "./TransferReceipt.module.css";

// /app/transfers/{id}/receipt — printable transfer receipt.
//
// Layout:
//   ┌────────────────────────────────────────────────────────┐
//   │  [Logo]   Store name                  Tax ID           │
//   │           Address · Phone · Email                      │
//   ├────────────────────────────────────────────────────────┤
//   │  TRANSFER RECEIPT      Date · Confirm # · Status       │
//   ├────────────────────────────────────────────────────────┤
//   │  Sender:    Maria Lopez                                │
//   │             +1 5551112222                              │
//   │             123 Main St, Houston TX                    │
//   │                                                        │
//   │  Recipient: Juan Garcia                                │
//   │             +52 ... · Mexico                           │
//   ├────────────────────────────────────────────────────────┤
//   │  Service     Company       Amount    Fee   Tax  TOTAL  │
//   │  Money tx    Intermex      100.00   5.00  1.00 106.00 │
//   ├────────────────────────────────────────────────────────┤
//   │  Cashier signature:        Customer signature:         │
//   │  ____________________      ____________________        │
//   ├────────────────────────────────────────────────────────┤
//   │  {store.receipt_footer or default system footer}       │
//   └────────────────────────────────────────────────────────┘
//
// Print CSS hides everything except the receipt card so the
// operator's browser print dialog produces a clean page.

export default function TransferReceipt() {
  const { id } = useParams<{ id: string }>();
  const transferId = Number(id);
  const { data, isLoading, isError, error, refetch } =
    useTransferReceipt(transferId);

  // Set the document title so the browser's print preview filename
  // defaults to something readable. Reset on unmount.
  useEffect(() => {
    if (!data) return;
    const original = document.title;
    document.title = `Receipt ${data.transfer.confirm_number || `#${data.transfer.id}`} — ${data.store.name}`;
    return () => { document.title = original; };
  }, [data]);

  if (!Number.isFinite(transferId)) {
    return (
      <div className={styles.page}>
        <div className={styles.shellChrome}>
          <Link to="/transfers" className={styles.backLink}>
            ← Back to transfers
          </Link>
        </div>
        <ErrorState message="Invalid transfer id in URL." />
      </div>
    );
  }
  if (isLoading) {
    return (
      <div className={styles.page}>
        <div className={styles.shellChrome}>
          <Link to="/transfers" className={styles.backLink}>
            ← Back to transfers
          </Link>
        </div>
        <Loading />
      </div>
    );
  }
  if (isError || !data) {
    return (
      <div className={styles.page}>
        <div className={styles.shellChrome}>
          <Link to="/transfers" className={styles.backLink}>
            ← Back to transfers
          </Link>
        </div>
        <ErrorState
          message={
            error instanceof Error
              ? `Couldn't load receipt: ${error.message}`
              : "Couldn't load receipt."
          }
          onRetry={() => { void refetch(); }}
        />
      </div>
    );
  }

  const { store, transfer } = data;
  const total = transfer.total_collected.toFixed(2);

  return (
    <div className={styles.page}>
      {/* Chrome — hidden in print so only the receipt card prints. */}
      <div className={styles.shellChrome}>
        <Link to={`/transfers/${transfer.id}/edit`} className={styles.backLink}>
          ← Back to transfer
        </Link>
        <Button
          tone="primary"
          size="sm"
          onClick={() => window.print()}
        >
          Print receipt
        </Button>
      </div>

      <article className={styles.receipt} aria-label="Transfer receipt">
        <header className={styles.header}>
          {store.receipt_logo_url ? (
            <img
              src={store.receipt_logo_url}
              alt={store.name}
              className={styles.logo}
            />
          ) : (
            <div className={styles.wordmark}>{store.name}</div>
          )}
          <div className={styles.headerMeta}>
            {store.receipt_logo_url && (
              <div className={styles.storeName}>{store.name}</div>
            )}
            {store.address && (
              <div className={styles.storeLine}>{store.address}</div>
            )}
            <div className={styles.storeLine}>
              {[store.phone, store.email].filter(Boolean).join(" · ")}
            </div>
            {store.receipt_tax_id && (
              <div className={styles.storeLine}>
                Tax ID: {store.receipt_tax_id}
              </div>
            )}
          </div>
        </header>

        <div className={styles.titleBar}>
          <span className={styles.title}>Transfer Receipt</span>
          <span className={styles.meta}>
            {transfer.send_date}
            {transfer.confirm_number && (
              <> · Confirmation #{transfer.confirm_number}</>
            )}
            <> · {transfer.status}</>
          </span>
        </div>

        <section className={styles.parties}>
          <div>
            <h2 className={styles.partyHeading}>Sender</h2>
            <div className={styles.partyName}>{transfer.sender_name || "—"}</div>
            {transfer.sender_phone && (
              <div className={styles.partyLine}>
                {transfer.sender_phone_country} {transfer.sender_phone}
              </div>
            )}
            {transfer.sender_address && (
              <div className={styles.partyLine}>
                {transfer.sender_address}
              </div>
            )}
          </div>
          <div>
            <h2 className={styles.partyHeading}>Recipient</h2>
            <div className={styles.partyName}>{transfer.recipient_name || "—"}</div>
            {transfer.recipient_phone && (
              <div className={styles.partyLine}>{transfer.recipient_phone}</div>
            )}
            <div className={styles.partyLine}>{transfer.country}</div>
          </div>
        </section>

        <div style={{ overflowX: "auto" }}>
        <table className={styles.amounts}>
          <thead>
            <tr>
              <th>Service</th>
              <th>Company</th>
              <th className={styles.numCol}>Send amount</th>
              <th className={styles.numCol}>Fee</th>
              <th className={styles.numCol}>Federal tax</th>
              <th className={styles.numCol}>Total</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>{transfer.service_type}</td>
              <td>{transfer.company}</td>
              <td className={styles.numCol}>
                ${transfer.send_amount.toFixed(2)}
              </td>
              <td className={styles.numCol}>
                ${transfer.fee.toFixed(2)}
              </td>
              <td className={styles.numCol}>
                ${transfer.federal_tax.toFixed(2)}
              </td>
              <td className={`${styles.numCol} ${styles.totalCell}`}>
                ${total}
              </td>
            </tr>
          </tbody>
        </table>
        </div>

        <div className={styles.totalBlock}>
          <span className={styles.totalLabel}>Customer paid</span>
          <span className={styles.totalAmount}>${total}</span>
        </div>

        <section className={styles.signatures}>
          <div className={styles.signatureRow}>
            <span className={styles.signatureLine} />
            <span className={styles.signatureLabel}>
              Cashier{transfer.employee_name && ` (${transfer.employee_name})`}
            </span>
          </div>
          <div className={styles.signatureRow}>
            <span className={styles.signatureLine} />
            <span className={styles.signatureLabel}>
              Customer
            </span>
          </div>
        </section>

        <footer className={styles.footer}>
          {store.receipt_footer || (
            <>
              Funds will arrive at the destination country per the
              sending company's standard delivery window. Keep this
              receipt for your records.
            </>
          )}
          <div className={styles.footerMeta}>
            Powered by DineroBook
          </div>
        </footer>
      </article>
    </div>
  );
}
