import { useParams, useSearchParams } from "react-router-dom";

import { usePaystub } from "../api/timeclock";
import { useProfile, useStoreInfo } from "../api/account";
import { formatTimestamp } from "../lib/datetime";
import {
  Button, ErrorState, Loading, PageShell,
} from "../components/ui";
import { getCurrentIdentity } from "../lib/auth";
import styles from "./TimeClockPaystub.module.css";

// /app/admin/timeclock/paystub/:id?from=YYYY-MM-DD&to=YYYY-MM-DD
//
// Printable paystub for one roster member. The page renders a
// clean letter-sized sheet (SPA chrome stripped via print CSS)
// summarising approved hours × hourly rate = gross pay, with
// every shift in the window itemised below for cross-check.

export default function TimeClockPaystub() {
  const { id } = useParams<{ id: string }>();
  const empId = id ? Number(id) : NaN;
  const [sp] = useSearchParams();
  const from = sp.get("from") ?? "";
  const to   = sp.get("to") ?? "";

  const identity = getCurrentIdentity();
  const { data: profile }   = useProfile();
  const { data: storeInfo } = useStoreInfo();
  const userTz   = profile?.timezone ?? "";
  const storeTz  = storeInfo?.store?.timezone ?? "";

  const canView = identity?.role === "admin"
                  || identity?.role === "owner"
                  || identity?.role === "superadmin";

  const { data, isLoading, isError, error, refetch } = usePaystub(
    Number.isFinite(empId) ? empId : null, from, to,
  );

  if (!canView) {
    return (
      <PageShell>
        <ErrorState
          message="Admin or owner only."
          onRetry={() => { void refetch(); }}
        />
      </PageShell>
    );
  }

  if (!from || !to) {
    return (
      <PageShell>
        <ErrorState
          message="Paystub URL needs ?from=YYYY-MM-DD&to=YYYY-MM-DD query params."
          onRetry={() => { void refetch(); }}
        />
      </PageShell>
    );
  }

  if (isLoading) {
    return <PageShell><Loading /></PageShell>;
  }
  if (isError || !data) {
    return (
      <PageShell>
        <ErrorState
          message={error instanceof Error
            ? error.message
            : "Couldn't load paystub."}
          onRetry={() => { void refetch(); }}
        />
      </PageShell>
    );
  }

  const storeName = storeInfo?.store?.name ?? "Store";

  return (
    <PageShell maxWidth="48rem">
      <div className={styles.printbar}>
        <Button onClick={() => window.print()} tone="primary">
          Print
        </Button>
        <Button tone="secondary" onClick={() => window.history.back()}>
          Back
        </Button>
      </div>

      <div className={styles.paystub}>
        <div className={styles.header}>
          <div>
            <div className={styles.headerLeft}>Paystub</div>
            <div className={styles.headerSub}>
              {storeName} · pay period {data.from_date} → {data.to_date}
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontWeight: 600 }}>{data.employee_name}</div>
            <div className={styles.headerSub}>
              Roster #{data.store_employee_id}
            </div>
          </div>
        </div>

        <div className={styles.summaryGrid}>
          <div className={styles.summaryTile}>
            <div className={styles.summaryLabel}>Approved hours</div>
            <div className={styles.summaryValue}>
              {data.approved_hours.toFixed(2)}
            </div>
          </div>
          <div className={styles.summaryTile}>
            <div className={styles.summaryLabel}>Hourly rate</div>
            <div className={styles.summaryValue}>
              {data.hourly_rate > 0
                ? `$${data.hourly_rate.toFixed(2)}`
                : "—"}
            </div>
          </div>
          <div className={styles.summaryTile}>
            <div className={styles.summaryLabel}>Gross pay</div>
            <div
              className={`${styles.summaryValue} ${styles.grossPay}`}
            >
              {data.hourly_rate > 0
                ? `$${data.gross_pay.toFixed(2)}`
                : "—"}
            </div>
          </div>
        </div>

        <div className={styles.shiftsWrap}>
          <table className={styles.shifts}>
            <thead>
              <tr>
                <th>Time in</th>
              <th>Time out</th>
              <th>Hours</th>
              <th>Status</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            {data.shifts.length === 0 && (
              <tr>
                <td colSpan={5}>
                  <em>No shifts in this window.</em>
                </td>
              </tr>
            )}
            {data.shifts.map((s) => (
              <tr key={s.id}>
                <td className={styles.mono}>
                  {formatTimestamp(s.clock_in_at, {
                    userTimezone: userTz, storeTimezone: storeTz,
                  })}
                </td>
                <td className={styles.mono}>
                  {s.clock_out_at
                    ? formatTimestamp(s.clock_out_at, {
                        userTimezone: userTz, storeTimezone: storeTz,
                      })
                    : "—"}
                </td>
                <td className={styles.mono}>
                  {s.hours_worked == null
                    ? "—"
                    : s.hours_worked.toFixed(2)}
                </td>
                <td className={`${styles.mono} ${_statusClass(s.status)}`}>
                  {s.status}
                </td>
                <td>{s.notes || "—"}</td>
              </tr>
            ))}
          </tbody>
          </table>
        </div>

        <div className={styles.footer}>
          Only <strong>approved</strong> shifts count toward gross pay.
          Pending / rejected / open rows appear in the itemised list
          so the operator can spot anything the admin still needs to
          review. Generated {new Date().toLocaleString()}.
        </div>
      </div>
    </PageShell>
  );
}


function _statusClass(s: string): string {
  if (s === "approved") return styles.statusApproved;
  if (s === "rejected") return styles.statusRejected;
  return styles.statusPending;
}
