import { useState } from "react";
import { Link } from "react-router-dom";

import { startCheckout } from "../api/billing";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  Alert, Button, Card, Empty, PageHeader, PageShell,
} from "../components/ui";
import styles from "./Subscribe.module.css";

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
            Cancel any time from{" "}
            <Link to="/settings" className={styles.inlineLink}>Settings</Link>.
            Yearly billing saves two months.
          </>
        )}
      />

      {error && <Alert tone="error">{error}</Alert>}

      <div className={styles.grid}>
        {PLANS.map((p) => (
          <Card key={p.slug} padding="1.5rem" className={styles.tile}>
            <h2 className={styles.tileTitle}>{p.label}</h2>
            <p className={styles.tilePrice}>
              <span className={styles.mono}>{p.price}</span>{" "}
              <span className={styles.cadence}>{p.cadence}</span>
            </p>
            <p className={styles.tileBlurb}>{p.blurb}</p>
            <Button
              onClick={() => pickPlan(p.slug)}
              busy={busy === p.slug}
              disabled={busy !== null}
            >
              {busy === p.slug ? "Redirecting…" : "Subscribe"}
            </Button>
          </Card>
        ))}
      </div>
    </PageShell>
  );
}
