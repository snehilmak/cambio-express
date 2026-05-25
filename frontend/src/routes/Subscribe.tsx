import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  fetchSubscriptionSummary, openBillingPortal, startCheckout,
  type SubscriptionSummary,
} from "../api/billing";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  Breadcrumbs,
  Alert, Button, Card, Empty, Loading, PageHeader, PageShell, Pill,
} from "../components/ui";
import styles from "./Subscribe.module.css";

// Plan picker at /app/subscribe.  Mirrors the legacy /subscribe
// Jinja form.  Two flows:
//
//   - Trial / inactive store → each tile POSTs /billing/checkout,
//     redirects to Stripe Checkout.  Webhook flips Store.plan on
//     success.
//   - Already-paid store → the active tile shows "Current plan"
//     (no Subscribe button), the others swap to "Change to <plan>"
//     which opens the Stripe Billing Portal (Stripe handles
//     upgrades / downgrades within a single subscription rather
//     than minting a parallel one through Checkout).

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
  const [summary, setSummary] = useState<SubscriptionSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (identity == null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- skip the fetch when not signed in; the early return below handles the UI
      setLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const s = await fetchSubscriptionSummary();
        if (!cancelled) setSummary(s);
      } catch {
        // Plan picker should still render even if the summary
        // fetch fails — fall back to the no-current-plan view.
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [identity]);

  if (identity == null) {
    return (
      <PageShell maxWidth="62rem">
        <PageHeader title="Subscribe" />
        <Empty>Sign in first to choose a plan.</Empty>
      </PageShell>
    );
  }

  if (loading) {
    return (
      <PageShell maxWidth="62rem">
        <PageHeader title="Choose a plan" />
        <Loading />
      </PageShell>
    );
  }

  const currentPlan = summary?.store.plan ?? null;
  const hasPaid = Boolean(summary?.has_paid_plan);
  const cancelling = Boolean(summary?.cancel_at_period_end);

  async function pickPlan(slug: string) {
    setError(null);
    setBusy(slug);
    try {
      if (hasPaid) {
        // Already paid → Stripe handles upgrade/downgrade in the
        // Billing Portal.  Avoids minting a parallel subscription
        // through Checkout.
        const result = await openBillingPortal();
        window.location.assign(result.url);
      } else {
        const result = await startCheckout(slug);
        window.location.assign(result.url);
      }
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message
        : hasPaid ? "Could not open the billing portal."
        : "Could not start checkout.",
      );
      setBusy(null);
    }
  }

  return (
    <PageShell maxWidth="62rem">

      <Breadcrumbs crumbs={[{ label: "Subscribe" }]} />

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

      {hasPaid && summary && cancelling && (
        <Alert tone="warning">
          Your <strong>{summary.plan_label}</strong> subscription is{" "}
          <strong>cancelled</strong>
          {summary.cancel_at
            ? <> — active until <strong>{summary.cancel_at}</strong></>
            : null
          }.
          {" "}To keep your access, resubscribe below before it expires.
        </Alert>
      )}
      {hasPaid && summary && !cancelling && (
        <Alert tone="info">
          You're currently on{" "}
          <strong>{summary.plan_label}</strong>
          {summary.plan_price ? ` (${summary.plan_price})` : ""}.
          {" "}Switching plans opens the Stripe billing portal so any
          credit / proration is handled cleanly.
        </Alert>
      )}

      {error && <Alert tone="error">{error}</Alert>}

      <div className={styles.grid}>
        {PLANS.map((p) => {
          const isCurrent = currentPlan === p.slug;
          const isCancelledCurrent = isCurrent && cancelling;
          return (
            <Card key={p.slug} padding="1.5rem" className={styles.tile}>
              <div className={styles.tileHeaderRow}>
                <h2 className={styles.tileTitle}>{p.label}</h2>
                {isCancelledCurrent && <Pill tone="warning">Cancelled</Pill>}
                {isCurrent && !cancelling && <Pill tone="accent">Current plan</Pill>}
              </div>
              <p className={styles.tilePrice}>
                <span className={styles.mono}>{p.price}</span>{" "}
                <span className={styles.cadence}>{p.cadence}</span>
              </p>
              <p className={styles.tileBlurb}>{p.blurb}</p>
              <Button
                onClick={() => pickPlan(p.slug)}
                busy={busy === p.slug}
                disabled={busy !== null || (isCurrent && !cancelling)}
                tone={(isCurrent && !cancelling) ? "secondary" : "primary"}
              >
                {isCancelledCurrent ? "Resubscribe"
                  : isCurrent ? "Current plan"
                  : busy === p.slug ? "Redirecting…"
                  : hasPaid ? `Switch to ${p.label}`
                  : "Subscribe"}
              </Button>
            </Card>
          );
        })}
      </div>
    </PageShell>
  );
}
