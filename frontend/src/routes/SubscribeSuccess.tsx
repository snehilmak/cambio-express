import { useEffect, useState } from "react";

import { useStoreInfo } from "../api/account";
import { getCurrentIdentity } from "../lib/auth";
import { tokens } from "../components/ui";

// /app/subscribe/success — Stripe Checkout's success_url. Stripe
// redirects here right after the customer pays; the
// checkout.session.completed webhook bumps `Store.plan` to basic
// or pro shortly after (Stripe sends both signals roughly
// simultaneously, but the order isn't guaranteed). When the user
// lands here we may briefly still see plan="trial"; we poll
// store-info every 2s for up to ~30s so the success message
// flips from "Payment received, activating…" to "You're on
// Basic/Pro" without the user having to refresh.

const POLL_INTERVAL_MS = 2000;
const POLL_MAX_TICKS   = 15;  // ~30s total

export default function SubscribeSuccess() {
  const identity = getCurrentIdentity();
  const { data, refetch } = useStoreInfo();
  const [ticks, setTicks] = useState(0);

  const plan = data?.store.plan ?? "";
  const activated = plan === "basic" || plan === "pro";

  useEffect(() => {
    if (activated || ticks >= POLL_MAX_TICKS) return;
    const t = setTimeout(() => {
      refetch();
      setTicks((n) => n + 1);
    }, POLL_INTERVAL_MS);
    return () => clearTimeout(t);
  }, [activated, ticks, refetch]);

  if (!identity) {
    return (
      <main style={pageStyle}>
        <p style={{ color: tokens.textMuted }}>
          Sign in to view your subscription status.
        </p>
      </main>
    );
  }

  return (
    <main style={pageStyle}>
      {activated ? <Activated plan={plan} /> : <Pending />}
    </main>
  );
}


function Activated({ plan }: { plan: string }) {
  const planLabel = plan.charAt(0).toUpperCase() + plan.slice(1);
  return (
    <>
      <div style={{ ...badgeStyle, ...successBadge }}>
        <Check />
      </div>
      <h1 style={titleStyle}>You're on {planLabel}</h1>
      <p style={leadStyle}>
        Your account is active. You now have full access to all{" "}
        {planLabel} features.
      </p>
      <a href="/app/dashboard" style={btnPrimaryStyle}>
        Go to Dashboard →
      </a>
    </>
  );
}


function Pending() {
  return (
    <>
      <div style={{ ...badgeStyle, ...pendingBadge }}>
        <Clock />
      </div>
      <h1 style={titleStyle}>Payment Received</h1>
      <p style={leadStyle}>
        We've received your payment and are activating your account.
        This usually takes a few seconds — we'll flip this page
        automatically as soon as the upgrade lands.
      </p>
      <div style={{ display: "flex", gap: "0.75rem", justifyContent: "center" }}>
        <a href="/app/dashboard" style={btnPrimaryStyle}>
          Go to Dashboard →
        </a>
      </div>
    </>
  );
}


function Check() {
  return (
    <svg width="36" height="36" viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
         strokeLinejoin="round" aria-hidden>
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function Clock() {
  return (
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth="2" strokeLinecap="round"
         strokeLinejoin="round" aria-hidden>
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  );
}


const pageStyle: React.CSSProperties = {
  flex: 1, display: "flex", flexDirection: "column",
  alignItems: "center", textAlign: "center",
  padding: "4rem 1.5rem", maxWidth: "36rem",
  margin: "0 auto", width: "100%", boxSizing: "border-box",
};

const badgeStyle: React.CSSProperties = {
  width: "4.5rem", height: "4.5rem",
  borderRadius: "1.1rem",
  display: "inline-flex", alignItems: "center", justifyContent: "center",
  marginBottom: "1.25rem",
};

const successBadge: React.CSSProperties = {
  background: "rgba(63,255,0,0.1)",
  border: "1px solid rgba(63,255,0,0.3)",
  color: tokens.accent,
  boxShadow: "0 0 28px rgba(63,255,0,0.4)",
};

const pendingBadge: React.CSSProperties = {
  background: "rgba(255,176,32,0.08)",
  border: "1px solid rgba(255,176,32,0.3)",
  color: tokens.warning,
};

const titleStyle: React.CSSProperties = {
  fontFamily: tokens.fontDisplay,
  fontSize: "1.75rem", fontWeight: 600,
  color: tokens.text,
  letterSpacing: "-0.025em",
  margin: "0 0 0.6rem",
};

const leadStyle: React.CSSProperties = {
  color: tokens.textMuted,
  fontSize: "0.95rem",
  lineHeight: 1.7,
  margin: "0 0 2rem",
};

const btnPrimaryStyle: React.CSSProperties = {
  display: "inline-block",
  padding: "0.75rem 1.75rem",
  fontSize: "0.95rem",
  fontWeight: 600,
  background: tokens.accent,
  color: tokens.onAccent,
  border: "none", borderRadius: "0.5rem",
  textDecoration: "none",
};
