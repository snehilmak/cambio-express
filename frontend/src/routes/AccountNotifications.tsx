import { useEffect, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  subscribePush,
  unsubscribePush,
  updateNotifications,
  useNotifications,
  usePushStatus,
  type NotificationsUpdateBody,
} from "../api/account";
import { ApiError } from "../lib/api";
import {
  getPushPermission,
  hasLocalSubscription,
  pushSupported,
  subscribeBrowser,
  unsubscribeBrowser,
} from "../lib/push";
import {
  Breadcrumbs,
  Alert, Button, Card, ErrorState, Loading, PageHeader, PageShell, Section,
  Table, tdStyle, thStyle, tokens, useToast,
} from "../components/ui";
import styles from "./AccountNotifications.module.css";

// /app/account/notifications — per-user boolean toggles.
//
// Trial-reminder toggle is interactive only when the user's role
// + store make it relevant (admin/owner of an actively-trialing
// store). For everyone else (employees, paid stores, superadmin)
// it renders disabled with an inline "not applicable" note —
// matches the legacy Jinja behavior so users see the full
// preference surface.

export default function AccountNotifications() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError, error, refetch } = useNotifications();

  const [draft, setDraft] = useState<NotificationsUpdateBody>({});
  const [busy, setBusy]   = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const toast = useToast();

  useEffect(() => {
    if (!data) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate local editable draft from server-fetched notifications once GET resolves
    setDraft({
      notify_trial_reminders:        data.notify_trial_reminders,
      notify_announcement_email:     data.notify_announcement_email,
      notify_locked_day_digest:      data.notify_locked_day_digest,
      notify_daily_summary:          data.notify_daily_summary,
      notify_trial_reminders_push:   data.notify_trial_reminders_push,
      notify_announcement_push:      data.notify_announcement_push,
      notify_locked_day_digest_push: data.notify_locked_day_digest_push,
      notify_daily_summary_push:     data.notify_daily_summary_push,
    });
  }, [data]);

  function set<K extends keyof NotificationsUpdateBody>(
    key: K, value: NotificationsUpdateBody[K],
  ) {
    setDraft((d) => ({ ...d, [key]: value }));
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!data) return;
    setBusy(true);
    setServerError(null);
    try {
      await updateNotifications(draft);
      toast({ message: "Notification preferences saved.", tone: "success" });
      queryClient.invalidateQueries({ queryKey: ["account", "notifications"] });
    } catch (err) {
      setServerError(
        err instanceof ApiError ? err.message : "Network error. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (isLoading) {
    return (
      <PageShell maxWidth="60rem">
        <PageHeader title="Notifications" />
        <Loading />
      </PageShell>
    );
  }
  if (isError || !data) {
    return (
      <PageShell maxWidth="60rem">
        <PageHeader title="Notifications" />
        <ErrorState
          message={`Couldn't load preferences.${error instanceof Error ? ` ${error.message}` : ""}`}
          onRetry={() => { void refetch(); }}
        />
      </PageShell>
    );
  }

  const trialApplies = data.trial_toggle_applies;
  const trialNotApplicableNote = data.role === "admin" || data.role === "owner"
    ? "Not applicable for your account right now — you're on a paid plan (or no active trial)."
    : "Not applicable for your account right now — you're on a role that doesn't own a trial.";
  const digestApplies = data.locked_day_digest_applies;
  const summaryApplies = data.daily_summary_applies;

  return (
    <PageShell maxWidth="60rem">

      <Breadcrumbs crumbs={[{ label: "Account", to: "/settings" }, { label: "Notifications" }]} />

      <PageHeader title="Notifications" subtitle="Control which email and push alerts you receive." />

      <div className={styles.grid}>
        <Section title="Your preferences">
          <Card>
            {serverError && <Alert tone="error">{serverError}</Alert>}

            <form onSubmit={onSubmit} autoComplete="off">
              <div className={styles.kindHeader}>
                <span />
                <span className={styles.channelLabel}>Email</span>
                <span className={styles.channelLabel}>Push</span>
              </div>

              <PrefKindRow
                id="trial"
                title="Trial-ending reminder"
                disabled={busy || !trialApplies}
                emailChecked={draft.notify_trial_reminders ?? false}
                emailOnChange={(v) => set("notify_trial_reminders", v)}
                pushChecked={draft.notify_trial_reminders_push ?? false}
                pushOnChange={(v) => set("notify_trial_reminders_push", v)}
              >
                One reminder during the last 3 days of my trial so I
                can subscribe before the books lock. Turned off means
                you'll only see the in-app banner.
                {!trialApplies && (
                  <>
                    <br />
                    <em className={styles.notApplicable}>
                      {trialNotApplicableNote}
                    </em>
                  </>
                )}
              </PrefKindRow>

              <PrefKindRow
                id="announcement"
                title="Platform announcements"
                disabled={busy}
                emailChecked={draft.notify_announcement_email ?? false}
                emailOnChange={(v) => set("notify_announcement_email", v)}
                pushChecked={draft.notify_announcement_push ?? false}
                pushOnChange={(v) => set("notify_announcement_push", v)}
              >
                New features, outages, policy changes. Email is off
                by default; push is on for users who enabled the
                browser-notifications channel below. You'll still see
                every announcement as a banner when you sign in.
              </PrefKindRow>

              <PrefKindRow
                id="digest"
                title="Daily book close-out digest"
                disabled={busy || !digestApplies}
                emailChecked={draft.notify_locked_day_digest ?? false}
                emailOnChange={(v) => set("notify_locked_day_digest", v)}
                pushChecked={draft.notify_locked_day_digest_push ?? false}
                pushOnChange={(v) => set("notify_locked_day_digest_push", v)}
              >
                Notification when a daily book is locked, with the
                receipts / disbursements / over-short totals so you can
                cross-check against the bank. Sent to admins + linked
                owners only.
                {!digestApplies && (
                  <>
                    <br />
                    <em className={styles.notApplicable}>
                      Not applicable — your role doesn't receive this digest.
                    </em>
                  </>
                )}
              </PrefKindRow>

              <PrefKindRow
                id="summary"
                title="Daily summary"
                disabled={busy || !summaryApplies}
                emailChecked={draft.notify_daily_summary ?? false}
                emailOnChange={(v) => set("notify_daily_summary", v)}
                pushChecked={draft.notify_daily_summary_push ?? false}
                pushOnChange={(v) => set("notify_daily_summary_push", v)}
              >
                Nightly per-store summary of the prior day's transfer
                count, send volume, receipts, disbursements, and
                over-short — so you see the close-out numbers by
                morning without logging in. Quiet days don't generate
                a notification. Sent to admins + linked owners only.
                {!summaryApplies && (
                  <>
                    <br />
                    <em className={styles.notApplicable}>
                      Not applicable — your role doesn't receive this digest.
                    </em>
                  </>
                )}
              </PrefKindRow>

              <div style={{ marginTop: "1.25rem" }}>
                <Button type="submit" busy={busy} disabled={busy}>
                  {busy ? "Saving…" : "Save preferences"}
                </Button>
              </div>
            </form>
          </Card>
        </Section>

        <Section title="Browser notifications">
          <BrowserPushCard />
        </Section>

        <Section title="What DineroBook sends you">
          <Card>
            <p className={styles.lead}>
              We send as little as possible. Here's the complete list —
              anything user-controllable has a toggle on the left; the
              rest is either essential (password reset) or not yet
              implemented.
            </p>
            <Table>
              <thead>
                <tr>
                  {["Channel", "What", "Control"].map((h) => (
                    <th key={h} style={thStyle}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <Row
                  channel="Email" what="Password reset link"
                  control="Always on — you initiate it."
                  muted
                />
                <Row
                  channel="Email" what="Trial-ending reminder (last 3 days)"
                  control="Toggle above."
                />
                <Row
                  channel="Email"
                  what="Platform announcements (when superadmin broadcasts)"
                  control="Toggle above."
                />
                <Row
                  channel="Email"
                  what="Daily book close-out digest (admins + linked owners)"
                  control="Toggle above."
                />
                <Row
                  channel="Email"
                  what="Daily summary (nightly per-store, admins + linked owners)"
                  control="Toggle above."
                />
                <Row
                  channel="Browser push"
                  what="Platform announcements + future delivery alerts"
                  control={'"Browser notifications" section above.'}
                />
                <Row
                  channel="In-app banner"
                  what="Announcements, trial status, retention notices"
                  control="Not dismissible per-user (yet)."
                  muted
                />
              </tbody>
            </Table>
            <p className={styles.fine}>
              We don't ship controls for imaginary notifications —
              every toggle on this page has a real sender behind it.
              New senders land here alongside their toggle.
            </p>
          </Card>
        </Section>
      </div>
    </PageShell>
  );
}


function PrefKindRow({
  id, title, disabled,
  emailChecked, emailOnChange,
  pushChecked,  pushOnChange,
  children,
}: {
  id:            string;
  title:         string;
  disabled:      boolean;
  emailChecked:  boolean;
  emailOnChange: (v: boolean) => void;
  pushChecked:   boolean;
  pushOnChange:  (v: boolean) => void;
  children:      React.ReactNode;
}) {
  const emailId = `${id}-email`;
  const pushId  = `${id}-push`;
  return (
    <div className={styles.kindRow}>
      <div className={styles.prefBody}>
        <div className={styles.prefTitleRow}>
          <span className={styles.prefTitle}>{title}</span>
          <ChannelStatusBadge
            disabled={disabled}
            emailOn={emailChecked}
            pushOn={pushChecked}
          />
        </div>
        <div className={styles.prefDesc}>{children}</div>
      </div>
      <label
        htmlFor={emailId}
        className={styles.channelCell}
        aria-label={`Email — ${title}`}
      >
        <input
          id={emailId} type="checkbox"
          checked={emailChecked}
          disabled={disabled}
          onChange={(e) => emailOnChange(e.target.checked)}
          className={styles.checkbox}
        />
      </label>
      <label
        htmlFor={pushId}
        className={styles.channelCell}
        aria-label={`Push — ${title}`}
      >
        <input
          id={pushId} type="checkbox"
          checked={pushChecked}
          disabled={disabled}
          onChange={(e) => pushOnChange(e.target.checked)}
          className={styles.checkbox}
        />
      </label>
    </div>
  );
}


function Row({
  channel, what, control, muted,
}: {
  channel: string; what: string; control: string; muted?: boolean;
}) {
  const ctrlStyle: React.CSSProperties = muted
    ? { ...tdStyle, color: tokens.textMuted }
    : tdStyle;
  return (
    <tr>
      <td style={tdStyle}>{channel}</td>
      <td style={tdStyle}>{what}</td>
      <td style={ctrlStyle}>{control}</td>
    </tr>
  );
}


function BrowserPushCard() {
  const queryClient = useQueryClient();
  const { data: status, isLoading } = usePushStatus();
  const [localSubscribed, setLocalSubscribed] = useState<boolean>(false);
  const [permission, setPermission] = useState(getPushPermission());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();
  const supported = pushSupported();

  // Sync local "is this browser subscribed?" once on mount + after
  // every action.  The server cross-device count comes from
  // ``usePushStatus``; this hook is purely about THIS browser.
  useEffect(() => {
    void (async () => {
      const has = await hasLocalSubscription();
      setLocalSubscribed(has);
    })();
  }, []);

  if (!supported) {
    return (
      <Card>
        <p className={styles.pushUnsupported}>
          Your browser doesn't support push notifications.  Try a
          modern Chrome / Firefox / Edge / Safari 16.4+ build.
        </p>
      </Card>
    );
  }

  if (isLoading) {
    return <Card><Loading /></Card>;
  }

  if (!status?.enabled) {
    return (
      <Card>
        <p className={styles.pushUnsupported}>
          Push notifications aren't configured on this server yet.
          Once the operator sets the VAPID keys, this section will
          flip to an "Enable" button.
        </p>
      </Card>
    );
  }

  async function onEnable() {
    if (!status?.public_key) return;
    setBusy(true); setError(null);
    try {
      const env = await subscribeBrowser(status.public_key);
      await subscribePush({
        endpoint:   env.endpoint,
        p256dh:     env.p256dh,
        auth:       env.auth,
        user_agent: env.userAgent,
      });
      setLocalSubscribed(true);
      setPermission(getPushPermission());
      toast({
        message: "Browser notifications enabled on this device.",
        tone: "success",
      });
      queryClient.invalidateQueries({ queryKey: ["account", "push-status"] });
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message
        : err instanceof Error  ? err.message
        : "Couldn't enable browser notifications.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function onDisable() {
    setBusy(true); setError(null);
    try {
      const endpoint = await unsubscribeBrowser();
      if (endpoint) {
        await unsubscribePush({ endpoint });
      }
      setLocalSubscribed(false);
      toast({
        message: "Browser notifications disabled on this device.",
        tone: "success",
      });
      queryClient.invalidateQueries({ queryKey: ["account", "push-status"] });
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message
        : err instanceof Error  ? err.message
        : "Couldn't disable browser notifications.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <div className={styles.pushRow}>
        <div className={styles.pushStatus}>
          <span
            className={`${styles.pushDot} ${localSubscribed ? styles.pushDotOn : styles.pushDotOff}`}
            aria-hidden="true"
          />
          {localSubscribed
            ? "Browser notifications are enabled on this device."
            : "Browser notifications are off on this device."}
          {status.device_count > 0 && (
            <span className={styles.pushDeviceHint}>
              {" "}({status.device_count} {status.device_count === 1 ? "device" : "devices"} on file)
            </span>
          )}
        </div>

        {error && <Alert tone="error">{error}</Alert>}
        {permission === "denied" && (
          <Alert tone="info">
            Notifications are blocked for this site.  Allow them in
            your browser's site-settings, then click Enable.
          </Alert>
        )}

        <div className={styles.pushActions}>
          {!localSubscribed && (
            <Button
              type="button"
              busy={busy}
              disabled={busy || permission === "denied"}
              onClick={() => { void onEnable(); }}
            >
              {busy ? "Enabling…" : "Enable browser notifications"}
            </Button>
          )}
          {localSubscribed && (
            <Button
              type="button" tone="secondary"
              busy={busy} disabled={busy}
              onClick={() => { void onDisable(); }}
            >
              {busy ? "Disabling…" : "Disable on this device"}
            </Button>
          )}
        </div>

        <p className={styles.pushDeviceHint}>
          You'll get a small system notification for platform
          announcements (and future delivery / payroll alerts).
          Disabling here only affects this device — you can re-
          enable on a different browser without losing the others.
        </p>
      </div>
    </Card>
  );
}


/** Inline pill on each notification kind summarizing which
 *  channels are active.  Helps users see "I'll get this as
 *  push only" without parsing two adjacent checkboxes.
 *
 *  Suppressed when the row is disabled (inapplicable kind) —
 *  showing "Both off" on an irrelevant row reads as a problem
 *  to fix, but it's actually correct + intentional. */
function ChannelStatusBadge({
  disabled, emailOn, pushOn,
}: { disabled: boolean; emailOn: boolean; pushOn: boolean }) {
  if (disabled) return null;
  const both = emailOn && pushOn;
  const none = !emailOn && !pushOn;
  let label: string;
  let kind: "on" | "off" | "mixed";
  if (both)        { label = "Email + push"; kind = "on"; }
  else if (none)   { label = "Both off";     kind = "off"; }
  else if (emailOn){ label = "Email only";   kind = "mixed"; }
  else             { label = "Push only";    kind = "mixed"; }
  return (
    <span
      className={`${styles.statusBadge} ${
        kind === "on"   ? styles.statusBadgeOn
      : kind === "off"  ? styles.statusBadgeOff
                        : styles.statusBadgeMixed
      }`}
    >
      {label}
    </span>
  );
}
