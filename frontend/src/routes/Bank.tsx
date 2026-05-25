import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  completeStripeConnect,
  disconnectBankAccount,
  refreshBankBalances,
  setBankAccountNickname,
  startStripeConnect,
  useBankAccounts,
  type BankAccountRow,
} from "../api/bankSync";
import { ApiError } from "../lib/api";
import {
  Breadcrumbs,
  Button, Card, ConfirmDialog, ErrorState,
  Loading, PageHeader, PageShell, SectionTitle, space, useToast,
} from "../components/ui";
import styles from "./Bank.module.css";

declare global {
  interface Window {
    Stripe?: (pk: string) => {
      collectFinancialConnectionsAccounts: (opts: {
        clientSecret: string;
      }) => Promise<{ error?: { message?: string } }>;
    };
  }
}

// /app/bank — connected bank accounts grid + recent transactions
// + the Stripe Financial Connections Connect modal flow.
//
// Connect flow (post-cutover, PR #654):
//   1. SPA POSTs /api/v2/bank/connect → server mints an FC
//      session, returns clientSecret + sessionId + publishableKey.
//   2. SPA loads Stripe.js if not already loaded, then calls
//      stripe.collectFinancialConnectionsAccounts({ clientSecret }).
//   3. Once Stripe.js resolves, SPA POSTs sessionId to
//      /api/v2/bank/connect/complete → server fetches the FC
//      session, upserts the linked accounts.
//   4. SPA invalidates the accounts/transactions React-Query
//      caches so the grid refreshes client-side.
//
// All account-level mutations (refresh, disconnect, sync
// transactions) now POST to /api/v2/bank/* and invalidate the
// React-Query cache for a refresh-free UI update.
export default function Bank() {
  const queryClient = useQueryClient();
  const accounts = useBankAccounts();
  const [connectError, setConnectError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const toast = useToast();

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ["bank", "accounts"] });
    void queryClient.invalidateQueries({ queryKey: ["bank", "transactions"] });
  }

  async function handleConnect() {
    setConnectError(null);
    setBusy("connect");
    try {
      await ensureStripeJs();
      const session = await startStripeConnect();
      const stripe = window.Stripe?.(session.publishableKey);
      if (!stripe) throw new Error("Stripe.js failed to load.");
      const result = await stripe.collectFinancialConnectionsAccounts({
        clientSecret: session.clientSecret,
      });
      if (result.error) {
        throw new Error(result.error.message || "Bank connection canceled.");
      }
      // Persist server-side, then refresh the accounts grid in
      // place (no full page reload).
      const persisted = await completeStripeConnect(session.sessionId);
      invalidate();
      toast({
        message: persisted.accounts_added > 0
          ? `Linked ${persisted.accounts_added} account(s).`
          : "Account already linked — nothing new to add.",
        tone: "success",
      });
    } catch (e) {
      const msg = e instanceof ApiError ? e.message
        : e instanceof Error ? e.message
        : "Connect failed.";
      setConnectError(msg);
    } finally {
      setBusy(null);
    }
  }

  async function handleRefresh() {
    setConnectError(null);
    setBusy("refresh");
    try {
      const r = await refreshBankBalances();
      invalidate();
      toast({
        message: r.error
          ? `Refreshed (${r.accounts_refreshed}). Warning: ${r.error}`
          : `Refreshed ${r.accounts_refreshed} account(s).`,
        tone: r.error ? "warning" : "success",
      });
    } catch (e) {
      setConnectError(
        e instanceof ApiError ? e.message
          : e instanceof Error ? e.message
          : "Refresh failed.",
      );
    } finally {
      setBusy(null);
    }
  }



  async function handleSaveNickname(acctId: number, nickname: string) {
    setConnectError(null);
    setBusy(`nickname:${acctId}`);
    try {
      await setBankAccountNickname(acctId, nickname);
      invalidate();
      toast({
        message: nickname.trim()
          ? `Renamed to "${nickname.trim()}".`
          : "Nickname cleared.",
        tone: "success",
      });
    } catch (e) {
      setConnectError(
        e instanceof ApiError ? e.message
          : e instanceof Error ? e.message
          : "Couldn't save nickname.",
      );
    } finally {
      setBusy(null);
    }
  }

  // Confirm-dialog state for the destructive disconnect.  The
  // pending object holds both id + label so the dialog can show
  // the right copy + the action handler can use the right id.
  const [pendingDisconnect, setPendingDisconnect] = useState<
    { id: number; label: string } | null
  >(null);

  async function doDisconnect() {
    if (!pendingDisconnect) return;
    const { id: acctId, label } = pendingDisconnect;
    setConnectError(null);
    setBusy(`disconnect:${acctId}`);
    try {
      await disconnectBankAccount(acctId);
      invalidate();
      toast({ message: `Disconnected ${label}.`, tone: "success" });
    } catch (e) {
      setConnectError(
        e instanceof ApiError ? e.message
          : e instanceof Error ? e.message
          : "Disconnect failed.",
      );
    } finally {
      setBusy(null);
      setPendingDisconnect(null);
    }
  }

  const accountList = accounts.data?.rows ?? [];
  const atCap = accountList.length >= 6; // mirror MAX_BANK_ACCOUNTS_PER_STORE

  return (
    <PageShell maxWidth="70rem" gap="1.25rem">

      <Breadcrumbs crumbs={[{ label: "Finance" }, { label: "Bank accounts" }]} />

      <PageHeader title="Bank Accounts" />

      {connectError && <ErrorState message={connectError} />}

      <Card>
        <header className={styles.sectionHeader}>
          <span className={styles.cardTitle}>
            Connected Bank Accounts
            {accountList.length > 0 && (
              <span className={styles.mutedInline}> {accountList.length} of 6</span>
            )}
          </span>
          {accountList.length > 0 && (
            <div className={styles.headerActions}>
              <Button
                tone="secondary" size="sm"
                busy={busy === "refresh"}
                disabled={busy !== null}
                onClick={() => { void handleRefresh(); }}
              >
                {busy === "refresh" ? "Refreshing…" : "Refresh"}
              </Button>
              {!atCap && (
                <Button
                  size="sm"
                  busy={busy === "connect"}
                  disabled={busy !== null}
                  onClick={() => { void handleConnect(); }}
                >
                  {busy === "connect" ? "Opening Stripe…" : "＋ Connect another"}
                </Button>
              )}
            </div>
          )}
        </header>

        {accounts.isLoading && <Loading />}
        {accounts.isError && (
          <ErrorState
            message="Couldn't load accounts."
            onRetry={() => { void accounts.refetch(); }}
          />
        )}

        {!accounts.isLoading && !accounts.isError && accountList.length === 0 && (
          <div className={styles.emptyConnect}>
            <SectionTitle>Connect your bank</SectionTitle>
            <p className={styles.muted}>
              Link your accounts securely through Stripe Financial Connections.
              We only see balances — never your bank login.
            </p>
            <Button
              busy={busy === "connect"}
              disabled={busy !== null}
              onClick={() => { void handleConnect(); }}
              style={{ marginTop: space.lg }}
            >
              {busy === "connect" ? "Opening Stripe…" : "Connect Bank via Stripe →"}
            </Button>
          </div>
        )}

        {accountList.length > 0 && (
          <div className={styles.accountGrid}>
            {accountList.map((a) => (
              <AccountCard
                key={a.id}
                acct={a}
                onDisconnect={() => setPendingDisconnect({ id: a.id, label: a.label })}
                onSaveNickname={(nickname) => handleSaveNickname(a.id, nickname)}
                disconnectBusy={busy === `disconnect:${a.id}`}
                nicknameBusy={busy === `nickname:${a.id}`}
                anyBusy={busy !== null}
              />
            ))}
          </div>
        )}
      </Card>

      <ConfirmDialog
        open={pendingDisconnect != null}
        title="Disconnect bank"
        message={
          `Disconnect ${pendingDisconnect?.label ?? "this bank"}? `
          + "Future transactions won't sync to DineroBook until "
          + "you reconnect."
        }
        confirmLabel="Disconnect"
        confirmTone="danger"
        busy={busy === `disconnect:${pendingDisconnect?.id}`}
        onConfirm={() => { void doDisconnect(); }}
        onCancel={() => setPendingDisconnect(null)}
      />
    </PageShell>
  );
}

