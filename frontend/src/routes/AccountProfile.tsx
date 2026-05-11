import { useEffect, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  updateProfile, useProfile,
  type ProfileUpdateBody,
} from "../api/account";
import { ApiError } from "../lib/api";
import {
  Card, ErrorState, Loading, PageHeader, PageShell, Section, tokens,
} from "../components/ui";

// /app/account/profile — personal info form (full_name, email,
// phone, timezone) + read-only metadata (username, role,
// created_at, last_login_at). Field-level errors mirror the legacy
// Jinja form: server returns 422 with `field_errors` keyed by name,
// SPA renders inline.
//
// The legacy /account/profile also had an "Appearance" theme
// picker. That UI is intentionally NOT ported — CLAUDE.md
// invariant #1 fixes the SPA to dark-only, so the picker would
// have nothing to do.

export default function AccountProfile() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError, error, refetch } = useProfile();

  const [draft, setDraft] = useState<ProfileUpdateBody>({});
  const [busy, setBusy]   = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);

  // Hydrate the draft once the GET resolves so the inputs are
  // controlled from first paint.
  useEffect(() => {
    if (!data) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate local editable draft from server-fetched profile so inputs are controlled from first paint
    setDraft({
      full_name: data.full_name,
      email:     data.email,
      phone:     data.phone,
      timezone:  data.timezone,
    });
  }, [data]);

  function set<K extends keyof ProfileUpdateBody>(
    key: K, value: ProfileUpdateBody[K],
  ) {
    setDraft((d) => ({ ...d, [key]: value }));
    if (saved) setSaved(false);
    if (fieldErrors[key as string]) {
      setFieldErrors((e) => {
        const next = { ...e }; delete next[key as string]; return next;
      });
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!data) return;
    setBusy(true);
    setServerError(null);
    setFieldErrors({});
    try {
      await updateProfile(draft);
      setSaved(true);
      // Refetch so read-only metadata + the canonical normalized
      // values (lowercased email, stripped phone) come back.
      queryClient.invalidateQueries({ queryKey: ["account", "profile"] });
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        const detail = (err.body as { detail?: { field_errors?: Record<string, string> } })?.detail;
        if (detail?.field_errors) {
          setFieldErrors(detail.field_errors);
        } else {
          setServerError(err.message);
        }
      } else if (err instanceof ApiError) {
        setServerError(err.message);
      } else {
        setServerError("Network error. Try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  if (isLoading) {
    return (
      <PageShell maxWidth="40rem">
        <PageHeader title="Profile" />
        <Loading />
      </PageShell>
    );
  }
  if (isError || !data) {
    return (
      <PageShell maxWidth="40rem">
        <PageHeader title="Profile" />
        <ErrorState
          message={`Couldn't load your profile.${error instanceof Error ? ` ${error.message}` : ""}`}
          onRetry={() => { void refetch(); }}
        />
      </PageShell>
    );
  }

  const memberSince = data.created_at
    ? new Date(data.created_at).toLocaleDateString("en-US", {
        month: "short", day: "2-digit", year: "numeric",
      })
    : "—";
  const lastLogin = data.last_login_at
    ? formatTs(data.last_login_at)
    : "—";

  return (
    <PageShell maxWidth="40rem">
      <PageHeader title="Profile" />

      <Section title="Personal info">
        <Card padding="1.5rem">
          <p style={leadStyle}>
            Used for things addressed to you personally — receipts,
            password-reset emails, audit-log attribution. Your
            username and role are set by your store admin and shown
            here for reference.
          </p>

          {serverError && <div style={alertErrorStyle}>{serverError}</div>}
          {saved && (
            <div style={alertOkStyle} role="status">Profile updated.</div>
          )}

          <form onSubmit={onSubmit} autoComplete="off">
            <FormField label="Display name *" error={fieldErrors.full_name}>
              <input
                type="text" maxLength={120} required
                value={draft.full_name ?? ""}
                onChange={(e) => set("full_name", e.target.value)}
                disabled={busy} style={inputStyle}
              />
            </FormField>

            <FormField label="Email" error={fieldErrors.email}
                   hint="We use this for password reset and account notices. Leave blank if you'd rather not receive email.">
              <input
                type="email" maxLength={255}
                autoComplete="email"
                placeholder="you@example.com"
                value={draft.email ?? ""}
                onChange={(e) => set("email", e.target.value)}
                disabled={busy} style={inputStyle}
              />
            </FormField>

            <FormField label="Phone" error={fieldErrors.phone}>
              <input
                type="tel" maxLength={40}
                autoComplete="tel"
                placeholder="+1 555 123 4567"
                value={draft.phone ?? ""}
                onChange={(e) => set("phone", e.target.value)}
                disabled={busy} style={inputStyle}
              />
            </FormField>

            <FormField label="Timezone" error={fieldErrors.timezone}
                   hint="Daily reports + audit timestamps render in this zone for you. Don't see yours? Ask your admin to add it.">
              <select
                value={draft.timezone ?? ""}
                onChange={(e) => set("timezone", e.target.value)}
                disabled={busy} style={inputStyle}
              >
                <option value="">— Use store / UTC default —</option>
                {data.timezone_choices.map((tz) => (
                  <option key={tz} value={tz}>{tz}</option>
                ))}
              </select>
            </FormField>

            <hr style={hrStyle} />

            <div style={readOnlyGridStyle}>
              <ReadOnly label="Username" value={data.username} />
              <ReadOnly label="Role" value={
                data.role.charAt(0).toUpperCase() + data.role.slice(1)
              } />
              <ReadOnly label="Member since" value={memberSince} />
              <ReadOnly label="Last sign-in" value={lastLogin} />
            </div>

            <div style={{ marginTop: "1.5rem", display: "flex", gap: "0.6rem" }}>
              <button
                type="submit" disabled={busy} style={btnPrimaryStyle}
              >
                {busy ? "Saving…" : "Save profile"}
              </button>
              <a href="/app/settings" style={btnOutlineStyle}>
                Security →
              </a>
            </div>
          </form>
        </Card>
      </Section>
    </PageShell>
  );
}


function FormField({
  label, error, hint, children,
}: {
  label:    string;
  error?:   string;
  hint?:    string;
  children: React.ReactNode;
}) {
  return (
    <label style={fieldStyle}>
      <span style={labelStyle}>{label}</span>
      {children}
      {error && <span style={fieldErrorStyle}>{error}</span>}
      {hint && !error && <span style={hintStyle}>{hint}</span>}
    </label>
  );
}


function ReadOnly({ label, value }: { label: string; value: string }) {
  return (
    <label style={fieldStyle}>
      <span style={labelStyle}>{label}</span>
      <input
        type="text" disabled value={value || "—"}
        style={{ ...inputStyle, opacity: 0.7, cursor: "not-allowed" }}
      />
    </label>
  );
}


function formatTs(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const month = d.toLocaleString("en-US", { month: "short", timeZone: "UTC" });
  const day   = String(d.getUTCDate()).padStart(2, "0");
  const yr    = d.getUTCFullYear();
  const hh    = String(d.getUTCHours()).padStart(2, "0");
  const mm    = String(d.getUTCMinutes()).padStart(2, "0");
  return `${month} ${day}, ${yr} ${hh}:${mm} UTC`;
}


const leadStyle: React.CSSProperties = {
  margin: "0 0 1.25rem", color: tokens.textMuted,
  fontSize: "0.88rem", lineHeight: 1.55,
};

const fieldStyle: React.CSSProperties = {
  display: "flex", flexDirection: "column",
  gap: "0.35rem", marginBottom: "1rem",
};

const labelStyle: React.CSSProperties = {
  fontSize: "0.7rem", letterSpacing: "0.06em",
  textTransform: "uppercase", fontWeight: 600,
  color: tokens.textMuted,
};

const inputStyle: React.CSSProperties = {
  padding: "0.6rem 0.75rem",
  background: "var(--db-bg-input, #0d0d0d)",
  color: tokens.text,
  border: `1px solid ${tokens.border}`,
  borderRadius: "0.5rem", fontSize: "0.95rem",
  fontFamily: tokens.fontBody,
};

const hintStyle: React.CSSProperties = {
  fontSize: "0.78rem", color: tokens.textMuted,
};

const fieldErrorStyle: React.CSSProperties = {
  fontSize: "0.8rem", color: tokens.negative,
};

const hrStyle: React.CSSProperties = {
  border: 0, borderTop: `1px solid ${tokens.border}`,
  margin: "1.5rem 0 1rem",
};

const readOnlyGridStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(12rem, 1fr))",
  gap: "0.6rem 1rem",
};

