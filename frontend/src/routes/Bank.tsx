import { useState } from "react";

import {
  startStripeConnect,
  useBankAccounts,
  useBankTransactions,
  type BankAccountRow,
} from "../api/bankSync";
import {
  Button, ButtonLink, Card, EmptyState, ErrorState, Loading, PageHeader,
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
// The Connect button dynamically loads Stripe.js (https://js.stripe.com/v3/),
// posts to the existing legacy /bank/stripe/connect endpoint to mint
// a Financial Connections client_secret, opens Stripe's hosted modal,
// then navigates to /bank/stripe/return so the server can persist the
// linked accounts. Account-level mutations (refresh, disconnect, set
// nickname, sync transactions) submit to the existing Flask form-POST
// endpoints that 302 back here.
export default function Bank() {
  const accounts = useBankAccounts();
  const recent = useBankTransactions({ per_page: 10, page: 1 });
  const [connectError, setConnectError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleConnect() {
    setConnectError(null);
    setBusy(true);
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
      window.location.href = session.returnUrl;
    } catch (e) {
      setConnectError(e instanceof Error ? e.message : "Connect failed.");
      setBusy(false);
    }
  }

  const accountList = accounts.data?.rows ?? [];
  const txnList = recent.data?.rows ?? [];
  const atCap = accountList.length >= 6; // mirror MAX_BANK_ACCOUNTS_PER_STORE

  return (
    <PageShell maxWidth="70rem" gap="1.25rem">
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
              <form method="POST" action="/bank/stripe/refresh">
                <Button type="submit" tone="secondary" size="sm">Refresh</Button>
              </form>
              {!atCap && (
                <Button
                  size="sm"
                  busy={busy}
                  disabled={busy}
                  onClick={handleConnect}
                >
                  {busy ? "Opening Stripe…" : "＋ Connect another"}
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
              busy={busy}
              disabled={busy}
              onClick={handleConnect}
              style={{ marginTop: "1rem" }}
            >
              {busy ? "Opening Stripe…" : "Connect Bank via Stripe →"}
            </Button>
          </div>
        )}

        {accountList.length > 0 && (
          <div className={styles.accountGrid}>
            {accountList.map((a) => (
              <AccountCard key={a.id} acct={a} />
            ))}
          </div>
        )}
      </Card>

      {accountList.length > 0 && (
        <Card>
          <header className={styles.sectionHeader}>
            <span className={styles.cardTitle}>Recent Transactions</span>
            <div className={styles.headerActions}>
              <form method="POST" action="/bank/stripe/sync-transactions">
                <Button type="submit" size="sm">Sync transactions</Button>
              </form>
              <ButtonLink href="/bank-transactions" tone="secondary" size="sm">
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

function AccountCard({ acct }: { acct: BankAccountRow }) {
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
        method="POST"
        action={`/bank/stripe/nickname/${acct.id}`}
        className={styles.nicknameForm}
      >
        <input
          type="text"
          name="nickname"
          value={nickname}
          onChange={(e) => setNickname(e.target.value)}
          placeholder="Set nickname (e.g. MSB Checking)"
          maxLength={60}
          className={styles.nicknameInput}
        />
        <Button type="submit" tone="secondary" size="sm">Save</Button>
      </form>
      <form
        method="POST"
        action={`/bank/stripe/disconnect/${acct.id}`}
        onSubmit={(e) => {
          if (!confirm(`Disconnect ${acct.label}?`)) e.preventDefault();
        }}
        className={styles.disconnectForm}
      >
        <Button type="submit" tone="danger" size="sm">Disconnect</Button>
      </form>
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
