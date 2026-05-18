import { useMemo, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  fetchPunchChallenge,
  useClockInMutation, useClockOutMutation, useTimeClockStatus,
  type PunchInput, type TimeClockEntryRow,
} from "../api/timeclock";
import { useEmployees } from "../api/transfers";
import { useStoreInfo, useProfile } from "../api/account";
import { ApiError } from "../lib/api";
import { formatTimestamp } from "../lib/datetime";
import { passkeysSupported, performPasskeyAssert } from "../lib/webauthn";
import {
  Alert, Button, Card, EmptyState, Empty, ErrorState, Field, Input,
  Loading, PageHeader, PageShell, Select, Table, tdStyle, thStyle,
} from "../components/ui";
import styles from "./TimeClock.module.css";

// /app/timeclock — employee punch page. Pick your roster name,
// clock in / out. The "who's currently clocked in?" panel below
// reflects every open entry at the store so a cashier can see if
// their name is already punched (e.g. by a different terminal).

export default function TimeClock() {
  const queryClient   = useQueryClient();
  const roster        = useEmployees();
  const status        = useTimeClockStatus();
  const { data: profile }   = useProfile();
  const { data: storeInfo } = useStoreInfo();
  const userTz   = profile?.timezone ?? "";
  const storeTz  = storeInfo?.store?.timezone ?? "";
  const clockIn  = useClockInMutation();
  const clockOut = useClockOutMutation();

  const [pickedEmpId, setPickedEmpId] = useState<number | "">("");
  const [notes, setNotes]             = useState("");
  const [flash, setFlash]             =
    useState<{ kind: "ok" | "err"; msg: string } | null>(null);

  const openByEmp = useMemo(() => {
    const map = new Map<number, TimeClockEntryRow>();
    for (const r of status.data?.open_entries ?? []) {
      map.set(r.store_employee_id, r);
    }
    return map;
  }, [status.data]);

  const pickedIsOpen =
    pickedEmpId !== "" && openByEmp.has(Number(pickedEmpId));

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ["timeclock", "status"] });
  }

  // True when the store has flipped on the passkey gate.
  // Determines whether the punch flow runs the extra WebAuthn
  // round-trip before hitting clock-in / clock-out.
  const passkeyRequired =
    Boolean(storeInfo?.store?.timeclock_require_passkey);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFlash(null);
    if (pickedEmpId === "") return;
    const empId = Number(pickedEmpId);
    const empName =
      roster.data?.employees.find((m) => m.id === empId)?.name
        ?? `roster #${empId}`;
    try {
      // Optional WebAuthn pre-step. When the store requires a
      // passkey, fetch a challenge → run the OS prompt → echo
      // the assertion back on the punch call. Skipped entirely
      // when the toggle is off so the existing punch flow keeps
      // its zero-prompt UX.
      const punch: PunchInput = {
        store_employee_id: empId, notes,
      };
      if (passkeyRequired) {
        if (!passkeysSupported()) {
          throw new Error(
            "This store requires a passkey for time-clock punches, "
            + "but this browser doesn't support WebAuthn. Use a modern "
            + "Chrome / Safari / Firefox / Edge build.",
          );
        }
        const challenge = await fetchPunchChallenge(empId);
        const assertion = await performPasskeyAssert(
          challenge.options_json,
        );
        punch.assert_token = challenge.assert_token;
        punch.assertion    = assertion;
      }
      if (pickedIsOpen) {
        await clockOut.mutateAsync(punch);
        setFlash({ kind: "ok", msg: `${empName} clocked out.` });
      } else {
        await clockIn.mutateAsync(punch);
        setFlash({ kind: "ok", msg: `${empName} clocked in.` });
      }
      setNotes("");
      refresh();
    } catch (err) {
      setFlash({
        kind: "err",
        msg: err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Couldn't record the punch.",
      });
    }
  }

  if (roster.isError) {
    return (
      <PageShell>
        <PageHeader title="Time clock" />
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
        <PageHeader title="Time clock" />
        <Loading />
      </PageShell>
    );
  }

  // ``useEmployees`` already filters to active-only server-side.
  const activeRoster = roster.data?.employees ?? [];

  return (
    <PageShell maxWidth="56rem">
      <PageHeader
        title="Time clock"
        subtitle="Pick your name on the roster, then clock in or out. Shifts are logged in the store's local time."
      />

      {activeRoster.length === 0 && (
        <Empty>
          No active roster members yet. An admin can add cashier
          names from <code>/app/settings</code> → Team.
        </Empty>
      )}

      {activeRoster.length > 0 && (
        <Card>
          <form onSubmit={onSubmit} className={styles.form}>
            <Field label="Roster name">
              <Select
                value={pickedEmpId === "" ? "" : String(pickedEmpId)}
                onChange={(e) => {
                  const v = e.target.value;
                  setPickedEmpId(v === "" ? "" : Number(v));
                }}
                required
              >
                <option value="">— pick your name —</option>
                {activeRoster.map((m) => {
                  const open = openByEmp.get(m.id);
                  return (
                    <option key={m.id} value={m.id}>
                      {m.name}{open ? "  (clocked in)" : ""}
                    </option>
                  );
                })}
              </Select>
            </Field>
            <Field
              label="Notes (optional)"
              hint="Anything that explains the shift — covered for someone, came in late, etc."
            >
              <Input
                type="text" maxLength={500}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </Field>
            {flash && (
              <Alert tone={flash.kind === "ok" ? "success" : "error"}>
                {flash.msg}
              </Alert>
            )}
            <div className={styles.actions}>
              <Button
                type="submit"
                tone={pickedIsOpen ? "secondary" : "primary"}
                busy={clockIn.isPending || clockOut.isPending}
                disabled={
                  pickedEmpId === ""
                  || clockIn.isPending
                  || clockOut.isPending
                }
              >
                {pickedIsOpen ? "Clock out" : "Clock in"}
              </Button>
            </div>
          </form>
        </Card>
      )}

      <Card>
        <h2 className={styles.panelTitle}>Currently clocked in</h2>
        {status.isLoading && <Loading />}
        {status.isError && (
          <ErrorState
            message="Couldn't load current shifts."
            onRetry={() => { void status.refetch(); }}
          />
        )}
        {status.data && status.data.open_entries.length === 0 && (
          <EmptyState title="Nobody's on the clock right now." />
        )}
        {status.data && status.data.open_entries.length > 0 && (
          <Table>
            <thead>
              <tr>
                {["Roster name", "Clocked in", "Notes"].map((h) => (
                  <th key={h} style={thStyle}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {status.data.open_entries.map((r) => (
                <tr key={r.id}>
                  <td style={tdStyle}>{r.employee_name}</td>
                  <td style={tdStyle}>
                    <span className={styles.mono}>
                      {formatTimestamp(r.clock_in_at, {
                        userTimezone: userTz, storeTimezone: storeTz,
                      })}
                    </span>
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
