import { useState } from "react";
import { Link } from "react-router-dom";

import {
  startStripeConnect,
  useBankAccounts,
  useBankTransactions,
  type BankAccountRow,
} from "../api/bankSync";
import {
  Card, EmptyState, ErrorState, Loading, PageHeader, PageShell,
  TableSkeleton, tokens,
} from "../components/ui";

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
        <header style={sectionHeader}>
          <span style={cardTitle}>
            Connected Bank Accounts
            {accountList.length > 0 && (
              <span style={mutedInline}> {accountList.length} of 6</span>
            )}
          </span>
          {accountList.length > 0 && (
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <form method="POST" action="/bank/stripe/refresh">
                <button type="submit" style={btnOutline}>Refresh</button>
              </form>
              {!atCap && (
                <button
                  type="button"
                  style={btnPrimary}
                  disabled={busy}
                  onClick={handleConnect}
                >
                  {busy ? "Opening Stripe…" : "＋ Connect another"}
                </button>
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
          <div style={emptyState}>
            <h3 style={{ margin: "0 0 0.5rem", fontWeight: 600 }}>
              Connect your bank
            </h3>
            <p style={muted}>
              Link your accounts securely through Stripe Financial Connections.
              We only see balances — never your bank login.
            </p>
            <button
              type="button"
              style={{ ...btnPrimary, marginTop: "1rem" }}
              disabled={busy}
              onClick={handleConnect}
            >
              {busy ? "Opening Stripe…" : "Connect Bank via Stripe →"}
            </button>
          </div>
        )}

        {accountList.length > 0 && (
          <div style={accountGrid}>
            {accountList.map((a) => (
              <AccountCard key={a.id} acct={a} />
            ))}
          </div>
        )}
      </Card>

      {accountList.length > 0 && (
        <Card>
          <header style={sectionHeader}>
            <span style={cardTitle}>Recent Transactions</span>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <form method="POST" action="/bank/stripe/sync-transactions">
                <button type="submit" style={btnPrimary}>
                  Sync transactions
                </button>
              </form>
              <Link to="/bank-transactions" style={btnOutlineLink}>
                View all →
              </Link>
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
            <table style={tableStyle}>
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
                      style={{
                        ...tdStyle,
                        textAlign: "right",
                        color: t.amount >= 0 ? tokens.accent : tokens.negative,
                      }}
                    >
                      {t.amount >= 0 ? "+" : ""}${Math.abs(t.amount).toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      )}
    </PageShell>
  );
}

function AccountCard({ acct }: { acct: BankAccountRow }) {
  const [nickname, setNickname] = useState(acct.nickname || "");
  return (
    <div style={accountCard}>
      <div style={mutedSmall}>
        {acct.institution_name || "Bank"}
        {acct.category && ` · ${acct.category}`}
      </div>
      <div style={{ fontWeight: 600, marginTop: "0.25rem" }}>
        {acct.label}
      </div>
      <div style={balance}>
        ${acct.last_balance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </div>
      <div style={mutedSmall}>
        {acct.last_balance_as_of
          ? `As of ${new Date(acct.last_balance_as_of).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}`
          : "Balance not yet refreshed."}
      </div>
      <form
        method="POST"
        action={`/bank/stripe/nickname/${acct.id}`}
        style={{ marginTop: "0.5rem", display: "flex", gap: "0.4rem" }}
      >
        <input
          type="text"
          name="nickname"
          value={nickname}
          onChange={(e) => setNickname(e.target.value)}
          placeholder="Set nickname (e.g. MSB Checking)"
          maxLength={60}
          style={{
            flex: 1,
            padding: "0.4rem 0.5rem",
            background: tokens.surface,
            border: `1px solid ${tokens.border}`,
            color: "inherit",
            borderRadius: "0.4rem",
            fontSize: "0.85rem",
          }}
        />
        <button type="submit" style={btnOutlineSm}>
          Save
        </button>
      </form>
      <form
        method="POST"
        action={`/bank/stripe/disconnect/${acct.id}`}
        onSubmit={(e) => {
          if (!confirm(`Disconnect ${acct.label}?`)) e.preventDefault();
        }}
        style={{ marginTop: "0.5rem", textAlign: "right" }}
      >
        <button type="submit" style={btnDangerSm}>Disconnect</button>
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

const sectionHeader: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  gap: "1rem",
  marginBottom: "1rem",
};
const cardTitle: React.CSSProperties = {
  fontWeight: 600,
};
const mutedInline: React.CSSProperties = {
  fontWeight: 400,
  marginLeft: "0.5rem",
  fontSize: "0.85rem",
  color: tokens.textMuted,
};
const muted: React.CSSProperties = {
  color: tokens.textMuted,
  margin: 0,
};
const mutedSmall: React.CSSProperties = {
  ...muted,
  fontSize: "0.75rem",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
};
const emptyState: React.CSSProperties = {
  textAlign: "center",
  padding: "1.5rem 1rem",
};
const accountGrid: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
  gap: "1rem",
};
const accountCard: React.CSSProperties = {
  background: tokens.surface,
  border: `1px solid ${tokens.border}`,
  borderRadius: "0.5rem",
  padding: "1rem",
};
const balance: React.CSSProperties = {
  fontFamily: tokens.fontMono,
  fontSize: "1.5rem",
  fontWeight: 700,
  margin: "0.5rem 0 0.25rem",
};
const btnPrimary: React.CSSProperties = {
  background: tokens.accent,
  color: "#000",
  border: "none",
  padding: "0.4rem 0.85rem",
  borderRadius: "0.5rem",
  fontWeight: 600,
  fontSize: "0.85rem",
  cursor: "pointer",
};
const btnOutline: React.CSSProperties = {
  background: "transparent",
  color: "inherit",
  border: `1px solid ${tokens.border}`,
  padding: "0.4rem 0.85rem",
  borderRadius: "0.5rem",
  fontSize: "0.85rem",
  cursor: "pointer",
};
const btnOutlineLink: React.CSSProperties = {
  ...btnOutline,
  textDecoration: "none",
  display: "inline-block",
};
const btnOutlineSm: React.CSSProperties = {
  ...btnOutline,
  padding: "0.25rem 0.6rem",
  fontSize: "0.75rem",
};
const btnDangerSm: React.CSSProperties = {
  ...btnOutlineSm,
  color: tokens.negative,
  borderColor: tokens.negative,
};
const tableStyle: React.CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: "0.9rem",
};
const thStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "0.5rem 0.75rem",
  borderBottom: `1px solid ${tokens.border}`,
  fontWeight: 500,
  fontSize: "0.75rem",
  textTransform: "uppercase",
  color: tokens.textMuted,
};
const tdStyle: React.CSSProperties = {
  padding: "0.5rem 0.75rem",
  borderBottom: `1px solid ${tokens.borderSubtle}`,
};
