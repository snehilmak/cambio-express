import { Fragment, useMemo, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  adminCreateEntry, adminDeleteEntry, adminUpdateEntry,
  useAdminTimeClock, useTimeClockHistory,
  type TimeClockEntryRow,
} from "../api/timeclock";
import { useEmployees } from "../api/transfers";
import { useProfile, useStoreInfo } from "../api/account";
import { ApiError } from "../lib/api";
import { formatTimestamp } from "../lib/datetime";
import {
  Alert, Button, Card, EmptyState, ErrorState, Field, Input,
  Loading, PageHeader, PageShell, Select, Table, TableSkeleton,
  Textarea, tdStyle, thStyle,
} from "../components/ui";
import { getCurrentIdentity } from "../lib/auth";
import styles from "./AdminTimeClock.module.css";

// /app/admin/timeclock — payroll history view. Admins can:
//   • Filter by date window + roster member
//   • Back-fill shifts (e.g. cashier forgot to punch)
//   • Edit timestamps / notes on any existing entry
//   • Delete entries (audit chain survives)
//   • Inspect the audit chain per entry (clock-in / -out /
//     admin edits, newest-first)

type ModalState =
  | { kind: "closed" }
  | { kind: "create" }
  | { kind: "edit"; row: TimeClockEntryRow };

