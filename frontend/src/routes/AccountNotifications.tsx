import { useEffect, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  updateNotifications, useNotifications,
  type NotificationsUpdateBody,
} from "../api/account";
import { ApiError } from "../lib/api";
import {
  Alert, Button, Card, ErrorState, Loading, PageHeader, PageShell, Section,
  Table, tdStyle, thStyle, tokens,
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
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!data) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate local editable draft from server-fetched notifications once GET resolves
    setDraft({
      notify_trial_reminders:    data.notify_trial_reminders,
      notify_announcement_email: data.notify_announcement_email,
      notify_locked_day_digest:  data.notify_locked_day_digest,
      notify_daily_summary:      data.notify_daily_summary,
    });
  }, [data]);

  function set<K extends keyof NotificationsUpdateBody>(
    key: K, value: NotificationsUpdateBody[K],
  ) {
    setDraft((d) => ({ ...d, [key]: value }));
    if (saved) setSaved(false);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!data) return;
    setBusy(true);
    setServerError(null);
    try {
      await updateNotifications(draft);
      setSaved(true);
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
      <PageHeader title="Notifications" />

      <div className={styles.grid}>
        <Section title="Your preferences">
          <Card>
            {serverError && <Alert tone="error">{serverError}</Alert>}
            {saved && <Alert tone="success">Notification preferences saved.</Alert>}

            <form onSubmit={onSubmit} autoComplete="off">
              <PrefRow
                id="ntr"
                checked={draft.notify_trial_reminders ?? false}
                disabled={busy || !trialApplies}
                onChange={(v) => set("notify_trial_reminders", v)}
                title="Trial-ending reminder email"
              >
                Send me one email during the last 3 days of my trial so I
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
              </PrefRow>

              <PrefRow
                id="nae"
                checked={draft.notify_announcement_email ?? false}
                disabled={busy}
                onChange={(v) => set("notify_announcement_email", v)}
                title="Announcement emails"
              >
                Get a copy of platform announcements (new features,
                outages, policy changes) by email. Off by default — you'll
                still see every announcement as a banner when you sign in.
              </PrefRow>

              <PrefRow
                id="nldd"
                checked={draft.notify_locked_day_digest ?? false}
                disabled={busy || !digestApplies}
                onChange={(v) => set("notify_locked_day_digest", v)}
                title="Daily book close-out digest"
              >
                One email when a daily book is locked, with the receipts /
                disbursements / over-short totals so you can cross-check
                against the bank. Sent to admins + linked owners only.
                {!digestApplies && (
                  <>
                    <br />
                    <em className={styles.notApplicable}>
                      Not applicable — your role doesn't receive this digest.
                    </em>
                  </>
                )}
              </PrefRow>

              <PrefRow
                id="nds"
                checked={draft.notify_daily_summary ?? false}
                disabled={busy || !summaryApplies}
                onChange={(v) => set("notify_daily_summary", v)}
                title="Daily summary email"
              >
                Nightly per-store email with the prior day's transfer
                count, send volume, receipts, disbursements, and
                over-short — so you see the close-out numbers by morning
                without logging in. Quiet days don't generate an email.
                Sent to admins + linked owners only.
                {!summaryApplies && (
                  <>
                    <br />
                    <em className={styles.notApplicable}>
                      Not applicable — your role doesn't receive this digest.
                    </em>
                  </>
                )}
              </PrefRow>

              <div style={{ marginTop: "1.25rem" }}>
                <Button type="submit" busy={busy} disabled={busy}>
                  {busy ? "Saving…" : "Save preferences"}
                </Button>
              </div>
            </form>
          </Card>
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
                  what="Test pings only (announcement push in roadmap)"
                  control="Enable/disable from the top-right bell in your avatar menu."
                  muted
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


function PrefRow({
  id, checked, disabled, onChange, title, children,
}: {
  id:       string;
  checked:  boolean;
  disabled: boolean;
  onChange: (v: boolean) => void;
  title:    string;
  children: React.ReactNode;
}) {
  return (
    <div className={styles.prefRow}>
      <input
        id={id} type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className={styles.checkbox}
      />
      <div className={styles.prefBody}>
        <label htmlFor={id} className={styles.prefTitle}>{title}</label>
        <div className={styles.prefDesc}>{children}</div>
      </div>
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
