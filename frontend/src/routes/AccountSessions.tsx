import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  revokeOtherSessions,
  revokeSession,
  useActiveSessions,
  type ActiveSessionRow,
} from "../api/account";
import { ApiError } from "../lib/api";
import {
  Breadcrumbs,
  Alert, Button, Card, ConfirmDialog, ErrorState, InfoTip, Loading,
  PageHeader, PageShell, Section, space, Table, tdStyle, thStyle, tokens,
  useToast,
} from "../components/ui";
import styles from "./AccountSessions.module.css";

// /app/account/sessions — every browser the current user is signed
// in on. Backed by the refresh-token chain: one row per
// ``session_id`` (stable across rotation). The current session is
// flagged via the JWT's ``sid`` claim and rendered as
// non-revocable from the UI (the API still allows it, but
// dropping yourself out of your own page is bad UX).

export default function AccountSessions() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError, error, refetch } = useActiveSessions();
  const [busy, setBusy] = useState<string | null>(null);
  const [revokeError, setRevokeError] = useState<string | null>(null);
  const toast = useToast();

  async function onRevoke(sessionId: string) {
    setBusy(sessionId);
    setRevokeError(null);
    try {
      await revokeSession(sessionId);
      toast({ message: "Session signed out.", tone: "success" });
      queryClient.invalidateQueries({ queryKey: ["account", "sessions"] });
    } catch (e) {
      setRevokeError(
        e instanceof ApiError ? e.message : "Couldn't sign out that session.",
      );
    } finally {
      setBusy(null);
    }
  }

  // Destructive: gate the "sign out everywhere" action via a
  // confirm dialog so a stray click doesn't yank the user's
  // other browsers / installed PWAs offline.
  const [confirmingRevokeOthers, setConfirmingRevokeOthers] = useState(false);

  async function doRevokeOthers() {
    setBusy("others");
    setRevokeError(null);
    setConfirmingRevokeOthers(false);
    try {
      const result = await revokeOtherSessions();
      toast({
        message: result.revoked === 0
          ? "No other sessions to sign out."
          : `Signed out ${result.revoked} other session${
              result.revoked === 1 ? "" : "s"
            }.`,
        tone: "success",
      });
      queryClient.invalidateQueries({ queryKey: ["account", "sessions"] });
    } catch (e) {
      setRevokeError(
        e instanceof ApiError ? e.message : "Couldn't sign out other sessions.",
      );
    } finally {
      setBusy(null);
    }
  }

  if (isLoading) {
    return (
      <PageShell>
        <PageHeader title="Active sessions" />
        <Loading />
      </PageShell>
    );
  }
  if (isError || !data) {
    return (
      <PageShell>
        <PageHeader title="Active sessions" />
        <ErrorState
          message={
            error instanceof Error
              ? `Couldn't load sessions: ${error.message}`
              : "Couldn't load sessions."
          }
          onRetry={() => { void refetch(); }}
        />
      </PageShell>
    );
  }

  const sessions = data.sessions;
  const otherCount = sessions.filter((s) => !s.is_current).length;

  return (
    <PageShell>

      <Breadcrumbs crumbs={[{ label: "Account", to: "/settings" }, { label: "Sessions" }]} />

      <PageHeader
        title="Active sessions"
        subtitle={
          `${sessions.length} device${sessions.length === 1 ? "" : "s"}`
        }
        actions={otherCount > 0 ? (
          <Button
            tone="secondary"
            size="sm"
            busy={busy === "others"}
            disabled={busy !== null}
            onClick={() => setConfirmingRevokeOthers(true)}
          >
            Sign out everywhere else
          </Button>
        ) : undefined}
      />

      {revokeError && (
        <div style={{ marginBottom: space.lg }}>
          <Alert tone="error">{revokeError}</Alert>
        </div>
      )}

      <Section
        title={
          <>
            Signed-in devices
            <InfoTip text="A session is one browser on one device. Signing out of a session ends every API call from that browser; the next action there will redirect to login." />
          </>
        }
      >
        <Card>
          <Table>
            <thead>
              <tr>
                {["Device", "Last activity", "Signed in", "IP", ""]
                  .map((h, i) => (
                    <th key={i} style={thStyle}>{h}</th>
                  ))}
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => (
                <SessionRow
                  key={s.session_id}
                  session={s}
                  busy={busy === s.session_id}
                  disabled={busy !== null}
                  onRevoke={() => { void onRevoke(s.session_id); }}
                />
              ))}
            </tbody>
          </Table>
        </Card>
      </Section>


      <ConfirmDialog
        open={confirmingRevokeOthers}
        title="Sign out of other devices?"
        message="You'll stay signed in here. Every other browser / installed PWA will be signed out and need to re-authenticate."
        confirmLabel="Sign out everywhere else"
        confirmTone="danger"
        busy={busy === "others"}
        onConfirm={() => { void doRevokeOthers(); }}
        onCancel={() => setConfirmingRevokeOthers(false)}
      />
    </PageShell>
  );
}