function AccountCard({
  acct, onDisconnect, onSaveNickname,
  disconnectBusy, nicknameBusy, anyBusy,
}: {
  acct: BankAccountRow;
  onDisconnect: () => void;
  onSaveNickname: (nickname: string) => Promise<void>;
  disconnectBusy: boolean;
  nicknameBusy: boolean;
  anyBusy: boolean;
}) {
  const [nickname, setNickname] = useState(acct.nickname || "");
  return (
    <div className={styles.accountCard}>
      <div className={styles.mutedSmall}>
        {acct.institution_name || "Bank"}
        {acct.category && ` · ${acct.category}`}
      </div>
      <div className={styles.accountLabel}>
        {acct.label}
      </div>
      <div className={styles.balance}>
        ${acct.last_balance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </div>
      <div className={styles.mutedSmall}>
        {acct.last_balance_as_of
          ? `As of ${new Date(acct.last_balance_as_of).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}`
          : "Balance not yet refreshed."}
      </div>
      <form
        className={styles.nicknameForm}
        onSubmit={(e) => {
          e.preventDefault();
          void onSaveNickname(nickname);
        }}
      >
        <input
          type="text"
          name="nickname"
          value={nickname}
          onChange={(e) => setNickname(e.target.value)}
          placeholder="Set nickname (e.g. MSB Checking)"
          maxLength={60}
          className={styles.nicknameInput}
          disabled={anyBusy}
        />
        <Button
          type="submit" tone="secondary" size="sm"
          busy={nicknameBusy}
          disabled={anyBusy || nickname === (acct.nickname || "")}
        >
          {nicknameBusy ? "Saving…" : "Save"}
        </Button>
      </form>
      <div className={styles.disconnectForm}>
        <Button
          tone="danger" size="sm"
          busy={disconnectBusy}
          disabled={anyBusy}
          onClick={onDisconnect}
        >
          {disconnectBusy ? "Disconnecting…" : "Disconnect"}
        </Button>
      </div>
    </div>
  );
}

let _stripeLoadPromise: Promise<void> | null = null;
function ensureStripeJs(): Promise<void> {
  if (window.Stripe) return Promise.resolve();
  if (_stripeLoadPromise) return _stripeLoadPromise;
  _stripeLoadPromise = new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://js.stripe.com/v3/";
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Failed to load Stripe.js"));
    document.head.appendChild(s);
  });
  return _stripeLoadPromise;
}
