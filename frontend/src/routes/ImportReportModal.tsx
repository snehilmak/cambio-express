import { useState } from "react";

import { Alert, Button, Loading, Modal, Pill } from "../components/ui";
import { ApiError } from "../lib/api";
import {
  commitIntermexReport,
  parseIntermexReport,
  type IntermexCommit,
  type IntermexReport,
} from "../api/reportImport";
import styles from "./ImportReportModal.module.css";

// Daily-book "Import Intermex report" flow.  Upload the company's
// "Reporte de cierre del día" PDF → the backend parses it IN MEMORY
// (nothing stored) → we show the extracted rows for review → Commit
// aggregates the settled giros into the day's money-transfer breakdown
// (the Intermex company row) and reports how it reconciles against the
// transfers already logged.  The PDF is re-parsed server-side on
// commit — the client never sends money numbers.

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
  open, onClose, storeId, reportDate, onCommitted,
}: {
  open: boolean;
  onClose: () => void;
  /** Store whose daily book is being edited. */
  storeId: number;
  /** The day being edited (YYYY-MM-DD) — used to warn if the report's
   *  own date doesn't match, and the day the giros commit to. */
  reportDate: string;
  /** Called after a successful commit so the editor re-fetches the
   *  daily report (its money-transfer total changed). */
  onCommitted?: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<IntermexReport | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [fileName, setFileName] = useState("");
  const [committing, setCommitting] = useState(false);
  const [committed, setCommitted] = useState<IntermexCommit | null>(null);

  function reset() {
    setResult(null); setErr(null); setBusy(false); setFileName("");
    setFile(null); setCommitting(false); setCommitted(null);
  }

  async function handleFile(f: File) {
    setErr(null); setResult(null); setCommitted(null); setBusy(true);
    setFileName(f.name); setFile(f);
    try {
      setResult(await parseIntermexReport(f));
    } catch (e) {
      setErr(humanize(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleCommit() {
    if (!file || committing) return;
    setErr(null); setCommitting(true);
    try {
      const res = await commitIntermexReport(file, storeId, reportDate);
      setCommitted(res);
      onCommitted?.();
    } catch (e) {
      setErr(humanize(e));
    } finally {
      setCommitting(false);
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
            Money transfers · {result.giros.length}
          </div>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Transfer #</th>
                  <th className={styles.num}>Send</th>
                  <th className={styles.num}>Fee</th>
                  <th className={styles.num}>Federal tax</th>
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

          {committed && (
            <Alert tone={committed.matches_logged ? "success" : "warning"}>
              Committed {committed.giros_committed} giro
              {committed.giros_committed === 1 ? "" : "s"} to{" "}
              <strong>{committed.company}</strong> for {reportDate}:{" "}
              <strong>{money(committed.amount)}</strong> sent ·{" "}
              {money(committed.fees)} fees · {money(committed.federal_tax)}{" "}
              fed. tax.
              {committed.matches_logged
                ? " Matches the transfers already logged for this day."
                : ` Heads up — you have ${money(committed.logged_amount)} ` +
                  "logged as Intermex transfers for this day; the report " +
                  "total is now the money-transfer figure."}
            </Alert>
          )}

          {err && <Alert tone="error">{err}</Alert>}

          <div className={styles.actions}>
            <Button tone="secondary" onClick={reset} disabled={committing}>
              Import another
            </Button>
            {committed ? (
              <Button
                tone="primary"
                onClick={() => { reset(); onClose(); }}
              >
                Done
              </Button>
            ) : (
              <Button
                tone="primary"
                busy={committing}
                disabled={committing || !result.all_reconcile}
                title={result.all_reconcile
                  ? undefined
                  : "The giros must reconcile before committing"}
                onClick={() => void handleCommit()}
              >
                {committing ? "Committing…" : "Commit to money transfers"}
              </Button>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}