const btnPrimaryStyle: React.CSSProperties = {
  padding: "0.65rem 1.1rem",
  fontWeight: 600, fontSize: "0.92rem",
  background: tokens.accent,
  color: tokens.onAccent,
  border: "none", borderRadius: "0.5rem",
  cursor: "pointer",
};

const btnOutlineStyle: React.CSSProperties = {
  padding: "0.65rem 1.1rem",
  fontWeight: 500, fontSize: "0.92rem",
  background: "transparent",
  color: tokens.text,
  border: `1px solid ${tokens.border}`,
  borderRadius: "0.5rem",
  textDecoration: "none",
  display: "inline-block",
};

const alertErrorStyle: React.CSSProperties = {
  padding: "0.6rem 0.85rem",
  marginBottom: "1rem",
  background: "rgba(255,77,109,0.08)",
  border: "1px solid rgba(255,77,109,0.3)",
  borderRadius: "0.5rem",
  color: tokens.negative,
  fontSize: "0.88rem",
};

const alertOkStyle: React.CSSProperties = {
  padding: "0.6rem 0.85rem",
  marginBottom: "1rem",
  background: "rgba(63,255,0,0.08)",
  border: "1px solid rgba(63,255,0,0.3)",
  borderRadius: "0.5rem",
  color: tokens.accent,
  fontSize: "0.88rem",
};
