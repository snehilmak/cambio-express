import { useEffect, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  changePassword,
  createTeamMember,
  deactivateTeamMember,
  deletePasskey,
  passkeysSupported,
  registerPasskey,
  updateStoreInfo,
  updateTeamMember,
  usePasskeys,
  useStoreInfo,
  useTeam,
  type TeamMemberRow,
} from "../api/account";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  Alert, Button, ButtonLink, Card, ErrorState, Field, Input, Loading,
  PageHeader, PageShell, SectionTitle,
} from "../components/ui";
import styles from "./Settings.module.css";

// Account settings page at /app/settings. v1 ships the
// change-password card; subsequent PRs add profile / preferences /
// 2FA / passkey management.

export default function Settings() {
  const identity = getCurrentIdentity();

  return (
    <PageShell maxWidth="60rem" gap="1rem">
      <PageHeader title="Settings" subtitle={identity?.username || "—"} />

      <StoreInfoCard />
      <SubscriptionCard />
      <TeamCard />
      <ChangePasswordCard />
      <PasskeysCard />
    </PageShell>
  );
}

function PasskeysCard() {
  const queryClient = useQueryClient();
  const identity = getCurrentIdentity();
  const { data, isLoading, isError, refetch } = usePasskeys();
  const [busyId, setBusyId] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [addBusy, setAddBusy] = useState(false);
  const [newName, setNewName] = useState("");
  const supported = passkeysSupported();

  if (identity == null) return null;

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ["account", "passkeys"] });
  }

  async function remove(id: number, label: string) {
    if (!confirm(`Remove "${label || "this device"}"?`)) return;
    setErr(null); setBusyId(id);
    try {
      await deletePasskey(id);
      refresh();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not remove device.");
    } finally {
      setBusyId(null);
    }
  }

  async function add() {
    setErr(null); setAddBusy(true);
    try {
      await registerPasskey(newName.trim());
      setAdding(false);
      setNewName("");
      refresh();
    } catch (e) {
      // navigator.credentials.create() rejects on cancel / wrong
      // device / etc. with browser-specific messages — surface
      // them as-is so users see the actual reason.
      const msg = e instanceof ApiError
        ? e.message
        : (e instanceof Error ? e.message : "Could not create passkey.");
      setErr(msg);
    } finally {
      setAddBusy(false);
    }
  }

  return (
    <Card>
      <div className={styles.sectionHead}>
        <div style={{ flex: 1 }}>
          <SectionTitle>Passkeys</SectionTitle>
        </div>
        {supported && !adding && (
          <Button
            tone="secondary" size="sm"
            onClick={() => { setAdding(true); setErr(null); }}
          >
            + Add a passkey
          </Button>
        )}
      </div>
      <p className={styles.helpText}>
        Sign in with your device (Touch ID, Face ID, Windows Hello,
        or a hardware key) instead of a password. Passkeys are
        phishing-resistant and count as two-factor auth, so a passkey
        login skips the verification-code step.
      </p>
      {!supported && (
        <Alert tone="info">
          This browser doesn't expose the WebAuthn API, so passkeys
          aren't available here. Use a modern Chrome, Safari, Firefox,
          or Edge build.
        </Alert>
      )}
      {adding && (
        <div className={styles.addInset}>
          <Field label="Nickname for this passkey">
            <Input
              type="text" value={newName} maxLength={120}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="e.g. MacBook Touch ID"
              autoFocus disabled={addBusy}
            />
          </Field>
          <div className={styles.addInsetActions}>
            <Button onClick={add} busy={addBusy} disabled={addBusy} size="sm">
              {addBusy ? "Creating…" : "Create passkey"}
            </Button>
            <Button
              tone="secondary" size="sm"
              onClick={() => { setAdding(false); setNewName(""); setErr(null); }}
              disabled={addBusy}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}
      {isLoading && <Loading />}
      {isError && (
        <ErrorState
          message="Could not load passkeys."
          onRetry={() => { void refetch(); }}
        />
      )}
      {data && data.passkeys.length === 0 && !isLoading && (
        <p className={styles.muted}>No passkeys registered yet.</p>
      )}
      {data && data.passkeys.length > 0 && (
        <ul className={styles.list}>
          {data.passkeys.map((p) => (
            <li key={p.id} className={styles.row}>
              <span className={styles.rowBody}>
                <div className={styles.rowTitle}>
                  {p.name || "Unnamed device"}
                </div>
                <div className={styles.rowMeta}>
                  Added {p.created_at.slice(0, 10)}
                  {p.last_used_at &&
                    ` · last used ${p.last_used_at.slice(0, 10)}`}
                </div>
              </span>
              <Button
                tone="secondary" size="sm"
                onClick={() => remove(p.id, p.name)}
                busy={busyId === p.id}
                disabled={busyId === p.id}
              >
                {busyId === p.id ? "Removing…" : "Remove"}
              </Button>
            </li>
          ))}
        </ul>
      )}
      {err && <Alert tone="error">{err}</Alert>}
    </Card>
  );
}

