import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  adminDeleteCredential,
  adminRegisterCredentialBegin,
  adminRegisterCredentialFinish,
  useTimeClockCredentials,
  type TimeClockCredentialRow,
} from "../api/timeclock";
import { useStoreInfo } from "../api/account";
import { ApiError } from "../lib/api";
import { passkeysSupported, performPasskeyRegister } from "../lib/webauthn";
import {
  Breadcrumbs,
  Alert, Button, Card, ConfirmDialog, EmptyState, ErrorState, Loading,
  PageHeader, PageShell, Pill, Table, tdStyle, thStyle,
} from "../components/ui";
import { getCurrentIdentity } from "../lib/auth";
import styles from "./AdminTimeClockCredentials.module.css";

// /app/admin/timeclock/credentials — admin enrolls a passkey
// for each active roster member. Once every cashier is registered
// the admin flips the ``timeclock_require_passkey`` toggle on
// Settings → Store, after which clock-in / clock-out demand a
// fresh OS-level authentication (Windows Hello / Touch ID /
// Face ID / hardware key).

export default function AdminTimeClockCredentials() {
  const identity = getCurrentIdentity();
  const queryClient = useQueryClient();
  const { data, isLoading, isError, refetch } = useTimeClockCredentials();
  const { data: storeInfo } = useStoreInfo();
  const [busyEmpId, setBusyEmpId] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const canView = identity?.role === "admin"
                  || identity?.role === "owner"
                  || identity?.role === "superadmin";
  const browserSupports = passkeysSupported();
  const gateOn = Boolean(storeInfo?.store?.timeclock_require_passkey);

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ["timeclock", "credentials"] });
  }

  async function register(row: TimeClockCredentialRow) {
    setErr(null); setBusyEmpId(row.store_employee_id);
    try {
      const begin = await adminRegisterCredentialBegin(
        row.store_employee_id,
      );
      const credential = await performPasskeyRegister(begin.options_json);
      await adminRegisterCredentialFinish(row.store_employee_id, {
        register_token: begin.register_token,
        credential,
        name: row.employee_name,
      });
      refresh();
    } catch (e) {
      setErr(
        e instanceof ApiError ? e.message
        : e instanceof Error ? e.message
        : "Couldn't register the passkey.",
      );
    } finally {
      setBusyEmpId(null);
    }
  }

  // Pending credential staged for removal; null = no confirm
  // showing.  Held as the whole row so the dialog can show the
  // employee name + the action handler has the employee id.
  const [pendingRemove, setPendingRemove] =
    useState<TimeClockCredentialRow | null>(null);

  async function doRemove() {
    if (!pendingRemove) return;
    setErr(null); setBusyEmpId(pendingRemove.store_employee_id);
    try {
      await adminDeleteCredential(pendingRemove.store_employee_id);
      refresh();
      setPendingRemove(null);
    } catch (e) {
      setErr(
        e instanceof ApiError ? e.message : "Couldn't remove the passkey.",
      );
    } finally {
      setBusyEmpId(null);
    }
  }

  if (!canView) {
    return (
      <PageShell>
        <PageHeader title="Time-clock credentials" />
        <EmptyState title="Admin or owner only." />
      </PageShell>
    );
  }

  return (
    <PageShell maxWidth="56rem">

      <Breadcrumbs crumbs={[{ label: "HR" }, { label: "Time-clock credentials" }]} />

      <PageHeader
        title="Time-clock credentials"
        subtitle="Enroll a passkey for each cashier — Windows Hello, Touch ID, Face ID, or a hardware key. Once everyone is registered, flip on Settings → Store → Block time-clock punches without a passkey."
      />

      {!browserSupports && (
        <Alert tone="warning">
          This browser doesn't expose the WebAuthn API. Use a modern
          Chrome / Safari / Firefox / Edge build to enroll passkeys.
        </Alert>
      )}

      {gateOn && (
        <Alert tone="info">
          Passkey gate is currently <strong>ON</strong>. Any cashier
          without a registered passkey is blocked from clocking in or
          out — make sure every active roster member appears as
          <em> Registered</em> below before relying on this.
        </Alert>
      )}

      {!gateOn && (
        <p className={styles.intro}>
          The passkey gate is currently <strong>off</strong>. Enrolling
          passkeys here is no-op-friendly: punches still work without a
          passkey until you flip the gate on.
        </p>
      )}

      {isLoading && (
        <Card>
          <Loading />
        </Card>
      )}
      {isError && (
        <Card>
          <ErrorState
            message="Couldn't load roster credentials."
            onRetry={() => { void refetch(); }}
          />
        </Card>
      )}
      {data && data.rows.length === 0 && !isLoading && (
        <Card>
          <EmptyState
            title="No active roster members yet."
            body="Add cashier names on Settings → Team first."
          />
        </Card>
      )}
      {data && data.rows.length > 0 && (
        <Card>
          <Table>
            <thead>
              <tr>
                {[
                  "Cashier", "Status", "Registered",
                  "Last used", "",
                ].map((h) => (
                  <th key={h} style={thStyle}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <tr key={r.store_employee_id}>
                  <td style={tdStyle}>
                    <strong>{r.employee_name}</strong>
                  </td>
                  <td style={tdStyle}>
                    {r.has_passkey
                      ? <Pill tone="accent">Registered</Pill>
                      : <Pill tone="warning">Pending</Pill>}
                  </td>
                  <td style={tdStyle}>
                    <span className={styles.mono}>
                      {r.registered_at
                        ? r.registered_at.slice(0, 10)
                        : "—"}
                    </span>
                  </td>
                  <td style={tdStyle}>
                    <span className={styles.mono}>
                      {r.last_used_at
                        ? r.last_used_at.slice(0, 10)
                        : "—"}
                    </span>
                  </td>
                  <td style={tdStyle}>
                    <div className={styles.rowActions}>
                      <Button
                        size="sm"
                        tone={r.has_passkey ? "secondary" : "primary"}
                        busy={busyEmpId === r.store_employee_id}
                        disabled={
                          !browserSupports
                          || busyEmpId !== null
                        }
                        onClick={() => register(r)}
                      >
                        {r.has_passkey ? "Re-enroll" : "Enroll passkey"}
                      </Button>
                      {r.has_passkey && (
                        <Button
                          size="sm" tone="secondary"
                          busy={busyEmpId === r.store_employee_id}
                          disabled={busyEmpId !== null}
                          onClick={() => setPendingRemove(r)}
                        >
                          Remove
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Card>
      )}

      {err && <Alert tone="error">{err}</Alert>}

      <ConfirmDialog
        open={pendingRemove != null}
        title="Remove passkey"
        message={
          `Remove ${pendingRemove?.employee_name ?? "this cashier"}'s `
          + "registered passkey?  They'll need to re-enroll before "
          + "they can clock in / out (if the store gate is on)."
        }
        confirmLabel="Remove"
        confirmTone="danger"
        busy={busyEmpId === pendingRemove?.store_employee_id}
        onConfirm={() => { void doRemove(); }}
        onCancel={() => setPendingRemove(null)}
      />
    </PageShell>
  );
}
