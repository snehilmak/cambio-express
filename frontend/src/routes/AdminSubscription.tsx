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
import { ErrorState, Loading } from "../components/ui";

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
      <main style={pageStyle}>
        <h1 style={titleStyle}>Billing &amp; Subscription</h1>
        <ErrorState message={error} onRetry={() => { void load(); }} />
      </main>
    );
  }
  if (!data) {
    return (
      <main style={pageStyle}>
        <h1 style={titleStyle}>Billing &amp; Subscription</h1>
        <Loading />
      </main>
    );
  }

  const { store, has_paid_plan, plan_label, plan_price } = data;
  const inactive = store.plan === "inactive";
  const trial = store.plan === "trial";

  return (
    <main style={pageStyle}>
      <h1 style={titleStyle}>Billing &amp; Subscription</h1>

      {error && <ErrorState message={error} />}

      {inactive && data.retention_days_left != null && (
        <div style={bannerError}>
          Your subscription is canceled. Your store data is safe for{" "}
          <strong>
            {data.retention_days_left} more day
            {data.retention_days_left === 1 ? "" : "s"}
          </strong>
          . Resubscribe before then to pick up where you left off.
          <Link to="/subscribe" style={{ marginLeft: "1rem", color: "inherit" }}>
            Resubscribe
          </Link>
        </div>
      )}

      <div style={twoColGrid}>
        <div style={planHero}>
          <div style={planEyebrow}>Current Plan</div>
          <div style={planName}>{plan_label}</div>
          {plan_price && (
            <div style={planPrice}>{plan_price} · per store</div>
          )}
          {!plan_price && trial && (
            <div style={planPrice}>Free · trial</div>
          )}

          <div style={planMeta}>
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

          <div style={planActions}>
            {has_paid_plan ? (
              <>
                <button
                  type="button"
                  style={btnPrimaryDark}
                  disabled={busy === "portal"}
                  onClick={() => handlePortal("portal")}
                >
                  {busy === "portal" ? "Opening…" : "Manage Billing"}
                </button>
                <Link to="/subscribe" style={btnGhostDark}>
                  Change Plan
                </Link>
              </>
            ) : (
              <Link to="/subscribe" style={btnPrimaryDark}>
                Choose a Plan
              </Link>
            )}
          </div>
          {has_paid_plan && (
            <button
              type="button"
              style={cancelLink}
              onClick={() => setShowCancel(true)}
            >
              Cancel subscription
            </button>
          )}
        </div>

        <div style={cardStyle}>
          <h3 style={{ margin: 0, marginBottom: "0.75rem", fontWeight: 600 }}>
            Account
          </h3>
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
        </div>
      </div>

      <h2 style={{ fontSize: "1.1rem", margin: "1.5rem 0 0.75rem" }}>Add-ons</h2>

      {!has_paid_plan && (
        <div style={bannerWarn}>
          Add-ons require an active <strong>Basic</strong> or{" "}
          <strong>Pro</strong> subscription.{" "}
          <Link to="/subscribe" style={{ color: "inherit", textDecoration: "underline" }}>
            Choose a plan
          </Link>{" "}
          to unlock them.
        </div>
      )}

      <div style={addonGrid}>
        {data.addons.map((a) => (
          <div key={a.key} style={addonCard}>
            <div style={addonRow}>
              <div>
                <div style={addonName}>{a.name}</div>
                <div style={mutedStyle}>{a.tagline}</div>
              </div>
              <div style={{ textAlign: "right", display: "flex", flexDirection: "column", gap: "0.25rem", alignItems: "flex-end" }}>
                {a.status === "coming_soon" && (
                  <span style={comingPill}>Coming Soon</span>
                )}
                <span style={addonPrice}>{a.price_label}</span>
              </div>
            </div>
            <p style={addonDesc}>{a.description}</p>
            <div style={addonFoot}>
              <span style={mutedStyle}>
                {a.is_active ? (
                  <span style={badgeGreen}>Active</span>
                ) : (
                  "Not added"
                )}
              </span>
              <button
                type="button"
                disabled={
                  busy === `addon:${a.key}` ||
                  (!has_paid_plan && a.status !== "coming_soon")
                }
                onClick={() => handleToggle(a)}
                style={a.status === "coming_soon" || a.is_active ? btnLinkLive : btnLinkLive}
              >
                {a.status === "coming_soon"
                  ? "Notify Me"
                  : a.is_active
                    ? "Remove"
                    : "Add"}
              </button>
            </div>
          </div>
        ))}
        {data.addons.length === 0 && (
          <p style={mutedStyle}>No add-ons available right now.</p>
        )}
      </div>

      {showCancel && has_paid_plan && (
        <div style={modalBackdrop} onClick={() => setShowCancel(false)}>
          <div style={modalCard} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ margin: 0 }}>Before you cancel</h3>
            <p>
              You're about to cancel your <strong>{plan_label}</strong>{" "}
              subscription. We hold your data so you can come back without
              losing a thing.
            </p>
            <div style={infoBox}>
              <strong>Your data is safe for 6 months.</strong>
              <br />
              Reports, transfers, batches, employees, and settings stay
              exactly where you left them. Resubscribe anytime within 6
              months and you're right back in. After 6 months, all of this
              store's data is permanently deleted.
            </div>
            <p style={mutedStyle}>
              Clicking continue takes you to Stripe to confirm the cancellation.
            </p>
            <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
              <button
                type="button"
                style={btnOutline}
                onClick={() => setShowCancel(false)}
              >
                Keep Subscription
              </button>
              <button
                type="button"
                style={btnDanger}
                disabled={busy === "cancel"}
                onClick={() => handlePortal("cancel")}
              >
                {busy === "cancel" ? "Opening…" : "Continue to Cancel"}
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

function InfoRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "0.4rem 0", borderBottom: "1px solid var(--db-border-subtle, #1f1f1f)" }}>
      <span style={mutedStyle}>{label}</span>
      <span style={mono ? { ...moneyValue, fontSize: "0.85rem" } : undefined}>
        {value}
      </span>
    </div>
  );
}

