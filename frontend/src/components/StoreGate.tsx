import { Button, ButtonLink } from "./ui";
import styles from "./StoreGate.module.css";

// Full-screen takeover shown when a store's users are gated out of the
// app (PR C). Two reasons:
//
//   "subscription" — trial/grace fully lapsed or plan inactive. Self-
//                    serve: a "Re-subscribe" CTA into Stripe Checkout.
//   "frozen"       — a superadmin suspended the store. NOT self-serve —
//                    re-subscribing wouldn't lift it — so we show a
//                    "contact support" message and only Log out.
//
// Rendered by AppShell in place of the normal chrome, so the sidebar /
// topbar / page content never mount for a gated user.

export interface StoreGateProps {
  reason: "frozen" | "subscription";
  storeName: string;
  onSignOut: () => void;
}

export default function StoreGate({ reason, storeName, onSignOut }: StoreGateProps) {
  const frozen = reason === "frozen";
  return (
    <div className={styles.wrap}>
      <div className={styles.card}>
        <div className={styles.mark} aria-hidden="true">
          {frozen ? (
            // lock
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="2" strokeLinecap="round"
              strokeLinejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2" />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
          ) : (
            // credit card
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="2" strokeLinecap="round"
              strokeLinejoin="round">
              <rect x="2" y="5" width="20" height="14" rx="2" />
              <path d="M2 10h20" />
            </svg>
          )}
        </div>

        <h1 className={styles.title}>
          {frozen ? "Account suspended" : "Your subscription has ended"}
        </h1>

        <p className={styles.body}>
          {frozen ? (
            <>
              {storeName ? <strong>{storeName}</strong> : "This store"} has been
              suspended by the DineroBook team. Please contact support to
              restore access. Your data is safe.
            </>
          ) : (
            <>
              Re-subscribe to regain access
              {storeName ? <> to <strong>{storeName}</strong></> : null}. Your
              books and history are safe — nothing is deleted while you decide.
            </>
          )}
        </p>

        <div className={styles.actions}>
          {!frozen && (
            <ButtonLink to="/subscribe" tone="primary">
              Re-subscribe
            </ButtonLink>
          )}
          <Button tone="secondary" onClick={onSignOut}>
            Log out
          </Button>
        </div>
      </div>
    </div>
  );
}
