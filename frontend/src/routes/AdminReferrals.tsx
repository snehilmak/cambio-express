import { useState } from "react";

import {
  useReferralCode,
  type ReferralRedemptionRow,
} from "../api/admin";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  ButtonLink, Empty, ErrorState, Loading, PageHeader, PageShell, tokens,
} from "../components/ui";

// /app/account/referrals — admin self-service for the store's
// referral code: copy-to-clipboard for code + share link, history
// of redemptions, lifetime credits-earned. Paid-plan only — trial
// admins see an upsell card pointing at /app/subscribe.

export default function AdminReferrals() {
  const identity = getCurrentIdentity();
  const { data, isLoading, isError, error, refetch } = useReferralCode();

  if (identity?.role !== "admin" && identity?.role !== "owner") {
    return (
      <PageShell maxWidth="60rem">
        <PageHeader title="Referrals" />
        <Empty>You need a store-admin sign-in to manage referrals.</Empty>
      </PageShell>
    );
  }

  // Trial-plan stores get a 409 with a clear upsell.
  if (isError && error instanceof ApiError && error.status === 409) {
    return (
      <PageShell maxWidth="60rem">
        <PageHeader title="Referrals" />
        <section style={cardStyle}>
          <h2 style={cardTitleStyle}>Unlock referrals on a paid plan</h2>
          <p style={leadStyle}>
            Refer another store, both of you get credit. Activate Basic
            or Pro and your referral code mints automatically.
          </p>
          <ButtonLink href="/app/subscribe" tone="primary" style={{ marginTop: "1rem" }}>
            See plans →
          </ButtonLink>
        </section>
      </PageShell>
    );
  }

  return (
    <PageShell maxWidth="60rem">
      <PageHeader title="Referrals" />

      {isLoading && <Loading />}
      {isError && !(error instanceof ApiError && error.status === 409) && (
        <ErrorState
          message={error instanceof Error ? error.message : "Could not load"}
          onRetry={() => { void refetch(); }}
        />
      )}

      {data && (
        <>
          <Hero
            code={data.code}
            shareUrl={data.share_url}
            rewardSelfCents={data.reward_self_cents}
            rewardRefereeCents={data.reward_referee_cents}
          />

          <section style={statsRowStyle}>
            <StatCard
              label="Successful referrals"
              value={String(data.redeemed_count)}
              sub="converted to paid"
              accent="var(--db-warning, #ffb020)"
            />
            <StatCard
              label="Credits earned"
              value={`$${(data.credits_earned_cents / 100).toFixed(2)}`}
              sub="applied to your Stripe balance"
              accent="var(--db-neon, #3fff00)"
            />
            <StatCard
              label="Status"
              value={data.is_active ? "Active" : "Disabled"}
              sub={data.is_active
                ? "earning credits"
                : "contact support to re-enable"}
              accent="var(--db-info, #5ea9ff)"
            />
          </section>

          <section style={howBoxStyle}>
            <strong>How it works.</strong>{" "}
            Give the code (or the link) to anyone signing up.
            Their ${(data.reward_referee_cents / 100).toFixed(0)} posts
            the moment they start a paid plan; your $
            {(data.reward_self_cents / 100).toFixed(0)} posts the same
            moment. Credits apply to your next invoice via Stripe's
            customer-balance system — no coupon codes to redeem, no
            accounting from your side.
          </section>

          <section style={cardStyle}>
            <div style={cardHeaderStyle}>
              <span>History</span>
              <span style={{ marginLeft: "auto", color: tokens.textMuted, fontSize: "0.85rem", fontWeight: 400 }}>
                {data.redemptions.length}{" "}
                {data.redemptions.length === 1 ? "redemption" : "redemptions"}
              </span>
            </div>
            <HistoryTable rows={data.redemptions} />
          </section>
        </>
      )}
    </PageShell>
  );
}