const pageStyle: React.CSSProperties = {
  flex: 1,
  padding: "2rem 1.5rem",
  maxWidth: "70rem",
  margin: "0 auto",
  width: "100%",
  boxSizing: "border-box",
};
const titleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "clamp(1.5rem, 3.5vw, 2rem)",
  fontWeight: 600,
  marginTop: 0,
};
const twoColGrid: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
  gap: "1.25rem",
  marginBottom: "1.5rem",
};
const planHero: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-accent, #3fff00)",
  borderRadius: "0.75rem",
  padding: "1.5rem",
  position: "relative",
};
const planEyebrow: React.CSSProperties = {
  fontSize: "0.75rem",
  letterSpacing: "0.1em",
  textTransform: "uppercase",
  color: "var(--db-accent, #3fff00)",
  fontWeight: 600,
};
const planName: React.CSSProperties = {
  fontSize: "1.75rem",
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  marginTop: "0.25rem",
};
const planPrice: React.CSSProperties = {
  fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
  fontSize: "0.85rem",
  color: "var(--db-text-muted, #a3a3a3)",
};
const planMeta: React.CSSProperties = {
  marginTop: "1rem",
  fontSize: "0.9rem",
  color: "var(--db-text-muted, #a3a3a3)",
};
const planActions: React.CSSProperties = {
  marginTop: "1.25rem",
  display: "flex",
  gap: "0.5rem",
  flexWrap: "wrap",
};
const cardStyle: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem",
  padding: "1.25rem",
};
const btnPrimaryDark: React.CSSProperties = {
  background: "var(--db-accent, #3fff00)",
  color: "#000",
  padding: "0.55rem 1rem",
  borderRadius: "0.5rem",
  fontSize: "0.9rem",
  fontWeight: 600,
  textDecoration: "none",
  border: "none",
  cursor: "pointer",
};
const btnGhostDark: React.CSSProperties = {
  background: "transparent",
  color: "inherit",
  padding: "0.55rem 1rem",
  borderRadius: "0.5rem",
  fontSize: "0.9rem",
  fontWeight: 500,
  border: "1px solid var(--db-border, #262626)",
  textDecoration: "none",
  cursor: "pointer",
};
const cancelLink: React.CSSProperties = {
  background: "transparent",
  color: "var(--db-text-muted, #a3a3a3)",
  border: "none",
  padding: "0.5rem 0",
  marginTop: "0.5rem",
  fontSize: "0.85rem",
  cursor: "pointer",
  textDecoration: "underline",
  display: "block",
};
const mutedStyle: React.CSSProperties = {
  color: "var(--db-text-muted, #a3a3a3)",
  fontSize: "0.85rem",
};
const moneyValue: React.CSSProperties = {
  fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
};
const bannerError: React.CSSProperties = {
  color: "var(--db-negative, #ff3b30)",
  background: "rgba(255,59,48,0.08)",
  border: "1px solid rgba(255,59,48,0.4)",
  padding: "0.75rem 1rem",
  borderRadius: "0.5rem",
  marginBottom: "1.25rem",
};
const bannerWarn: React.CSSProperties = {
  background: "rgba(255,204,0,0.08)",
  border: "1px solid rgba(255,204,0,0.4)",
  color: "var(--db-warning, #ffcc00)",
  padding: "0.75rem 1rem",
  borderRadius: "0.5rem",
  marginBottom: "1rem",
};
const addonGrid: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
  gap: "1rem",
};
const addonCard: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem",
  padding: "1.25rem",
  display: "flex",
  flexDirection: "column",
  gap: "0.75rem",
};
const addonRow: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "flex-start",
  gap: "0.75rem",
};
const addonName: React.CSSProperties = {
  fontSize: "1.05rem",
  fontWeight: 600,
};
const addonPrice: React.CSSProperties = {
  fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
  fontSize: "0.85rem",
  color: "var(--db-text-muted, #a3a3a3)",
};
const addonDesc: React.CSSProperties = {
  margin: 0,
  fontSize: "0.9rem",
  color: "var(--db-text-muted, #a3a3a3)",
};
const addonFoot: React.CSSProperties = {
  marginTop: "auto",
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "0.5rem",
  paddingTop: "0.5rem",
};
const btnLinkLive: React.CSSProperties = {
  background: "transparent",
  border: "1px solid var(--db-accent, #3fff00)",
  color: "var(--db-accent, #3fff00)",
  padding: "0.4rem 0.85rem",
  borderRadius: "0.5rem",
  fontSize: "0.85rem",
  fontWeight: 600,
  cursor: "pointer",
};
const badgeGreen: React.CSSProperties = {
  background: "rgba(63,255,0,0.15)",
  color: "var(--db-accent, #3fff00)",
  padding: "0.15rem 0.55rem",
  borderRadius: "999px",
  fontSize: "0.75rem",
  fontWeight: 600,
};
const comingPill: React.CSSProperties = {
  background: "rgba(255,204,0,0.15)",
  color: "var(--db-warning, #ffcc00)",
  padding: "0.15rem 0.55rem",
  borderRadius: "999px",
  fontSize: "0.7rem",
  fontWeight: 600,
};
const modalBackdrop: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(0,0,0,0.5)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 100,
};
const modalCard: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem",
  padding: "1.5rem",
  maxWidth: "32rem",
  width: "90%",
  display: "flex",
  flexDirection: "column",
  gap: "0.75rem",
};
const infoBox: React.CSSProperties = {
  background: "rgba(63,255,0,0.05)",
  border: "1px solid rgba(63,255,0,0.2)",
  padding: "0.75rem 1rem",
  borderRadius: "0.5rem",
};
const btnOutline: React.CSSProperties = {
  background: "transparent",
  border: "1px solid var(--db-border, #262626)",
  color: "inherit",
  padding: "0.5rem 1rem",
  borderRadius: "0.5rem",
  cursor: "pointer",
};
const btnDanger: React.CSSProperties = {
  background: "var(--db-negative, #ff3b30)",
  color: "#fff",
  padding: "0.5rem 1rem",
  borderRadius: "0.5rem",
  border: "none",
  fontWeight: 600,
  cursor: "pointer",
};
