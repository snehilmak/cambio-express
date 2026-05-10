import { useState } from "react";
import { Link } from "react-router-dom";

import {
  startStripeConnect,
  useBankAccounts,
  useBankTransactions,
  type BankAccountRow,
} from "../api/bankSync";

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
    <main style={pageStyle}>
      <h1 style={titleStyle}>Bank Accounts</h1>

      {connectError && <div style={errorStyle}>{connectError}</div>}

      <section style={cardStyle}>
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

        {accounts.isLoading && <p style={muted}>Loading…</p>}
        {accounts.isError && (
          <p style={errorStyle}>Couldn't load accounts.</p>
        )}

        {!accounts.isLoading && accountList.length === 0 && (
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
      </section>

      {accountList.length > 0 && (
        <section style={cardStyle}>
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

          {recent.isLoading && <p style={muted}>Loading…</p>}
          {!recent.isLoading && txnList.length === 0 && (
            <p style={muted}>
              No transactions pulled yet. Click <strong>Sync transactions</strong> above to fetch.
            </p>
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
                        color: t.amount >= 0 ? "var(--db-positive, #3fff00)" : "var(--db-negative, #ff3b30)",
                      }}
                    >
                      {t.amount >= 0 ? "+" : ""}${Math.abs(t.amount).toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}
    </main>
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
            background: "var(--db-surface-1, #0a0a0a)",
            border: "1px solid var(--db-border, #262626)",
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

const pageStyle: React.CSSProperties = {
  flex: 1,
  padding: "2rem 1.5rem",
  maxWidth: "70rem",
  margin: "0 auto",
  width: "100%",
  boxSizing: "border-box",
  display: "flex",
  flexDirection: "column",
  gap: "1.25rem",
};
const titleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "clamp(1.5rem, 3.5vw, 2rem)",
  fontWeight: 600,
  margin: 0,
};
const cardStyle: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem",
  padding: "1.25rem",
};
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
  color: "var(--db-text-muted, #a3a3a3)",
};
const muted: React.CSSProperties = {
  color: "var(--db-text-muted, #a3a3a3)",
  margin: 0,
};
const mutedSmall: React.CSSProperties = {
  ...muted,
  fontSize: "0.75rem",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
};
const errorStyle: React.CSSProperties = {
  color: "var(--db-negative, #ff3b30)",
  background: "rgba(255,59,48,0.08)",
  border: "1px solid rgba(255,59,48,0.4)",
  padding: "0.75rem 1rem",
  borderRadius: "0.5rem",
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
  background: "var(--db-surface-1, #0a0a0a)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem",
  padding: "1rem",
};
const balance: React.CSSProperties = {
  fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
  fontSize: "1.5rem",
  fontWeight: 700,
  margin: "0.5rem 0 0.25rem",
};
const btnPrimary: React.CSSProperties = {
  background: "var(--db-accent, #3fff00)",
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
  border: "1px solid var(--db-border, #262626)",
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
  color: "var(--db-negative, #ff3b30)",
  borderColor: "var(--db-negative, #ff3b30)",
};
const tableStyle: React.CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: "0.9rem",
};
const thStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "0.5rem 0.75rem",
  borderBottom: "1px solid var(--db-border, #262626)",
  fontWeight: 500,
  fontSize: "0.75rem",
  textTransform: "uppercase",
  color: "var(--db-text-muted, #a3a3a3)",
};
const tdStyle: React.CSSProperties = {
  padding: "0.5rem 0.75rem",
  borderBottom: "1px solid var(--db-border-subtle, #1f1f1f)",
};
