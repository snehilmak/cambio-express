import { useMemo, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  createShift,
  deleteShift,
  updateShift,
  useShifts,
  type ShiftRow,
} from "../api/timeclock";
import { useEmployees } from "../api/transfers";
import { ApiError } from "../lib/api";
import {
  Breadcrumbs,
  Alert, Button, Card, ConfirmDialog, EmptyState, ErrorState, Field, Input,
  Loading, PageHeader, PageShell, Select,
} from "../components/ui";
import styles from "./AdminTimeClockSchedule.module.css";

// /app/admin/timeclock/schedule — admin shift planner.
//
// v1 layout: a 7-day grid for the picked week, one column per
// day, one card per scheduled shift inside the column.  Click
// "Add shift" → inline form at the top of the column for that
// day.  Click an existing shift → inline form to edit / delete.
// Punches (TimeClockEntry) are tracked separately — this page
// is the operator's PLAN, not the actual punches.  Late-arrival
// / no-show derivation against actual punches is a follow-up.

export default function AdminTimeClockSchedule() {
  const queryClient = useQueryClient();
  const roster      = useEmployees();
  const [weekStart, setWeekStart] = useState(() => mondayOf(new Date()));
  const weekEnd     = useMemo(() => addDays(weekStart, 7), [weekStart]);
  const shifts      = useShifts(isoDate(weekStart), isoDate(weekEnd));
  const [flash, setFlash] = useState<
    { kind: "ok" | "err"; msg: string } | null
  >(null);

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ["timeclock", "shifts"] });
  }

  const shiftsByDay = useMemo(() => {
    const map = new Map<string, ShiftRow[]>();
    for (const s of shifts.data?.rows ?? []) {
      const list = map.get(s.shift_date) ?? [];
      list.push(s);
      map.set(s.shift_date, list);
    }
    return map;
  }, [shifts.data]);

  if (roster.isError) {
    return (
      <PageShell>
        <PageHeader title="Schedule" />
        <ErrorState
          message="Couldn't load the store roster."
          onRetry={() => { void roster.refetch(); }}
        />
      </PageShell>
    );
  }
  if (roster.isLoading) {
    return (
      <PageShell>
        <PageHeader title="Schedule" />
        <Loading />
      </PageShell>
    );
  }
  const activeRoster = roster.data?.employees ?? [];

  return (
    <PageShell>

      <Breadcrumbs crumbs={[{ label: "HR" }, { label: "Schedule" }]} />

      <PageHeader
        title="Schedule"
        subtitle="Plan shifts for your team — one row per scheduled shift. Actual punches stay tracked on the payroll history page."
      />

      <Card>
        <div className={styles.weekBar}>
          <Button
            type="button" tone="secondary"
            onClick={() => setWeekStart(addDays(weekStart, -7))}
          >
            ← Prev week
          </Button>
          <div className={styles.weekLabel}>
            {formatWeekRange(weekStart, weekEnd)}
          </div>
          <Button
            type="button" tone="secondary"
            onClick={() => setWeekStart(addDays(weekStart, 7))}
          >
            Next week →
          </Button>
          <Button
            type="button" tone="secondary"
            onClick={() => setWeekStart(mondayOf(new Date()))}
          >
            This week
          </Button>
        </div>
        {flash && (
          <div className={styles.flash}>
            <Alert tone={flash.kind === "ok" ? "success" : "error"}>
              {flash.msg}
            </Alert>
          </div>
        )}
      </Card>

      {activeRoster.length === 0 ? (
        <Card>
          <EmptyState
            title="No roster members yet."
            body="Add cashier names from /app/settings → Team before scheduling shifts."
          />
        </Card>
      ) : shifts.isLoading ? (
        <Card><Loading /></Card>
      ) : (
        <div className={styles.weekGrid}>
          {Array.from({ length: 7 }, (_, i) => {
            const day = addDays(weekStart, i);
            const iso = isoDate(day);
            return (
              <DayColumn
                key={iso}
                date={day}
                shifts={shiftsByDay.get(iso) ?? []}
                roster={activeRoster}
                onSaved={(msg) => {
                  setFlash({ kind: "ok", msg });
                  refresh();
                }}
                onError={(msg) => setFlash({ kind: "err", msg })}
              />
            );
          })}
        </div>
      )}
    </PageShell>
  );
}


function DayColumn({
  date, shifts, roster, onSaved, onError,
}: {
  date: Date;
  shifts: ShiftRow[];
  roster: { id: number; name: string }[];
  onSaved: (msg: string) => void;
  onError: (msg: string) => void;
}) {
  const [adding, setAdding] = useState(false);
  const isToday = isoDate(date) === isoDate(new Date());
  return (
    <div className={`${styles.dayCol}${isToday ? " " + styles.dayColToday : ""}`}>
      <div className={styles.dayHeader}>
        <span className={styles.dayName}>{DAY_NAMES[date.getDay()]}</span>
        <span className={styles.dayDate}>{date.getDate()}</span>
      </div>
      <div className={styles.dayBody}>
        {shifts.length === 0 && !adding && (
          <div className={styles.empty}>No shifts</div>
        )}
        {shifts.map((s) => (
          <ShiftCard
            key={s.id} shift={s} roster={roster}
            onSaved={onSaved} onError={onError}
          />
        ))}
        {adding ? (
          <ShiftForm
            defaultDate={isoDate(date)}
            roster={roster}
            onCancel={() => setAdding(false)}
            onSaved={(msg) => { setAdding(false); onSaved(msg); }}
            onError={onError}
          />
        ) : (
          <Button
            type="button" tone="secondary"
            onClick={() => setAdding(true)}
          >
            + Add shift
          </Button>
        )}
      </div>
    </div>
  );
}