function SubscriptionCard() {
  const identity = getCurrentIdentity();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const canManage =
    identity?.role === "admin" ||
    identity?.role === "owner" ||
    identity?.role === "superadmin";
  if (!canManage || identity?.store_id == null) return null;

  async function openPortal() {
    setErr(null);
    setBusy(true);
    try {
      const { openBillingPortal } = await import("../api/billing");
      const result = await openBillingPortal();
      window.location.assign(result.url);
    } catch (e) {
      // 409 = no Stripe customer yet (trial store) — push to subscribe
      if (e instanceof ApiError && e.status === 409) {
        window.location.assign("/app/subscribe");
        return;
      }
      setErr(e instanceof ApiError ? e.message : "Could not open billing portal.");
      setBusy(false);
    }
  }

  return (
    <Card>
      <SectionTitle>Subscription</SectionTitle>
      <p className={styles.subscriptionInfo}>
        Change plan, update payment method, or cancel — all on Stripe's
        secure billing portal. Trial stores can pick a plan instead.
      </p>
      <div className={styles.actionsRow}>
        <ButtonLink href="/app/subscribe" tone="primary">
          Choose / change plan
        </ButtonLink>
        <Button
          tone="secondary"
          onClick={openPortal}
          busy={busy}
          disabled={busy}
        >
          {busy ? "Opening…" : "Manage on Stripe"}
        </Button>
      </div>
      {err && <Alert tone="error">{err}</Alert>}
    </Card>
  );
}

