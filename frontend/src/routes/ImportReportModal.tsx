import { useState } from "react";

import { Alert, Button, Loading, Modal, Pill } from "../components/ui";
import { ApiError } from "../lib/api";
import { parseIntermexReport, type IntermexReport } from "../api/reportImport";
import styles from "./ImportReportModal.module.css";

// Daily-book "Import Intermex report" flow.  Upload the company's
// "Reporte de cierre del día" PDF → the backend parses it IN MEMORY
// (nothing stored) → we show the extracted rows for review.  Writing
// the reviewed transfers into the day's money-transfer log is a
// follow-up; the Commit button is intentionally disabled here.

function money(n: number): string {
  return n.toLocaleString("en-US", {
    style: "currency", currency: "USD",
  });
}

function humanize(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return "Could not read the report.";
}

export function ImportReportModal({
  open, onClose, reportDate,
}: {
  open: boolean;
  onClose: () => void;
  /** The day being edited (YYYY-MM-DD) — used to warn if the report's
   *  own date doesn't match. */
  reportDate: string;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<IntermexReport | null>(null);
  const [fileName, setFileName] = useState("");

  function reset() {
    setResult(null); setErr(null); setBusy(false); setFileName("");
  }

  async function handleFile(file: File) {
    setErr(null); setResult(null); setBusy(true); setFileName(file.name);
    try {
      setResult(await parseIntermexReport(file));
    } catch (e) {
      setErr(humanize(e));
    } finally {
      setBusy(false);
    }
  }

  const dateMismatch =
    result?.report_date != null && result.report_date !== reportDate;

  return (
    <Modal
      open={open}
      title="Import Intermex report"
      size="lg"
      disabled={busy}
      onClose={() => { reset(); onClose(); }}
    >
      {!result && (
        <div className={styles.uploadPane}>
          <p className={styles.lead}>
            Upload the Intermex <em>“Reporte de cierre del día”</em> PDF.
            We read it on the spot and show you the transactions to
            review — the file isn’t stored.
          </p>
          <label className={styles.fileLabel}>
            <input
              type="file"
              accept="application/pdf,.pdf"
              disabled={busy}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void handleFile(f);
              }}
            />
          </label>
          {busy && <Loading />}
          {err && <Alert tone="error">{err}</Alert>}
        </div>
      )}

      {result && (
        <div className={styles.result}>
          <div className={styles.summaryRow}>
            <div>
              <div className={styles.agency}>{result.agency}</div>
              <div className={styles.sub}>
                {fileName} · report date{" "}
                <strong>{result.report_date ?? "—"}</strong>
              </div>
            </div>
            <Pill tone={result.all_reconcile ? "success" : "warning"} dot>
              {result.all_reconcile
                ? "All transfers reconcile"
                : "Review — totals don’t match"}
            </Pill>
          </div>

          {dateMismatch && (
            <Alert tone="warning">
              This report is dated <strong>{result.report_date}</strong>,
              but you’re editing <strong>{reportDate}</strong>. Make sure
              you’re on the right day before committing.
            </Alert>
          )}

          <div className={styles.sectionTitle}>
            Money transfers (Giros) · {result.giros.length}
          </div>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Giro #</th>
                  <th className={styles.num}>Send</th>
                  <th className={styles.num}>Fee</th>
                  <th className={styles.num}>Fed. tax</th>
                  <th className={styles.num}>Total</th>
                  <th>Cashier</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {result.giros.map((g) => (
                  <tr key={g.confirm_number}
                      className={g.cancelled ? styles.cancelled : undefined}>
                    <td className={styles.mono}>{g.confirm_number}</td>
                    <td className={`${styles.num} ${styles.mono}`}>{money(g.send_amount)}</td>
                    <td className={`${styles.num} ${styles.mono}`}>{money(g.fee)}</td>
                    <td className={`${styles.num} ${styles.mono}`}>{money(g.federal_tax)}</td>
                    <td className={`${styles.num} ${styles.mono}`}>{money(g.total_collected)}</td>
                    <td>{g.cashier || "—"}</td>
                    <td>
                      {g.cancelled ? <Pill tone="negative">Cancelled</Pill>
                        : g.replacement ? <Pill tone="info">Replacement</Pill>
                        : g.reconciles ? <Pill tone="success">OK</Pill>
                        : <Pill tone="warning">Check</Pill>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className={styles.otherCounts}>
            Also in this report: {result.money_orders.length} money order
            {result.money_orders.length === 1 ? "" : "s"} ·{" "}
            {result.bill_payments.length} bill payment
            {result.bill_payments.length === 1 ? "" : "s"}
            <span className={styles.soon}> (wired next)</span>
          </div>

          <div className={styles.actions}>
            <Button tone="secondary" onClick={reset}>
              Import another
            </Button>
            <Button tone="primary" disabled title="Coming next">
              Commit to transfer log
            </Button>
            <Pill tone="info">Review only — commit coming next</Pill>
          </div>
        </div>
      )}
    </Modal>
  );
}