function ShiftCard({
  shift, roster, onSaved, onError,
}: {
  shift: ShiftRow;
  roster: { id: number; name: string }[];
  onSaved: (msg: string) => void;
  onError: (msg: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  async function doDelete() {
    setBusy(true);
    try {
      await deleteShift(shift.id);
      onSaved(`Deleted ${shift.employee_name}'s shift.`);
      setConfirmingDelete(false);
    } catch (err) {
      onError(err instanceof ApiError
        ? err.message
        : "Could not delete the shift.");
    } finally {
      setBusy(false);
    }
  }

  if (editing) {
    return (
      <ShiftForm
        existing={shift}
        defaultDate={shift.shift_date}
        roster={roster}
        onCancel={() => setEditing(false)}
        onSaved={(msg) => { setEditing(false); onSaved(msg); }}
        onError={onError}
      />
    );
  }
  return (
    <div className={styles.shift}>
      <div className={styles.shiftTimes}>
        {trimSeconds(shift.start_time)}–{trimSeconds(shift.end_time)}
      </div>
      <div className={styles.shiftWho}>{shift.employee_name}</div>
      {shift.notes && (
        <div className={styles.shiftNotes}>{shift.notes}</div>
      )}
      <div className={styles.shiftActions}>
        <button
          type="button" className={styles.linkBtn}
          onClick={() => setEditing(true)}
        >
          Edit
        </button>
        <button
          type="button" className={styles.linkBtn}
          onClick={() => setConfirmingDelete(true)}
          disabled={busy}
        >
          {busy ? "…" : "Delete"}
        </button>
      </div>
      <ConfirmDialog
        open={confirmingDelete}
        title="Delete shift"
        message={
          `Delete the ${trimSeconds(shift.start_time)} shift for `
          + `${shift.employee_name}? The roster row stays; only this `
          + "planned shift is removed."
        }
        confirmLabel="Delete"
        confirmTone="danger"
        busy={busy}
        onConfirm={() => { void doDelete(); }}
        onCancel={() => setConfirmingDelete(false)}
      />
    </div>
  );
}


function ShiftForm({
  existing, defaultDate, roster, onCancel, onSaved, onError,
}: {
  existing?: ShiftRow;
  defaultDate: string;
  roster: { id: number; name: string }[];
  onCancel: () => void;
  onSaved: (msg: string) => void;
  onError: (msg: string) => void;
}) {
  const [empId, setEmpId] = useState<number | "">(
    existing?.store_employee_id ?? "",
  );
  const [startTime, setStartTime] = useState(
    existing ? trimSeconds(existing.start_time) : "09:00",
  );
  const [endTime, setEndTime] = useState(
    existing ? trimSeconds(existing.end_time) : "17:00",
  );
  const [notes, setNotes] = useState(existing?.notes ?? "");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (empId === "") return;
    setBusy(true);
    try {
      if (existing) {
        const updated = await updateShift(existing.id, {
          store_employee_id: Number(empId),
          shift_date: defaultDate,
          start_time: startTime,
          end_time:   endTime,
          notes,
        });
        onSaved(`Updated ${updated.employee_name}'s shift.`);
      } else {
        const created = await createShift({
          store_employee_id: Number(empId),
          shift_date: defaultDate,
          start_time: startTime,
          end_time:   endTime,
          notes,
        });
        onSaved(`Scheduled ${created.employee_name}.`);
      }
    } catch (err) {
      onError(err instanceof ApiError
        ? err.message
        : "Could not save the shift.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className={styles.form}>
      <Field label="Cashier">
        <Select
          value={empId === "" ? "" : String(empId)}
          onChange={(e) => {
            const v = e.target.value;
            setEmpId(v === "" ? "" : Number(v));
          }}
          required
        >
          <option value="">— pick —</option>
          {roster.map((m) => (
            <option key={m.id} value={m.id}>{m.name}</option>
          ))}
        </Select>
      </Field>
      <div className={styles.formTimeRow}>
        <Field label="Start">
          <Input
            type="time" value={startTime}
            onChange={(e) => setStartTime(e.target.value)}
            required
          />
        </Field>
        <Field label="End">
          <Input
            type="time" value={endTime}
            onChange={(e) => setEndTime(e.target.value)}
            required
          />
        </Field>
      </div>
      <Field label="Notes (optional)">
        <Input
          type="text" maxLength={500}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </Field>
      <div className={styles.formActions}>
        <Button
          type="button" tone="secondary"
          onClick={onCancel} disabled={busy}
        >
          Cancel
        </Button>
        <Button type="submit" busy={busy} disabled={busy || empId === ""}>
          {existing ? "Save" : "Add"}
        </Button>
      </div>
    </form>
  );
}


// ── date helpers ────────────────────────────────────────────

const DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function mondayOf(d: Date): Date {
  const out = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  // getDay(): 0 = Sunday, 1 = Monday, ..., 6 = Saturday.
  // Walk back to the most recent Monday — treat Sunday as the
  // tail of the prior week.
  const dow = out.getDay();
  const back = dow === 0 ? 6 : dow - 1;
  out.setDate(out.getDate() - back);
  return out;
}

function addDays(d: Date, n: number): Date {
  const out = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  out.setDate(out.getDate() + n);
  return out;
}

function isoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function formatWeekRange(start: Date, end: Date): string {
  const e = addDays(end, -1);
  const fmt = (d: Date) => d.toLocaleDateString(undefined, {
    month: "short", day: "numeric",
  });
  return `${fmt(start)} – ${fmt(e)}, ${start.getFullYear()}`;
}

function trimSeconds(t: string): string {
  // "09:00:00" → "09:00".  Backend returns HH:MM:SS from Python
  // ``time.isoformat()``; we display HH:MM only.
  return t.length >= 5 ? t.slice(0, 5) : t;
}
