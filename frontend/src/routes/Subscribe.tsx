import { useState } from "react";
import { Link } from "react-router-dom";

import { startCheckout } from "../api/billing";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";

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
      <main style={pageStyle}>
        <h1 style={titleStyle}>Subscribe</h1>
        <p style={emptyStyle}>Sign in first to choose a plan.</p>
      </main>
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
    <main style={pageStyle}>
      <header style={{ marginBottom: "1.5rem" }}>
        <h1 style={titleStyle}>Choose a plan</h1>
        <p
          style={{
            margin: "0.35rem 0 0",
            color: "var(--db-text-muted, #a3a3a3)",
            fontSize: "0.95rem",
          }}
        >
          Cancel any time from <Link to="/settings" style={linkStyle}>Settings</Link>.
          Yearly billing saves two months.
        </p>
      </header>

      {error && (
        <p
          role="alert"
          style={{
            ...emptyStyle,
            color: "var(--db-negative, #ff3b30)",
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
          <article key={p.slug} style={tileStyle}>
            <h2 style={tileTitle}>{p.label}</h2>
            <p style={tilePrice}>
              <span style={mono}>{p.price}</span>{" "}
              <span style={{ color: "var(--db-text-muted, #a3a3a3)" }}>
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
          </article>
        ))}
      </div>
    </main>
  );
}

const pageStyle: React.CSSProperties = {
  flex: 1,
  display: "flex",
  flexDirection: "column",
  padding: "2rem 1.5rem",
  maxWidth: "62rem",
  margin: "0 auto",
  width: "100%",
  boxSizing: "border-box",
};

const titleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "clamp(1.5rem, 3.5vw, 2rem)",
  fontWeight: 600,
  margin: 0,
};

const tileStyle: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem",
  padding: "1.5rem",
  display: "flex",
  flexDirection: "column",
  gap: "0.75rem",
};

const tileTitle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
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
  color: "var(--db-text-muted, #a3a3a3)",
  fontSize: "0.9rem",
  flex: 1,
};

const primaryBtn: React.CSSProperties = {
  background: "var(--db-accent, #3fff00)",
  color: "var(--db-on-accent, #0a0a0a)",
  border: "none",
  borderRadius: "0.5rem",
  padding: "0.7rem 1rem",
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "0.95rem",
  fontWeight: 600,
};

const mono: React.CSSProperties = {
  fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
};

const linkStyle: React.CSSProperties = {
  color: "var(--db-accent, #3fff00)",
  textDecoration: "none",
};

const emptyStyle: React.CSSProperties = {
  margin: 0,
  padding: "1rem 0",
  textAlign: "center",
  color: "var(--db-text-muted, #a3a3a3)",
};
