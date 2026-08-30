import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import {
  generateOwnerConnectCode, revokeOwnerConnectCode, useOwnerConnectCodes,
  type OwnerConnectCodeRow,
} from "../api/owner";
import { useProfile } from "../api/account";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import { formatDate as formatDateTz } from "../lib/datetime";
import {
  Breadcrumbs,
  Button, Card, ConfirmDialog, ErrorState, Loading, PageHeader, PageShell,
  Section, Table, tdStyle, thStyle,
  Empty,
} from "../components/ui";
import styles from "./OwnerConnect.module.css";

// /app/owner/connect — owner mints 8-character invite codes that
// store admins redeem on their settings page to link a store to
// the owner's umbrella. v1 ships:
//   - one-active-code semantics: generating revokes the current
//     active code first, mirroring the legacy Flask behavior
//   - copy-to-clipboard for the active code
//   - revoke action for the active code
//   - last-10 redeemed history
//
// The 7-day TTL is enforced server-side; we just render
// `expires_at`. Backed by /api/v2/owner/connect-codes.

export default function OwnerConnect() {
  const identity = getCurrentIdentity();
  const queryClient = useQueryClient();
  const { data, isLoading, isError, error, refetch } = useOwnerConnectCodes();
  const { data: profile } = useProfile();
  const userTz = profile?.timezone ?? "";
  const formatDate = (iso: string) =>
    formatDateTz(iso, { userTimezone: userTz });

  const [busy, setBusy] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  // Two destructive actions live on this page; each gets its own
  // ConfirmDialog open-state so the right copy lands in the right
  // prompt.  Lifted above the role-check early-return so hooks
  // run in the same order on every render.
  const [confirmingGenerate, setConfirmingGenerate] = useState(false);
  const [confirmingRevoke, setConfirmingRevoke] = useState(false);

  // The legacy page shows the FIRST unused-unrevoked-unexpired
  // code as the "active" one; we narrow to the same shape.
  const active = useMemo<OwnerConnectCodeRow | null>(() => {
    if (!data) return null;
    return data.rows.find(
      (r) => !r.is_redeemed && !r.is_revoked && !r.is_expired,
    ) ?? null;
  }, [data]);

  const redeemed = useMemo<OwnerConnectCodeRow[]>(() => {
    if (!data) return [];
    return data.rows.filter((r) => r.is_redeemed).slice(0, 10);
  }, [data]);

  if (identity?.role !== "owner") {
    return (
      <PageShell maxWidth="40rem">
        <PageHeader title="Connect a Store" />
        <p className={styles.deny}>
          Only owners can mint store-connect codes.
        </p>
      </PageShell>
    );
  }

  async function doGenerate() {
    setConfirmingGenerate(false);
    setBusy(true); setServerError(null);
    try {
      // Legacy contract: generating revokes any active code first.
      // The new endpoint does NOT auto-revoke (clean separation),
      // so we revoke client-side before minting.
      if (active) {
        await revokeOwnerConnectCode(active.id);
      }
      await generateOwnerConnectCode();
      queryClient.invalidateQueries({ queryKey: ["owner", "connect-codes"] });
    } catch (err) {
      setServerError(
        err instanceof ApiError ? err.message : "Could not generate code.",
      );
    } finally { setBusy(false); }
  }

  async function doRevoke() {
    if (!active) return;
    setConfirmingRevoke(false);
    setBusy(true); setServerError(null);
    try {
      await revokeOwnerConnectCode(active.id);
      queryClient.invalidateQueries({ queryKey: ["owner", "connect-codes"] });
    } catch (err) {
      setServerError(
        err instanceof ApiError ? err.message : "Could not revoke code.",
      );
    } finally { setBusy(false); }
  }

  function handleCopy() {
    if (!active) return;
    if (navigator.clipboard) {
      navigator.clipboard.writeText(active.code);
    } else {
      const ta = document.createElement("textarea");
      ta.value = active.code; document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); } finally { ta.remove(); }
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  }

  return (
    <PageShell maxWidth="40rem">

      <Breadcrumbs crumbs={[{ label: "Owner" }, { label: "Connect a store" }]} />

      <PageHeader title="Connect a Store" />

      {serverError && <ErrorState message={serverError} />}

      <Section title="Active invite code">
        <Card>
          {isLoading && <Loading />}
          {isError && (
            <ErrorState
              message={`Couldn't load codes.${error instanceof Error ? ` ${error.message}` : ""}`}
              onRetry={() => { void refetch(); }}
            />
          )}
          {!isLoading && !active && (
            <>
              <p className={styles.lead}>
                No active code. Generate one to give to a store admin —
                they'll enter it on their store's Settings → Owner Access
                page to link their store to your umbrella. Codes are
                valid for 7 days.
              </p>
              <Button onClick={() => setConfirmingGenerate(true)} busy={busy} disabled={busy}>
                {busy ? "Generating…" : "Generate Invite Code"}
              </Button>
            </>
          )}
          {active && (
            <>
              <p className={styles.lead}>
                Share this code with the store admin you want to connect.
                They enter it on their store's Settings → Owner Access
                page. Code expires on{" "}
                <strong>{formatDate(active.expires_at)}</strong>.
              </p>
              <div className={styles.codeRow}>
                <input
                  type="text" readOnly value={active.code}
                  className={styles.codeInput}
                  onFocus={(e) => e.currentTarget.select()}
                />
                <Button tone="secondary" onClick={handleCopy} aria-label={copied ? "Code copied to clipboard" : "Copy code to clipboard"}>
                  {copied ? "Copied" : "Copy"}
                </Button>
              </div>
              <div className={styles.actionsRow}>
                <Button tone="secondary" onClick={() => setConfirmingRevoke(true)} disabled={busy}>
                  Revoke
                </Button>
                <Button tone="secondary" onClick={() => setConfirmingGenerate(true)} disabled={busy}>
                  {busy ? "Generating…" : "Generate New Code"}
                </Button>
              </div>
            </>
          )}
        </Card>
      </Section>

      <Section
        title="Recently redeemed"
        actions={<span className={styles.mutedSm}>Last 10</span>}
      >
        <Card>
          {redeemed.length > 0 ? (
            <Table>
              <thead>
                <tr>
                  <th style={thStyle}>Code</th>
                  <th style={thStyle}>Store</th>
                  <th style={thStyle}>Redeemed</th>
                </tr>
              </thead>
              <tbody>
                {redeemed.map((r) => (
                  <tr key={r.id}>
                    <td style={tdStyle} className={styles.mono}>{r.code}</td>
                    <td style={tdStyle}>{r.used_by_store_name || "—"}</td>
                    <td style={tdStyle} className={styles.cellMuted}>
                      {formatDate(r.used_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <Empty>
              No codes redeemed yet. Stores you've connected will show
              up here.
            </Empty>
          )}
        </Card>
      </Section>

      <p className={styles.fine}>
        To disconnect a store, head to your{" "}
        <Link to="/dashboard" className={styles.inlineLink}>Dashboard</Link>{" "}
        or{" "}
        <Link to="/owner/locations" className={styles.inlineLink}>Locations</Link>{" "}
        page — only the owner can break the link, store admins can't.
      </p>

      <ConfirmDialog
        open={confirmingGenerate}
        title={active ? "Replace the current code?" : "Generate a new code?"}
        message={
          active
            ? "Generating a new code revokes the current one — the store admin who's holding it won't be able to redeem anymore."
            : "A fresh 8-character invite code valid for 7 days.  Share it with the store admin you want to connect."
        }
        confirmLabel={active ? "Replace" : "Generate"}
        confirmTone={active ? "danger" : "primary"}
        busy={busy}
        onConfirm={() => { void doGenerate(); }}
        onCancel={() => setConfirmingGenerate(false)}
      />
      <ConfirmDialog
        open={confirmingRevoke}
        title="Revoke this code?"
        message="The store admin won't be able to redeem it.  You can generate a new one right after."
        confirmLabel="Revoke"
        confirmTone="danger"
        busy={busy}
        onConfirm={() => { void doRevoke(); }}
        onCancel={() => setConfirmingRevoke(false)}
      />
    </PageShell>
  );
}


