import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  createTeamMember,
  deactivateTeamMember,
  updateTeamMember,
  useTeam,
  type TeamMemberRow,
} from "../api/account";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  Breadcrumbs,
  Alert, Button, Card, ErrorState, Input, Loading,
  PageHeader, PageShell,
} from "../components/ui";
import styles from "./AdminCashiers.module.css";

// /app/admin/cashiers — cashier name roster used by the
// "Processed by" dropdown on the transfer form and as the
// payroll subject in /app/admin/timeclock.
//
// Lifted out of /app/settings/team into the HR sidebar group
// when HR became its own section. The old /settings/team URL
// keeps working via a Navigate redirect in App.tsx.
//
// Identity / payroll source of truth:
//   - Name + hourly_rate live on TeamMember (this page).
//   - Login accounts live on User (/app/admin/users — "Team
//     users" in the nav). They're separate concepts on purpose:
//     a cashier can exist without a login (handed-cash
//     attribution only) and a login can exist without payroll
//     (manager who doesn't take shifts).

export default function AdminCashiers() {
  const queryClient = useQueryClient();
  const identity = getCurrentIdentity();
  const { data, isLoading, isError } = useTeam();
  const [newName, setNewName] = useState("");
  const [newRate, setNewRate] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [rateDraftById, setRateDraftById] =
    useState<Record<number, string>>({});
  const canEdit =
    identity?.role === "admin" ||
    identity?.role === "owner" ||
    identity?.role === "superadmin";

  function refetch() {
    queryClient.invalidateQueries({ queryKey: ["admin", "team"] });
    // Also invalidate the transfer-form's roster hook so the
    // dropdown picks up new / removed cashiers without a reload.
    queryClient.invalidateQueries({ queryKey: ["transfers", "employees"] });
  }

  async function add() {
    setErr(null);
    setBusy(true);
    try {
      const rate = Number(newRate);
      await createTeamMember(
        newName,
        Number.isFinite(rate) && rate >= 0 ? rate : 0,
      );
      setNewName(""); setNewRate("");
      refetch();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't add member");
    } finally {
      setBusy(false);
    }
  }

  async function saveRate(m: TeamMemberRow) {
    setErr(null);
    const raw = rateDraftById[m.id];
    if (raw == null) return;
    const rate = Number(raw);
    if (!Number.isFinite(rate) || rate < 0) {
      setErr("Hourly rate must be a non-negative number.");
      return;
    }
    try {
      await updateTeamMember(m.id, { hourly_rate: rate });
      setRateDraftById((prev) => {
        const next = { ...prev };
        delete next[m.id];
        return next;
      });
      refetch();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't update rate");
    }
  }

  async function toggle(m: TeamMemberRow) {
    setErr(null);
    try {
      await updateTeamMember(m.id, { is_active: !m.is_active });
      refetch();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't update");
    }
  }

  async function remove(m: TeamMemberRow) {
    setErr(null);
    try {
      await deactivateTeamMember(m.id);
      refetch();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't deactivate");
    }
  }

  if (identity?.store_id == null) {
    return (
      <PageShell maxWidth="60rem">
        <PageHeader title="Cashiers" />
        <Card>
          <p className={styles.muted}>
            Sign in as a store admin to manage the cashier roster.
          </p>
        </Card>
      </PageShell>
    );
  }

  return (
    <PageShell maxWidth="60rem">

      <Breadcrumbs crumbs={[{ label: "HR" }, { label: "Cashiers" }]} />

      <PageHeader
        title="Cashiers"
        subtitle='Names for the "Processed by" dropdown on transfers. Deactivated rows preserve historical attribution.'
      />
      <Card>

        {isLoading && <Loading />}
        {isError && (
          <ErrorState
            message="Could not load team."
            onRetry={() => { void refetch(); }}
          />
        )}

        {data && (
          <ul className={styles.listSpaced}>
            {data.members.length === 0 && (
              <li className={styles.emptyRow}>No team members yet.</li>
            )}
            {data.members.map((m) => {
              const draft = rateDraftById[m.id];
              const displayRate = draft != null
                ? draft
                : (m.hourly_rate || 0).toFixed(2);
              return (
                <li key={m.id} className={styles.rowTeam}>
                  <span className={m.is_active ? styles.memberActive : styles.memberInactive}>
                    {m.name}
                  </span>
                  {canEdit && (
                    <>
                      <span className={styles.rateGroup}>
                        <span className={styles.rateLabel}>$/hr</span>
                        <Input
                          type="number" min="0" step="0.25"
                          value={displayRate}
                          onChange={(e) => setRateDraftById((prev) => ({
                            ...prev, [m.id]: e.target.value,
                          }))}
                          disabled={!m.is_active}
                          style={{ width: "5.5rem" }}
                        />
                        {draft != null && (
                          <Button
                            tone="secondary" size="sm"
                            onClick={() => saveRate(m)}
                          >
                            Save
                          </Button>
                        )}
                      </span>
                      <Button
                        tone="secondary" size="sm"
                        onClick={() => toggle(m)}
                        title={m.is_active ? "Deactivate" : "Reactivate"}
                      >
                        {m.is_active ? "Deactivate" : "Reactivate"}
                      </Button>
                      {m.is_active && (
                        <Button
                          tone="secondary" size="sm"
                          onClick={() => remove(m)}
                        >
                          ✕
                        </Button>
                      )}
                    </>
                  )}
                </li>
              );
            })}
          </ul>
        )}

        {canEdit && (
          <div className={styles.actionsInlineRow}>
            <Input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="New cashier name"
              onKeyDown={(e) => {
                if (e.key === "Enter" && newName.trim()) {
                  e.preventDefault();
                  add();
                }
              }}
            />
            <Input
              type="number" min="0" step="0.25"
              value={newRate}
              onChange={(e) => setNewRate(e.target.value)}
              placeholder="$/hr (optional)"
              style={{ width: "9rem" }}
            />
            <Button
              onClick={add}
              busy={busy}
              disabled={busy || !newName.trim()}
            >
              + Add
            </Button>
          </div>
        )}
        {err && <Alert tone="error">{err}</Alert>}
      </Card>
    </PageShell>
  );
}
