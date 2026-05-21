import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  completeStripeConnect,
  disconnectBankAccount,
  refreshBankBalances,
  startStripeConnect,
  syncBankTransactions,
  useBankAccounts,
  useBankTransactions,
  type BankAccountRow,
} from "../api/bankSync";
import { ApiError } from "../lib/api";
import {
  Alert, Button, ButtonLink, Card, EmptyState, ErrorState, Loading, PageHeader,
  PageShell, Table, TableSkeleton, tdStyle, thStyle,
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
  const recent = useBankTransactions({ per_page: 10, page: 1 });
  const [connectError, setConnectError] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ["bank", "accounts"] });
    void queryClient.invalidateQueries({ queryKey: ["bank", "transactions"] });
  }

  async function handleConnect() {
    setConnectError(null);
    setActionMsg(null);
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
      setActionMsg(
        persisted.accounts_added > 0
          ? `Linked ${persisted.accounts_added} account(s).`
          : "Account already linked — nothing new to add.",
      );
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
    setActionMsg(null);
    setBusy("refresh");
    try {
      const r = await refreshBankBalances();
      invalidate();
      setActionMsg(
        r.error ? `Refreshed (${r.accounts_refreshed}). Warning: ${r.error}`
          : `Refreshed ${r.accounts_refreshed} account(s).`,
      );
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

  async function handleSyncTxns() {
    setConnectError(null);
    setActionMsg(null);
    setBusy("sync");
    try {
      const r = await syncBankTransactions();
      invalidate();
      setActionMsg(
        r.error
          ? `Synced (new ${r.new_rows}). Warning: ${r.error}`
          : `Synced ${r.new_rows} new transaction(s) (${r.total_seen} seen).`,
      );
    } catch (e) {
      setConnectError(
        e instanceof ApiError ? e.message
          : e instanceof Error ? e.message
          : "Sync failed.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function handleDisconnect(acctId: number, label: string) {
    if (!confirm(`Disconnect ${label}?`)) return;
    setConnectError(null);
    setActionMsg(null);
    setBusy(`disconnect:${acctId}`);
    try {
      await disconnectBankAccount(acctId);
      invalidate();
      setActionMsg(`Disconnected ${label}.`);
    } catch (e) {
      setConnectError(
        e instanceof ApiError ? e.message
          : e instanceof Error ? e.message
          : "Disconnect failed.",
      );
    } finally {
      setBusy(null);
    }
  }

  const accountList = accounts.data?.rows ?? [];
  const txnList = recent.data?.rows ?? [];
  const atCap = accountList.length >= 6; // mirror MAX_BANK_ACCOUNTS_PER_STORE

  return (
    <PageShell maxWidth="70rem" gap="1.25rem">
      <PageHeader title="Bank Accounts" />

      {connectError && <ErrorState message={connectError} />}
      {actionMsg && <Alert tone="success">{actionMsg}</Alert>}

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
            <h3>Connect your bank</h3>
            <p className={styles.muted}>
              Link your accounts securely through Stripe Financial Connections.
              We only see balances — never your bank login.
            </p>
            <Button
              busy={busy === "connect"}
              disabled={busy !== null}
              onClick={() => { void handleConnect(); }}
              style={{ marginTop: "1rem" }}
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
                onDisconnect={() => { void handleDisconnect(a.id, a.label); }}
                disconnectBusy={busy === `disconnect:${a.id}`}
                anyBusy={busy !== null}
              />
            ))}
          </div>
        )}
      </Card>

      {accountList.length > 0 && (
        <Card>
          <header className={styles.sectionHeader}>
            <span className={styles.cardTitle}>Recent Transactions</span>
            <div className={styles.headerActions}>
              <Button
                size="sm"
                busy={busy === "sync"}
                disabled={busy !== null}
                onClick={() => { void handleSyncTxns(); }}
              >
                {busy === "sync" ? "Syncing…" : "Sync transactions"}
              </Button>
              <ButtonLink to="/bank-transactions" tone="secondary" size="sm">
                View all →
              </ButtonLink>
            </div>
          </header>

          {recent.isLoading && <TableSkeleton rows={5} cols={4} />}
          {!recent.isLoading && txnList.length === 0 && (
            <EmptyState
              title="No transactions yet"
              body={<>Click <strong>Sync transactions</strong> above to fetch.</>}
            />
          )}
          {txnList.length > 0 && (
            <Table>
              <thead>
                <tr>
                  <th style={thStyle}>Posted</th>
                  <th style={thStyle}>Description</th>
                  <th style={thStyle}>Status</th>
                  <th style={{ ...thStyle, textAlign: "right" }}>Amount</th>
                </tr>
              </thead>
              <tbody>
                {txnList.map((t) => (
                  <tr key={t.id}>
                    <td style={tdStyle}>
                      {t.posted_at
                        ? new Date(t.posted_at).toLocaleDateString(undefined, {
                            month: "2-digit",
                            day: "2-digit",
                          })
                        : "—"}
                    </td>
                    <td style={tdStyle}>{t.description || "—"}</td>
                    <td style={tdStyle}>{t.status}</td>
                    <td
                      style={{ ...tdStyle, textAlign: "right" }}
                      className={t.amount >= 0 ? styles.amountPos : styles.amountNeg}
                    >
                      {t.amount >= 0 ? "+" : ""}${Math.abs(t.amount).toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      )}
    </PageShell>
  );
}

function AccountCard({
  acct, onDisconnect, disconnectBusy, anyBusy,
}: {
  acct: BankAccountRow;
  onDisconnect: () => void;
  disconnectBusy: boolean;
  anyBusy: boolean;
}) {
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
      {/* Nickname editor was a Flask form posting to a route that
          went away in PR #550 — re-add when the API endpoint
          ships (separate PR).  For now the row's label falls back
          to display_name → institution_name + last4. */}
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