function Hero({
  code, shareUrl, rewardSelfCents, rewardRefereeCents,
}: {
  code: string;
  shareUrl: string;
  rewardSelfCents: number;
  rewardRefereeCents: number;
}) {
  const [codeFlash, setCodeFlash] = useState(false);
  const [linkFlash, setLinkFlash] = useState(false);

  function copy(text: string, after: () => void) {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text).then(after);
    } else {
      const ta = document.createElement("textarea");
      ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); } finally { ta.remove(); }
      after();
    }
  }

  return (
    <section style={heroStyle}>
      <div style={heroLabelStyle}>Your referral code</div>
      <div style={heroCodeStyle}>{code}</div>
      <p style={heroMetaStyle}>
        Share this with friends who run a money-service business.
        When they sign up and subscribe,{" "}
        <strong>they get ${(rewardRefereeCents / 100).toFixed(0)} off</strong>{" "}
        their first paid month and{" "}
        <strong>you get ${(rewardSelfCents / 100).toFixed(0)} off</strong>{" "}
        yours — applied automatically to your next invoice as a credit.
      </p>
      <div style={shareRowStyle}>
        <input
          readOnly
          value={shareUrl}
          style={shareInputStyle}
          onFocus={(e) => e.currentTarget.select()}
        />
        <button
          type="button"
          style={btnGoldStyle}
          onClick={() => copy(code, () => {
            setCodeFlash(true);
            setTimeout(() => setCodeFlash(false), 1400);
          })}
        >
          {codeFlash ? "Copied!" : "Copy code"}
        </button>
        <button
          type="button"
          style={btnGoldStyle}
          onClick={() => copy(shareUrl, () => {
            setLinkFlash(true);
            setTimeout(() => setLinkFlash(false), 1400);
          })}
        >
          {linkFlash ? "Copied!" : "Copy link"}
        </button>
      </div>
    </section>
  );
}


function StatCard({
  label, value, sub, accent,
}: {
  label: string;
  value: string;
  sub: string;
  accent: string;
}) {
  return (
    <div style={{
      ...cardStyle,
      borderLeft: `3px solid ${accent}`,
      padding: "1rem 1.1rem",
    }}>
      <div style={statLabelStyle}>{label}</div>
      <div style={statValueStyle}>{value}</div>
      <div style={statSubStyle}>{sub}</div>
    </div>
  );
}


