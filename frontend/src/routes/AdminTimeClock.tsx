import { useMemo, useState } from "react";

import { useAdminTimeClock } from "../api/timeclock";
import { useEmployees } from "../api/transfers";
import { useProfile, useStoreInfo } from "../api/account";
import { formatTimestamp } from "../lib/datetime";
import {
  Card, EmptyState, ErrorState, Field, Input, PageHeader,
  PageShell, Select, Table, TableSkeleton, tdStyle, thStyle,
} from "../components/ui";
import { getCurrentIdentity } from "../lib/auth";
import styles from "./AdminTimeClock.module.css";

// /app/admin/timeclock — payroll history view. Pick a date
// window + an optional roster filter; the table aggregates
// hours per row and prints a single total at the top. Open
// shifts show up in the rows (so admins can see who's still
// on the clock) but don't count toward the closed-period total.

export default function AdminTimeClock() {
  const identity = getCurrentIdentity();
  const roster   = useEmployees();
  const { data: profile }   = useProfile();
  const { data: storeInfo } = useStoreInfo();
  const userTz   = profile?.timezone ?? "";
  const storeTz  = storeInfo?.store?.timezone ?? "";

  // Default window: today and the prior 13 days (a typical
  // biweekly pay period). ``to`` is half-open per the API.
  const today = useMemo(() => new Date(), []);
  const [from, setFrom] = useState(() => _isoDate(_daysAgo(today, 13)));
  const [to,   setTo]   = useState(() =>
    _isoDate(_daysAgo(today, -1)));   // tomorrow
  const [empFilter, setEmpFilter] = useState<number | "">("");

  const data = useAdminTimeClock(
    from, to, empFilter === "" ? undefined : Number(empFilter),
  );

  const canView = identity?.role === "admin"
                  || identity?.role === "owner"
                  || identity?.role === "superadmin";

  if (!canView) {
    return (
      <PageShell>
        <PageHeader title="Payroll history" />
        <EmptyState title="Admin or owner only." />
      </PageShell>
    );
  }

  return (
    <PageShell>
      <PageHeader
        title="Payroll history"
        subtitle="Shift entries within the selected window. Open shifts show but don't count toward closed-period hours."
      />

      <Card>
        <div className={styles.filterRow}>
          <Field label="From" style={{ minWidth: "10rem" }}>
            <Input
              type="date" value={from}
              onChange={(e) => setFrom(e.target.value)}
            />
          </Field>
          <Field label="To (exclusive)" style={{ minWidth: "10rem" }}>
            <Input
              type="date" value={to}
              onChange={(e) => setTo(e.target.value)}
            />
          </Field>
          <Field label="Employee" style={{ minWidth: "12rem" }}>
            <Select
              value={empFilter === "" ? "" : String(empFilter)}
              onChange={(e) => {
                const v = e.target.value;
                setEmpFilter(v === "" ? "" : Number(v));
              }}
            >
              <option value="">Everyone</option>
              {(roster.data?.employees ?? []).map((m) => (
                <option key={m.id} value={m.id}>{m.name}</option>
              ))}
            </Select>
          </Field>
        </div>
      </Card>

      <Card>
        <div className={styles.summaryRow}>
          <strong>Total hours</strong>
          <span className={styles.totalNumber}>
            {data.data ? data.data.total_hours.toFixed(2) : "—"}
          </span>
          <span className={styles.subtle}>
            ({data.data ? data.data.rows.length : 0} entries in window)
          </span>
        </div>

        {data.isLoading && <TableSkeleton rows={5} cols={4} />}
        {data.isError && (
          <ErrorState
            message="Couldn't load payroll history."
            onRetry={() => { void data.refetch(); }}
          />
        )}
        {data.data && data.data.rows.length === 0 && !data.isLoading && (
          <EmptyState title="No shifts in this window." />
        )}
        {data.data && data.data.rows.length > 0 && (
          <Table>
            <thead>
              <tr>
                {["Roster name", "Clock in", "Clock out", "Hours", "Notes"]
                  .map((h) => (
                    <th key={h} style={thStyle}>{h}</th>
                  ))}
              </tr>
            </thead>
            <tbody>
              {data.data.rows.map((r) => (
                <tr key={r.id}>
                  <td style={tdStyle}>{r.employee_name}</td>
                  <td style={tdStyle}>
                    <span className={styles.mono}>
                      {formatTimestamp(r.clock_in_at, {
                        userTimezone: userTz, storeTimezone: storeTz,
                      })}
                    </span>
                  </td>
                  <td style={tdStyle}>
                    <span className={styles.mono}>
                      {r.clock_out_at
                        ? formatTimestamp(r.clock_out_at, {
                            userTimezone: userTz, storeTimezone: storeTz,
                          })
                        : <em className={styles.openTag}>in progress</em>}
                    </span>
                  </td>
                  <td style={tdStyle}>
                    {r.hours_worked == null ? "—" : r.hours_worked.toFixed(2)}
                  </td>
                  <td style={tdStyle}>{r.notes || "—"}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </PageShell>
  );
}


function _isoDate(d: Date): string {
  const yy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yy}-${mm}-${dd}`;
}

function _daysAgo(anchor: Date, days: number): Date {
  const d = new Date(anchor);
  d.setDate(d.getDate() - days);
  return d;
}