function SessionRow({
  session, busy, disabled, onRevoke,
}: {
  session: ActiveSessionRow;
  busy: boolean;
  disabled: boolean;
  onRevoke: () => void;
}) {
  return (
    <tr>
      <td style={tdStyle}>
        <div className={styles.deviceCell}>
          <strong>{describeUserAgent(session.user_agent)}</strong>
          {session.is_current && (
            <span className={styles.currentTag}>This device</span>
          )}
        </div>
        <div className={styles.uaRaw} title={session.user_agent || "(no User-Agent)"}>
          {session.user_agent || "(no User-Agent)"}
        </div>
      </td>
      <td style={tdStyle}>
        <span className={styles.timestamp}>
          {formatRelative(session.last_used_at)}
        </span>
      </td>
      <td style={tdStyle}>
        <span className={styles.timestamp}>
          {formatRelative(session.started_at)}
        </span>
      </td>
      <td style={tdStyle}>
        <span style={{ fontFamily: tokens.fontMono, fontSize: "0.85rem" }}>
          {session.ip_address || "—"}
        </span>
      </td>
      <td style={tdStyle}>
        {session.is_current ? (
          <span className={styles.muted}>Current</span>
        ) : (
          <Button
            tone="danger"
            size="sm"
            busy={busy}
            disabled={disabled}
            onClick={onRevoke}
          >
            Sign out
          </Button>
        )}
      </td>
    </tr>
  );
}


// Heuristic User-Agent → "Chrome on macOS" parser. Doesn't have to
// be perfect — falls back to the raw string in a sub-line so the
// detail-conscious user still sees what was captured.
function describeUserAgent(ua: string): string {
  if (!ua) return "Unknown device";
  const browser =
    /Edg\//.test(ua) ? "Edge" :
    /Firefox\//.test(ua) ? "Firefox" :
    /Chrome\//.test(ua) ? "Chrome" :
    /Safari\//.test(ua) ? "Safari" :
    /curl\//.test(ua) ? "curl" :
    /python-requests/.test(ua) ? "python-requests" :
    "Browser";
  const platform =
    /iPhone/.test(ua) ? "iPhone" :
    /iPad/.test(ua) ? "iPad" :
    /Android/.test(ua) ? "Android" :
    /Mac OS X/.test(ua) ? "macOS" :
    /Windows/.test(ua) ? "Windows" :
    /Linux/.test(ua) ? "Linux" :
    "";
  return platform ? `${browser} on ${platform}` : browser;
}


// "5 minutes ago", "Today at 14:23", "2 days ago", "May 12".
function formatRelative(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const diffMs = Date.now() - d.getTime();
  if (diffMs < 60_000) return "Just now";
  if (diffMs < 3_600_000) {
    const m = Math.floor(diffMs / 60_000);
    return `${m} minute${m === 1 ? "" : "s"} ago`;
  }
  if (diffMs < 24 * 3_600_000) {
    const h = Math.floor(diffMs / 3_600_000);
    return `${h} hour${h === 1 ? "" : "s"} ago`;
  }
  if (diffMs < 7 * 24 * 3_600_000) {
    const days = Math.floor(diffMs / (24 * 3_600_000));
    return `${days} day${days === 1 ? "" : "s"} ago`;
  }
  return d.toLocaleDateString(undefined, {
    month: "short", day: "numeric", year:
      d.getFullYear() === new Date().getFullYear() ? undefined : "numeric",
  });
}