function HistoryTable({ rows }: { rows: ReferralRedemptionRow[] }) {
  if (rows.length === 0) {
    return (
      <p style={emptyTableStyle}>
        No referrals yet. Share your code above — your first credit
        posts the moment someone subscribes.
      </p>
    );
  }
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.92rem" }}>
        <thead>
          <tr>
            {["Date", "Referred store", "Your $", "Their $"].map((h) => (
              <th key={h} style={thStyle}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.referee_store_id}-${r.redeemed_at}`}>
              <td style={cellStyle}>
                <span style={monoMuted}>
                  {r.redeemed_at ? r.redeemed_at.slice(0, 10) : "—"}
                </span>
              </td>
              <td style={cellStyle}>#{r.referee_store_id}</td>
              <td style={cellStyle}>
                {r.self_credit_applied ? (
                  <>
                    <Badge color="green">Credited</Badge>
                    {r.stripe_self_txn_id && (
                      <span style={{
                        marginLeft: "0.5rem", ...monoMuted,
                      }}>{r.stripe_self_txn_id}</span>
                    )}
                  </>
                ) : (
                  <Badge color="yellow">Pending</Badge>
                )}
              </td>
              <td style={cellStyle}>
                {r.referee_credit_applied
                  ? <Badge color="green">Credited</Badge>
                  : <Badge color="yellow">Pending</Badge>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


function Badge({
  children, color,
}: { children: React.ReactNode; color: "green" | "yellow" }) {
  const palette = color === "green"
    ? { bg: "rgba(63,255,0,0.10)", fg: "#3fff00", border: "rgba(63,255,0,0.35)" }
    : { bg: "rgba(255,176,32,0.10)", fg: "#ffb020", border: "rgba(255,176,32,0.35)" };
  return (
    <span style={{
      display: "inline-block",
      padding: "0.15rem 0.5rem",
      borderRadius: "999px",
      background: palette.bg,
      color: palette.fg,
      border: `1px solid ${palette.border}`,
      fontSize: "0.78rem",
      fontWeight: 500,
    }}>{children}</span>
  );
}


const cardStyle: React.CSSProperties = {
  background: tokens.surface2,
  border: `1px solid ${tokens.border}`,
  borderRadius: "0.75rem", padding: "1.25rem",
};

const cardTitleStyle: React.CSSProperties = {
  margin: "0 0 0.6rem", fontSize: "1.1rem", fontWeight: 600,
};

const cardHeaderStyle: React.CSSProperties = {
  display: "flex", alignItems: "center",
  fontWeight: 600, fontSize: "0.95rem",
  marginBottom: "0.75rem",
};

const leadStyle: React.CSSProperties = {
  margin: 0, color: tokens.textMuted,
  fontSize: "0.95rem", lineHeight: 1.55,
};

const heroStyle: React.CSSProperties = {
  background: "linear-gradient(135deg, #0a1a2e 0%, #050d1a 100%)",
  border: "1px solid #1f3656",
  borderRadius: "1rem",
  padding: "1.75rem",
  marginBottom: "1rem",
  color: "#e9eef5",
};

const heroLabelStyle: React.CSSProperties = {
  fontSize: "0.7rem",
  letterSpacing: "0.08em",
  textTransform: "uppercase",
  color: "#ffd96e",
  fontWeight: 600,
};

const heroCodeStyle: React.CSSProperties = {
  fontFamily: tokens.fontMono,
  fontSize: "2.2rem",
  color: "#ffd96e",
  marginTop: "0.4rem",
  letterSpacing: "0.15em",
};

const heroMetaStyle: React.CSSProperties = {
  marginTop: "0.85rem",
  fontSize: "0.9rem",
  color: "rgba(255,255,255,0.78)",
  lineHeight: 1.55,
};

const shareRowStyle: React.CSSProperties = {
  marginTop: "1rem",
  display: "flex",
  gap: "0.6rem",
  flexWrap: "wrap",
  alignItems: "center",
};

const shareInputStyle: React.CSSProperties = {
  flex: 1,
  minWidth: "16rem",
  background: "rgba(255,255,255,0.07)",
  color: "#fff",
  border: "1px solid rgba(255,255,255,0.22)",
  padding: "0.65rem 0.85rem",
  borderRadius: "0.5rem",
  fontSize: "0.85rem",
  fontFamily: tokens.fontMono,
};

const btnGoldStyle: React.CSSProperties = {
  background: "#d4a92a",
  color: "#fff",
  border: "none",
  padding: "0.65rem 1.1rem",
  borderRadius: "0.5rem",
  fontSize: "0.88rem",
  fontWeight: 600,
  cursor: "pointer",
  fontFamily: tokens.fontBody,
};

const statsRowStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
  gap: "0.85rem",
  marginBottom: "1rem",
};

const statLabelStyle: React.CSSProperties = {
  fontSize: "0.7rem", letterSpacing: "0.06em",
  textTransform: "uppercase", fontWeight: 600,
  color: tokens.textMuted,
};

const statValueStyle: React.CSSProperties = {
  fontFamily: tokens.fontDisplay,
  fontSize: "1.6rem",
  fontWeight: 600,
  marginTop: "0.35rem",
};

const statSubStyle: React.CSSProperties = {
  marginTop: "0.25rem",
  fontSize: "0.78rem",
  color: tokens.textMuted,
};

const howBoxStyle: React.CSSProperties = {
  background: tokens.surface2,
  borderLeft: "3px solid #d4a92a",
  borderRadius: "0.4rem",
  padding: "0.85rem 1.1rem",
  fontSize: "0.88rem",
  lineHeight: 1.6,
  color: tokens.text,
  marginBottom: "1rem",
};

const thStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "0.6rem 0.75rem",
  color: tokens.textMuted,
  fontWeight: 500,
  fontSize: "0.78rem",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  borderBottom: `1px solid ${tokens.border}`,
};

const cellStyle: React.CSSProperties = {
  padding: "0.7rem 0.75rem",
  borderBottom: `1px solid ${tokens.borderSubtle}`,
};

const monoMuted: React.CSSProperties = {
  fontFamily: tokens.fontMono,
  fontSize: "0.85rem",
  color: tokens.textMuted,
};

const emptyTableStyle: React.CSSProperties = {
  padding: "1.4rem 0", textAlign: "center",
  color: tokens.textMuted,
  fontSize: "0.9rem",
};
