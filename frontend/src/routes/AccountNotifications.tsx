import { useEffect, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  updateNotifications, useNotifications,
  type NotificationsUpdateBody,
} from "../api/account";
import { ApiError } from "../lib/api";
import { ErrorState, Loading } from "../components/ui";

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
      <main style={pageStyle}>
        <h1 style={titleStyle}>Notifications</h1>
        <Loading />
      </main>
    );
  }
  if (isError || !data) {
    return (
      <main style={pageStyle}>
        <h1 style={titleStyle}>Notifications</h1>
        <ErrorState
          message={`Couldn't load preferences.${error instanceof Error ? ` ${error.message}` : ""}`}
          onRetry={() => { void refetch(); }}
        />
      </main>
    );
  }

  const trialApplies = data.trial_toggle_applies;
  const trialNotApplicableNote = data.role === "admin" || data.role === "owner"
    ? "Not applicable for your account right now — you're on a paid plan (or no active trial)."
    : "Not applicable for your account right now — you're on a role that doesn't own a trial.";

  return (
    <main style={pageStyle}>
      <header style={{ marginBottom: "1rem" }}>
        <h1 style={titleStyle}>Notifications</h1>
      </header>

      <div style={gridStyle}>
        <section style={cardStyle}>
          <h2 style={cardTitleStyle}>Your preferences</h2>

          {serverError && <div style={alertErrorStyle}>{serverError}</div>}
          {saved && (
            <div style={alertOkStyle} role="status">
              Notification preferences saved.
            </div>
          )}

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
                  <em style={{ fontStyle: "italic", opacity: 0.85 }}>
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

            <div style={{ marginTop: "1.25rem" }}>
              <button
                type="submit" disabled={busy} style={btnPrimaryStyle}
              >
                {busy ? "Saving…" : "Save preferences"}
              </button>
            </div>
          </form>
        </section>

        <section style={cardStyle}>
          <h2 style={cardTitleStyle}>What DineroBook sends you</h2>
          <p style={leadStyle}>
            We send as little as possible. Here's the complete list —
            anything user-controllable has a toggle on the left; the
            rest is either essential (password reset) or not yet
            implemented.
          </p>
          <table style={tableStyle}>
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
          </table>
          <p style={fineStyle}>
            More channels coming (announcement broadcast emails, daily
            summary emails). Each one will land here as a toggle
            alongside its real sender — we don't ship controls for
            imaginary notifications.
          </p>
        </section>
      </div>
    </main>
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
    <div style={prefRowStyle}>
      <input
        id={id} type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        style={checkboxStyle}
      />
      <div style={{ flex: 1 }}>
        <label htmlFor={id} style={prefTitleStyle}>{title}</label>
        <div style={prefDescStyle}>{children}</div>
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
    ? { ...cellStyle, color: "var(--db-text-muted, #a3a3a3)" }
    : cellStyle;
  return (
    <tr>
      <td style={cellStyle}>{channel}</td>
      <td style={cellStyle}>{what}</td>
      <td style={ctrlStyle}>{control}</td>
    </tr>
  );
}


const pageStyle: React.CSSProperties = {
  flex: 1, display: "flex", flexDirection: "column",
  padding: "2rem 1.5rem", maxWidth: "60rem",
  margin: "0 auto", width: "100%", boxSizing: "border-box",
};

const titleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "clamp(1.5rem, 3.5vw, 2rem)",
  fontWeight: 600, margin: 0,
};

const gridStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(20rem, 1fr))",
  gap: "1rem",
};

const cardStyle: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem", padding: "1.25rem",
};

const cardTitleStyle: React.CSSProperties = {
  margin: "0 0 0.6rem", fontSize: "1.05rem", fontWeight: 600,
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
};

const leadStyle: React.CSSProperties = {
  margin: "0 0 1rem", color: "var(--db-text-muted, #a3a3a3)",
  fontSize: "0.88rem", lineHeight: 1.55,
};

const fineStyle: React.CSSProperties = {
  marginTop: "1rem", color: "var(--db-text-muted, #a3a3a3)",
  fontSize: "0.78rem", lineHeight: 1.55,
};

const prefRowStyle: React.CSSProperties = {
  display: "flex",
  gap: "0.75rem",
  alignItems: "flex-start",
  padding: "0.75rem 0",
  borderBottom: "1px solid var(--db-border-subtle, #1f1f1f)",
};

const checkboxStyle: React.CSSProperties = {
  width: "1.05rem", height: "1.05rem",
  marginTop: "0.2rem", flexShrink: 0,
  accentColor: "var(--db-neon, #3fff00)",
  cursor: "pointer",
};

const prefTitleStyle: React.CSSProperties = {
  fontSize: "0.95rem", fontWeight: 500,
  color: "var(--db-text, #e5e5e5)",
  display: "block",
  marginBottom: "0.25rem",
  cursor: "pointer",
};

const prefDescStyle: React.CSSProperties = {
  fontSize: "0.85rem", lineHeight: 1.55,
  color: "var(--db-text-muted, #a3a3a3)",
};

const tableStyle: React.CSSProperties = {
  width: "100%", borderCollapse: "collapse",
  fontSize: "0.88rem",
};

const thStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "0.55rem 0.7rem",
  color: "var(--db-text-muted, #a3a3a3)",
  fontWeight: 500,
  fontSize: "0.72rem",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  borderBottom: "1px solid var(--db-border, #262626)",
};

const cellStyle: React.CSSProperties = {
  padding: "0.6rem 0.7rem",
  borderBottom: "1px solid var(--db-border-subtle, #1f1f1f)",
  verticalAlign: "top",
};

const btnPrimaryStyle: React.CSSProperties = {
  padding: "0.65rem 1.1rem",
  fontWeight: 600, fontSize: "0.92rem",
  background: "var(--db-neon, #3fff00)",
  color: "var(--db-neon-ink, #001a0f)",
  border: "none", borderRadius: "0.5rem",
  cursor: "pointer",
};

const alertErrorStyle: React.CSSProperties = {
  padding: "0.6rem 0.85rem",
  marginBottom: "0.75rem",
  background: "rgba(255,77,109,0.08)",
  border: "1px solid rgba(255,77,109,0.3)",
  borderRadius: "0.5rem",
  color: "var(--db-negative, #ff4d6d)",
  fontSize: "0.88rem",
};

const alertOkStyle: React.CSSProperties = {
  padding: "0.6rem 0.85rem",
  marginBottom: "0.75rem",
  background: "rgba(63,255,0,0.08)",
  border: "1px solid rgba(63,255,0,0.3)",
  borderRadius: "0.5rem",
  color: "var(--db-neon, #3fff00)",
  fontSize: "0.88rem",
};