export default function AdminTimeClock() {
  const identity      = getCurrentIdentity();
  const queryClient   = useQueryClient();
  const roster        = useEmployees();
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

  const [modal, setModal] = useState<ModalState>({ kind: "closed" });
  const [expandedHistoryId, setExpandedHistoryId] =
    useState<number | null>(null);

  const data = useAdminTimeClock(
    from, to, empFilter === "" ? undefined : Number(empFilter),
  );

  const canView = identity?.role === "admin"
                  || identity?.role === "owner"
                  || identity?.role === "superadmin";

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ["timeclock"] });
  }

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
        actions={(
          <Button onClick={() => setModal({ kind: "create" })}>
            + New entry
          </Button>
        )}
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

        {data.isLoading && <TableSkeleton rows={5} cols={6} />}
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
                {[
                  "Roster name", "Clock in", "Clock out",
                  "Hours", "Notes", "",
                ].map((h) => (
                  <th key={h} style={thStyle}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.data.rows.map((r) => (
                <Fragment key={r.id}>
                  <tr>
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
                      {r.hours_worked == null
                        ? "—"
                        : r.hours_worked.toFixed(2)}
                    </td>
                    <td style={tdStyle}>{r.notes || "—"}</td>
                    <td style={tdStyle}>
                      <div className={styles.rowActions}>
                        <Button
                          size="sm" tone="secondary"
                          onClick={() => setModal({ kind: "edit", row: r })}
                        >
                          Edit
                        </Button>
                        <Button
                          size="sm" tone="secondary"
                          onClick={() => setExpandedHistoryId(
                            expandedHistoryId === r.id ? null : r.id,
                          )}
                        >
                          {expandedHistoryId === r.id ? "Hide" : "History"}
                        </Button>
                        <DeleteEntryButton entryId={r.id} onDone={refresh} />
                      </div>
                    </td>
                  </tr>
                  {expandedHistoryId === r.id && (
                    <tr className={styles.historyRow}>
                      <td colSpan={6} style={tdStyle}>
                        <HistoryPanel entryId={r.id} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      {modal.kind !== "closed" && (
        <EntryModal
          state={modal}
          roster={roster.data?.employees ?? []}
          onClose={() => setModal({ kind: "closed" })}
          onSaved={() => {
            setModal({ kind: "closed" });
            refresh();
          }}
        />
      )}
    </PageShell>
  );
}


// ── History panel ───────────────────────────────────────────


function HistoryPanel({ entryId }: { entryId: number }) {
  const { data, isLoading, isError, refetch } =
    useTimeClockHistory(entryId);
  if (isLoading) return <Loading />;
  if (isError) {
    return (
      <ErrorState
        message="Couldn't load entry history."
        onRetry={() => { void refetch(); }}
      />
    );
  }
  if (!data || data.rows.length === 0) {
    return <span className={styles.subtle}>No history yet.</span>;
  }
  return (
    <ul className={styles.historyList}>
      {data.rows.map((h) => (
        <li key={h.id} className={styles.historyItem}>
          <div className={styles.historyHeader}>
            <span className={styles.historyAction}>{h.action}</span>
            <span>{_formatHistoryDate(h.at)}</span>
            <span className={styles.historyActor}>
              by {h.actor || "unknown"}{h.actor_role
                ? ` (${h.actor_role})` : ""}
            </span>
          </div>
          <div className={styles.historySummary}>{h.summary}</div>
        </li>
      ))}
    </ul>
  );
}


function _formatHistoryDate(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}


// ── Delete button ───────────────────────────────────────────


function DeleteEntryButton({
  entryId, onDone,
}: { entryId: number; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  async function onClick() {
    if (!window.confirm(
      "Delete this time-clock entry? The audit row will survive "
      + "so the history view keeps a record of the deletion.",
    )) return;
    setBusy(true);
    try {
      await adminDeleteEntry(entryId);
      onDone();
    } catch (e) {
      window.alert(
        e instanceof ApiError ? e.message : "Couldn't delete the entry.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <Button
      size="sm" tone="secondary"
      busy={busy} disabled={busy}
      onClick={onClick}
    >
      Delete
    </Button>
  );
}


// ── Create / edit modal ─────────────────────────────────────


interface RosterMember { id: number; name: string }

function EntryModal({
  state, roster, onClose, onSaved,
}: {
  state: ModalState;
  roster: RosterMember[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = state.kind === "edit";
  const row    = state.kind === "edit" ? state.row : null;

  const [empId, setEmpId] = useState<number | "">(
    row ? row.store_employee_id : (roster[0]?.id ?? ""),
  );
  const [clockIn, setClockIn]   = useState(
    row ? _toLocalInput(row.clock_in_at) : "",
  );
  const [clockOut, setClockOut] = useState(
    row && row.clock_out_at ? _toLocalInput(row.clock_out_at) : "",
  );
  const [notes, setNotes]   = useState(row?.notes ?? "");
  const [busy, setBusy]     = useState(false);
  const [err, setErr]       = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErr(null); setBusy(true);
    try {
      if (isEdit && row) {
        await adminUpdateEntry(row.id, {
          clock_in_at:  clockIn
            ? new Date(clockIn).toISOString()
            : undefined,
          clock_out_at: clockOut
            ? new Date(clockOut).toISOString()
            : null,
          notes,
        });
      } else {
        if (empId === "") {
          setErr("Pick a roster member.");
          setBusy(false); return;
        }
        await adminCreateEntry({
          store_employee_id: Number(empId),
          clock_in_at:  new Date(clockIn).toISOString(),
          clock_out_at: clockOut
            ? new Date(clockOut).toISOString()
            : null,
          notes,
        });
      }
      onSaved();
    } catch (e2) {
      setErr(
        e2 instanceof ApiError ? e2.message : "Couldn't save the entry.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.modalBackdrop} onClick={onClose}>
      <div
        className={styles.modalCard}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 style={{ margin: 0 }}>
          {isEdit ? "Edit entry" : "New entry"}
        </h2>
        <form onSubmit={onSubmit}>
          <div className={styles.modalGrid}>
            <Field label="Roster name" style={{ gridColumn: "1 / -1" }}>
              <Select
                value={empId === "" ? "" : String(empId)}
                onChange={(e) => {
                  const v = e.target.value;
                  setEmpId(v === "" ? "" : Number(v));
                }}
                required
                disabled={isEdit}   // can't reattribute on edit
              >
                <option value="">— pick a roster member —</option>
                {roster.map((m) => (
                  <option key={m.id} value={m.id}>{m.name}</option>
                ))}
              </Select>
            </Field>
            <Field label="Clock in">
              <Input
                type="datetime-local" required
                value={clockIn}
                onChange={(e) => setClockIn(e.target.value)}
              />
            </Field>
            <Field
              label="Clock out (optional)"
              hint="Leave blank for an open / in-progress entry."
            >
              <Input
                type="datetime-local"
                value={clockOut}
                onChange={(e) => setClockOut(e.target.value)}
              />
            </Field>
            <Field label="Notes" style={{ gridColumn: "1 / -1" }}>
              <Textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={2}
                maxLength={500}
                placeholder="Why this entry was back-filled / edited."
              />
            </Field>
          </div>
          {err && <Alert tone="error">{err}</Alert>}
          <div className={styles.modalActions} style={{ marginTop: "0.75rem" }}>
            <Button
              type="button" tone="secondary"
              onClick={onClose} disabled={busy}
            >
              Cancel
            </Button>
            <Button type="submit" busy={busy} disabled={busy}>
              {isEdit ? "Save changes" : "Create entry"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}


// ── Date utils ──────────────────────────────────────────────


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

/** Convert a server-side ISO-8601 UTC string into the format
 *  ``<input type="datetime-local">`` expects ("YYYY-MM-DDTHH:MM"
 *  in local time). The form value gets re-converted back to
 *  ISO/UTC on save so the round-trip preserves the wall-clock
 *  the admin saw. */
function _toLocalInput(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
    + `T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
