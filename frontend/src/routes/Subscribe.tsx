import { useState } from "react";
import { Link } from "react-router-dom";

import { startCheckout } from "../api/billing";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  Card, Empty, PageHeader, PageShell, tokens,
} from "../components/ui";

// Plan picker at /app/subscribe. Mirrors the legacy /subscribe
// Jinja form. Each plan tile POSTs /api/v2/billing/checkout, gets
// a Stripe-hosted URL back, then `window.location.assign`s the
// browser to Stripe Checkout. The webhook handles the actual
// plan-flip on success — Stripe redirects back to /subscribe/success
// (legacy Jinja) which the cutover layer can route to a SPA twin
// in a follow-up.

interface PlanTile {
  slug: string;
  label: string;
  price: string;
  cadence: string;
  blurb: string;
}

const PLANS: PlanTile[] = [
  {
    slug:    "basic",
    label:   "Basic",
    price:   "$35",
    cadence: "/ month",
    blurb:   "Single store. Daily book + transfers + reports.",
  },
  {
    slug:    "basic_yearly",
    label:   "Basic (yearly)",
    price:   "$350",
    cadence: "/ year",
    blurb:   "Same as Basic, two months free.",
  },
  {
    slug:    "pro",
    label:   "Pro",
    price:   "$45",
    cadence: "/ month",
    blurb:   "Adds bank sync, owner umbrella, ACH batches.",
  },
  {
    slug:    "pro_yearly",
    label:   "Pro (yearly)",
    price:   "$450",
    cadence: "/ year",
    blurb:   "Same as Pro, two months free.",
  },
];

export default function Subscribe() {
  const identity = getCurrentIdentity();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (identity == null) {
    return (
      <PageShell maxWidth="62rem">
        <PageHeader title="Subscribe" />
        <Empty>Sign in first to choose a plan.</Empty>
      </PageShell>
    );
  }

  async function pickPlan(slug: string) {
    setError(null);
    setBusy(slug);
    try {
      const result = await startCheckout(slug);
      window.location.assign(result.url);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not start checkout.",
      );
      setBusy(null);
    }
  }

  return (
    <PageShell maxWidth="62rem">
      <PageHeader
        title="Choose a plan"
        subtitle={(
          <>
            Cancel any time from <Link to="/settings" style={linkStyle}>Settings</Link>.
            Yearly billing saves two months.
          </>
        )}
      />

      {error && (
        <p
          role="alert"
          style={{
            margin: 0,
            padding: "1rem 0",
            textAlign: "center",
            color: tokens.negative,
            marginBottom: "1rem",
          }}
        >
          {error}
        </p>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(15rem, 1fr))",
          gap: "1rem",
        }}
      >
        {PLANS.map((p) => (
          <Card key={p.slug} padding="1.5rem" style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <h2 style={tileTitle}>{p.label}</h2>
            <p style={tilePrice}>
              <span style={mono}>{p.price}</span>{" "}
              <span style={{ color: tokens.textMuted }}>
                {p.cadence}
              </span>
            </p>
            <p style={tileBlurb}>{p.blurb}</p>
            <button
              type="button"
              onClick={() => pickPlan(p.slug)}
              disabled={busy !== null}
              style={{
                ...primaryBtn,
                opacity: busy !== null ? 0.6 : 1,
                cursor: busy !== null ? "wait" : "pointer",
              }}
            >
              {busy === p.slug ? "Redirecting…" : "Subscribe"}
            </button>
          </Card>
        ))}
      </div>
    </PageShell>
  );
}

const tileTitle: React.CSSProperties = {
  fontFamily: tokens.fontDisplay,
  fontSize: "1.2rem",
  fontWeight: 600,
  margin: 0,
};

const tilePrice: React.CSSProperties = {
  fontSize: "1.6rem",
  margin: 0,
  fontWeight: 600,
};

const tileBlurb: React.CSSProperties = {
  margin: 0,
  color: tokens.textMuted,
  fontSize: "0.9rem",
  flex: 1,
};

const primaryBtn: React.CSSProperties = {
  background: tokens.accent,
  color: tokens.onAccent,
  border: "none",
  borderRadius: "0.5rem",
  padding: "0.7rem 1rem",
  fontFamily: tokens.fontDisplay,
  fontSize: "0.95rem",
  fontWeight: 600,
};

const mono: React.CSSProperties = {
  fontFamily: tokens.fontMono,
};

const linkStyle: React.CSSProperties = {
  color: tokens.accent,
  textDecoration: "none",
};
