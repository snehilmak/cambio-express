import { useState } from "react";

import {
  useReferralCode,
  type ReferralRedemptionRow,
} from "../api/admin";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  Breadcrumbs,
  ButtonLink, Card, Empty, ErrorState, KpiCard, KpiGrid, Loading,
  PageHeader, PageShell, Pill, space, Table, tdStyle, thStyle,
} from "../components/ui";
import styles from "./AdminReferrals.module.css";

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
        <Card>
          <h2 className={styles.cardTitle}>Unlock referrals on a paid plan</h2>
          <p className={styles.lead}>
            Refer another store, both of you get credit. Activate Basic
            or Pro and your referral code mints automatically.
          </p>
          <ButtonLink to="/subscribe" tone="primary" style={{ marginTop: space.lg }}>
            See plans →
          </ButtonLink>
        </Card>
      </PageShell>
    );
  }

  return (
    <PageShell maxWidth="60rem">

      <Breadcrumbs crumbs={[{ label: "Account", to: "/settings" }, { label: "Referrals" }]} />

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

          <KpiGrid minWidth="180px">
            <KpiCard
              label="Successful referrals"
              value={String(data.redeemed_count)}
              sub="converted to paid"
              tone="warning"
            />
            <KpiCard
              label="Credits earned"
              value={`$${(data.credits_earned_cents / 100).toFixed(2)}`}
              sub="applied to your Stripe balance"
              tone="neon"
            />
            <KpiCard
              label="Status"
              value={data.is_active ? "Active" : "Disabled"}
              sub={data.is_active
                ? "earning credits"
                : "contact support to re-enable"}
              tone="primary"
            />
          </KpiGrid>

          <section className={styles.howBox}>
            <strong>How it works.</strong>{" "}
            Give the code (or the link) to anyone signing up.
            Their ${(data.reward_referee_cents / 100).toFixed(0)} posts
            the moment they start a paid plan; your $
            {(data.reward_self_cents / 100).toFixed(0)} posts the same
            moment. Credits apply to your next invoice via Stripe's
            customer-balance system — no coupon codes to redeem, no
            accounting from your side.
          </section>

          <Card>
            <div className={styles.cardHeader}>
              <span>History</span>
              <span className={styles.cardHeaderCount}>
                {data.redemptions.length}{" "}
                {data.redemptions.length === 1 ? "redemption" : "redemptions"}
              </span>
            </div>
            <HistoryTable rows={data.redemptions} />
          </Card>
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
    <section className={styles.hero}>
      <div className={styles.heroLabel}>Your referral code</div>
      <div className={styles.heroCode}>{code}</div>
      <p className={styles.heroMeta}>
        Share this with friends who run a money-service business.
        When they sign up and subscribe,{" "}
        <strong>they get ${(rewardRefereeCents / 100).toFixed(0)} off</strong>{" "}
        their first paid month and{" "}
        <strong>you get ${(rewardSelfCents / 100).toFixed(0)} off</strong>{" "}
        yours — applied automatically to your next invoice as a credit.
      </p>
      <div className={styles.shareRow}>
        <input
          readOnly
          value={shareUrl}
          className={styles.shareInput}
          onFocus={(e) => e.currentTarget.select()}
        />
        <button
          type="button"
          className={styles.btnGold}
          onClick={() => copy(code, () => {
            setCodeFlash(true);
            setTimeout(() => setCodeFlash(false), 1400);
          })}
        >
          {codeFlash ? "Copied!" : "Copy code"}
        </button>
        <button
          type="button"
          className={styles.btnGold}
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


function HistoryTable({ rows }: { rows: ReferralRedemptionRow[] }) {
  if (rows.length === 0) {
    return (
      <p className={styles.emptyTable}>
        No referrals yet. Share your code above — your first credit
        posts the moment someone subscribes.
      </p>
    );
  }
  return (
    <Table>
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
            <td style={tdStyle}>
              <span className={styles.monoMuted}>
                {r.redeemed_at ? r.redeemed_at.slice(0, 10) : "—"}
              </span>
            </td>
            <td style={tdStyle}>#{r.referee_store_id}</td>
            <td style={tdStyle}>
              {r.self_credit_applied ? (
                <>
                  <Pill tone="accent">Credited</Pill>
                  {r.stripe_self_txn_id && (
                    <span className={`${styles.monoMuted} ${styles.txnId}`}>
                      {r.stripe_self_txn_id}
                    </span>
                  )}
                </>
              ) : (
                <Pill tone="warning">Pending</Pill>
              )}
            </td>
            <td style={tdStyle}>
              {r.referee_credit_applied
                ? <Pill tone="accent">Credited</Pill>
                : <Pill tone="warning">Pending</Pill>}
            </td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
