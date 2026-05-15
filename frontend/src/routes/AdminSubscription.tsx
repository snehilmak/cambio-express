import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  fetchSubscriptionSummary,
  openBillingPortal,
  toggleAddon,
  type SubscriptionAddon,
  type SubscriptionSummary,
} from "../api/billing";
import { ApiError } from "../lib/api";
import {
  Alert, Button, Card, ErrorState, Loading, PageHeader, PageShell, Pill,
} from "../components/ui";
import styles from "./AdminSubscription.module.css";

// /app/admin/subscription — current plan hero + account snapshot +
// add-ons grid + cancel modal. Mirrors the legacy
// /admin/subscription Jinja page; reads /api/v2/admin/subscription
// for the page state, calls /api/v2/billing/portal for the
// Manage / Cancel actions, and /api/v2/admin/addons/<key>/toggle
// for add-on flips.
export default function AdminSubscription() {
  const [data, setData] = useState<SubscriptionSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [showCancel, setShowCancel] = useState(false);

  async function load() {
    try {
      setData(await fetchSubscriptionSummary());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load.");
    }
  }
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial async fetch of subscription summary on mount; load() awaits the API then sets data/error state
    load();
  }, []);

  async function handlePortal(label: string) {
    setBusy(label);
    setError(null);
    try {
      const { url } = await openBillingPortal();
      window.location.assign(url);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Stripe error.");
      setBusy(null);
    }
  }

  async function handleToggle(addon: SubscriptionAddon) {
    setBusy(`addon:${addon.key}`);
    setError(null);
    try {
      await toggleAddon(addon.key);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Toggle failed.");
    } finally {
      setBusy(null);
    }
  }

  if (error && !data) {
    return (
      <PageShell maxWidth="70rem">
        <PageHeader title="Billing & Subscription" />
        <ErrorState message={error} onRetry={() => { void load(); }} />
      </PageShell>
    );
  }
  if (!data) {
    return (
      <PageShell maxWidth="70rem">
        <PageHeader title="Billing & Subscription" />
        <Loading />
      </PageShell>
    );
  }

  const { store, has_paid_plan, plan_label, plan_price } = data;
  const inactive = store.plan === "inactive";
  const trial = store.plan === "trial";

  return (
    <PageShell maxWidth="70rem">
      <PageHeader title="Billing & Subscription" />

      {error && <Alert tone="error">{error}</Alert>}

      {inactive && data.retention_days_left != null && (
        <Alert tone="error">
          Your subscription is canceled. Your store data is safe for{" "}
          <strong>
            {data.retention_days_left} more day
            {data.retention_days_left === 1 ? "" : "s"}
          </strong>
          . Resubscribe before then to pick up where you left off.
          <Link to="/subscribe" className={styles.resubLink}>
            Resubscribe
          </Link>
        </Alert>
      )}

      <div className={styles.twoColGrid}>
        <div className={styles.planHero}>
          <div className={styles.planEyebrow}>Current Plan</div>
          <div className={styles.planName}>{plan_label}</div>
          {plan_price && (
            <div className={styles.planPrice}>{plan_price} · per store</div>
          )}
          {!plan_price && trial && (
            <div className={styles.planPrice}>Free · trial</div>
          )}

          <div className={styles.planMeta}>
            {trial && data.trial_status === "active" && (
              <>
                Your free trial ends in{" "}
                <strong>
                  {data.trial_days_left} day
                  {data.trial_days_left === 1 ? "" : "s"}
                </strong>
                . Pick a plan now to keep full access without interruption.
              </>
            )}
            {trial && data.trial_status === "expiring_soon" && (
              <>
                Your free trial ends very soon —{" "}
                <strong>
                  {data.trial_days_left} day
                  {data.trial_days_left === 1 ? "" : "s"}
                </strong>{" "}
                left. Choose a plan to avoid interruption.
              </>
            )}
            {trial && data.trial_status === "grace" && (
              <>
                Your trial has ended. You're in a short grace period —
                upgrade now to avoid losing access.
              </>
            )}
            {trial && data.trial_status === "expired" && (
              <>Your trial has ended.</>
            )}
            {inactive && (
              <>Your subscription is inactive. Choose a plan to restore access.</>
            )}
            {has_paid_plan && (
              <>
                Subscription is active. Manage payment method, invoices, or
                cancellation in the billing portal.
              </>
            )}
          </div>

          <div className={styles.planActions}>
            {has_paid_plan ? (
              <>
                <Button
                  busy={busy === "portal"}
                  disabled={busy === "portal"}
                  onClick={() => handlePortal("portal")}
                >
                  {busy === "portal" ? "Opening…" : "Manage Billing"}
                </Button>
                <Link to="/subscribe" style={{ textDecoration: "none" }}>
                  <Button tone="secondary">Change Plan</Button>
                </Link>
              </>
            ) : (
              <Link to="/subscribe" style={{ textDecoration: "none" }}>
                <Button>Choose a Plan</Button>
              </Link>
            )}
          </div>
          {has_paid_plan && (
            <button
              type="button"
              className={styles.cancelLink}
              onClick={() => setShowCancel(true)}
            >
              Cancel subscription
            </button>
          )}
        </div>

        <Card>
          <h3 className={styles.cardH3}>Account</h3>
          <InfoRow label="Store" value={store.name || "—"} />
          <InfoRow label="Billing Email" value={store.email || "—"} />
          <InfoRow
            label="Customer ID"
            value={store.stripe_customer_id || "—"}
            mono
          />
          <InfoRow
            label="Subscription ID"
            value={store.stripe_subscription_id || "—"}
            mono
          />
          <InfoRow label="Active Add-ons" value={String(data.active_addon_count)} />
        </Card>
      </div>

      <h2 className={styles.addonsHeading}>Add-ons</h2>

      {!has_paid_plan && (
        <div className={styles.bannerWarn}>
          Add-ons require an active <strong>Basic</strong> or{" "}
          <strong>Pro</strong> subscription.{" "}
          <Link to="/subscribe" style={{ color: "inherit", textDecoration: "underline" }}>
            Choose a plan
          </Link>{" "}
          to unlock them.
        </div>
      )}

      <div className={styles.addonGrid}>
        {data.addons.map((a) => (
          <Card key={a.key} style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <div className={styles.addonRow}>
              <div>
                <div className={styles.addonName}>{a.name}</div>
                <div className={styles.muted}>{a.tagline}</div>
              </div>
              <div className={styles.addonRowEnd}>
                {a.status === "coming_soon" && (
                  <Pill tone="warning">Coming Soon</Pill>
                )}
                <span className={styles.addonPrice}>{a.price_label}</span>
              </div>
            </div>
            <p className={styles.addonDesc}>{a.description}</p>
            <div className={styles.addonFoot}>
              <span className={styles.muted}>
                {a.is_active ? <Pill tone="accent">Active</Pill> : "Not added"}
              </span>
              <button
                type="button"
                className={styles.btnLinkLive}
                disabled={
                  busy === `addon:${a.key}` ||
                  (!has_paid_plan && a.status !== "coming_soon")
                }
                onClick={() => handleToggle(a)}
              >
                {a.status === "coming_soon"
                  ? "Notify Me"
                  : a.is_active
                    ? "Remove"
                    : "Add"}
              </button>
            </div>
          </Card>
        ))}
        {data.addons.length === 0 && (
          <p className={styles.muted}>No add-ons available right now.</p>
        )}
      </div>

      {showCancel && has_paid_plan && (
        <div className={styles.modalBackdrop} onClick={() => setShowCancel(false)}>
          <div className={styles.modalCard} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ margin: 0 }}>Before you cancel</h3>
            <p>
              You're about to cancel your <strong>{plan_label}</strong>{" "}
              subscription. We hold your data so you can come back without
              losing a thing.
            </p>
            <div className={styles.infoBox}>
              <strong>Your data is safe for 6 months.</strong>
              <br />
              Reports, transfers, batches, employees, and settings stay
              exactly where you left them. Resubscribe anytime within 6
              months and you're right back in. After 6 months, all of this
              store's data is permanently deleted.
            </div>
            <p className={styles.muted}>
              Clicking continue takes you to Stripe to confirm the cancellation.
            </p>
            <div className={styles.modalActions}>
              <Button tone="secondary" onClick={() => setShowCancel(false)}>
                Keep Subscription
              </Button>
              <Button
                tone="danger"
                busy={busy === "cancel"}
                disabled={busy === "cancel"}
                onClick={() => handlePortal("cancel")}
              >
                {busy === "cancel" ? "Opening…" : "Continue to Cancel"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </PageShell>
  );
}

function InfoRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className={styles.infoRow}>
      <span className={styles.muted}>{label}</span>
      <span className={mono ? styles.monoSm : undefined}>
        {value}
      </span>
    </div>
  );
}