function TeamCard() {
  const queryClient = useQueryClient();
  const identity = getCurrentIdentity();
  const { data, isLoading, isError } = useTeam();
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
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
      await createTeamMember(newName);
      setNewName("");
      refetch();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Couldn't add member");
    } finally {
      setBusy(false);
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

  if (identity?.store_id == null) return null;

  return (
    <Card>
      <SectionTitle>Team</SectionTitle>
      <p className={styles.helpText}>
        Cashier names that appear in the "Processed by" dropdown
        on the transfer form. Deactivated rows stay so historical
        transfer attribution survives.
      </p>

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
          {data.members.map((m) => (
            <li key={m.id} className={styles.rowTeam}>
              <span className={m.is_active ? styles.memberActive : styles.memberInactive}>
                {m.name}
              </span>
              {canEdit && (
                <>
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
          ))}
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
  );
}

function StoreInfoCard() {
  const queryClient = useQueryClient();
  const identity = getCurrentIdentity();
  const { data, isLoading, isError, refetch } = useStoreInfo();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [taxRatePct, setTaxRatePct] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);

  // Hydrate the form from the read-side row when it arrives.
  // Federal tax is stored as a decimal (0.01 = 1%) but operators
  // think in percents — display + edit accordingly.
  useEffect(() => {
    if (!data?.store) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate local editable store-settings fields from server-fetched row (federal_tax_rate gets a decimal->percent conversion for display)
    setName(data.store.name);
    setEmail(data.store.email);
    setPhone(data.store.phone);
    setAddress(data.store.address);
    setTaxRatePct(((data.store.federal_tax_rate || 0) * 100).toFixed(2));
  }, [data]);

  const canEdit =
    identity?.role === "admin" ||
    identity?.role === "owner" ||
    identity?.role === "superadmin";

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setOkMsg(null);
    setBusy(true);
    try {
      await updateStoreInfo({
        name, email, phone, address,
        federal_tax_rate: Number(taxRatePct) / 100,
      });
      await queryClient.invalidateQueries({
        queryKey: ["admin", "store-info"],
      });
      setOkMsg("Store info saved.");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  if (identity?.store_id == null) {
    return (
      <Card>
        <SectionTitle>Store</SectionTitle>
        <p className={styles.muted}>
          Sign in as a store admin to manage store info.
        </p>
      </Card>
    );
  }

  if (isLoading) {
    return (
      <Card>
        <SectionTitle>Store</SectionTitle>
        <Loading />
      </Card>
    );
  }
  if (isError || !data) {
    return (
      <Card>
        <SectionTitle>Store</SectionTitle>
        <ErrorState
          message="Could not load store info."
          onRetry={() => { void refetch(); }}
        />
      </Card>
    );
  }

  return (
    <Card>
      <SectionTitle>Store</SectionTitle>
      <p className={styles.slugRow}>
        Slug <code className={styles.slug}>{data.store.slug}</code>{" "}
        · plan {data.store.plan}
      </p>
      <form onSubmit={onSubmit} className={styles.storeGrid}>
        <Field label="Store name">
          <Input type="text" value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={!canEdit} required />
        </Field>
        <Field label="Email">
          <Input type="email" value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={!canEdit} />
        </Field>
        <Field label="Phone">
          <Input type="tel" value={phone}
            onChange={(e) => setPhone(e.target.value)}
            disabled={!canEdit} />
        </Field>
        <Field label="Address">
          <Input type="text" value={address}
            onChange={(e) => setAddress(e.target.value)}
            disabled={!canEdit} />
        </Field>
        <Field label="Federal tax rate (%)">
          <Input type="number" step="0.01" min="0" max="100"
            value={taxRatePct}
            onChange={(e) => setTaxRatePct(e.target.value)}
            disabled={!canEdit} />
        </Field>
        {err && (
          <div className={styles.spanFull}>
            <Alert tone="error">{err}</Alert>
          </div>
        )}
        {okMsg && (
          <div className={styles.spanFull}>
            <Alert tone="success">{okMsg}</Alert>
          </div>
        )}
        {canEdit && (
          <div className={styles.spanFullRight}>
            <Button type="submit" busy={busy} disabled={busy || !name}>
              {busy ? "Saving…" : "Save"}
            </Button>
          </div>
        )}
      </form>
    </Card>
  );
}

function ChangePasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setOkMsg(null);
    setBusy(true);
    try {
      await changePassword({
        current_password: current,
        new_password:     next,
        confirm_password: confirm,
      });
      setOkMsg("Password updated.");
      setCurrent(""); setNext(""); setConfirm("");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not update password.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <SectionTitle>Change password</SectionTitle>
      <form onSubmit={onSubmit} className={styles.passwordForm}>
        <Field label="Current password">
          <Input
            type="password"
            autoComplete="current-password"
            required
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
          />
        </Field>
        <Field label="New password (≥ 8 chars)">
          <Input
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            value={next}
            onChange={(e) => setNext(e.target.value)}
          />
        </Field>
        <Field label="Confirm new password">
          <Input
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
        </Field>
        {error && <Alert tone="error">{error}</Alert>}
        {okMsg && <Alert tone="success">{okMsg}</Alert>}
        <Button
          type="submit"
          busy={busy}
          disabled={busy || !current || !next || !confirm}
        >
          {busy ? "Saving…" : "Update password"}
        </Button>
      </form>
    </Card>
  );
}
