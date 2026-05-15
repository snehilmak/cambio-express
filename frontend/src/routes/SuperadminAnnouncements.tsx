import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  createAnnouncement,
  deleteAnnouncement,
  toggleAnnouncement,
  useAnnouncements,
  type AnnouncementRow,
  type CreateAnnouncementBody,
} from "../api/announcements";
import {
  Alert, Button, Card, Empty, EmptyState, ErrorState, Field, Input,
  PageHeader, PageShell, Pill, SectionTitle, Select, Table, TableSkeleton,
  Textarea, tdStyle, thStyle, type PillTone,
} from "../components/ui";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import styles from "./SuperadminAnnouncements.module.css";

// Superadmin-only banner CRUD at /app/superadmin/announcements.
// Mirrors the legacy /superadmin/controls?tab=announcements panel.

const LEVELS: Array<CreateAnnouncementBody["level"]> = [
  "info", "warning", "error", "success",
];

const LEVEL_TONE: Record<string, PillTone> = {
  info:    "info",
  warning: "warning",
  error:   "negative",
  success: "accent",
};

export default function SuperadminAnnouncements() {
  const identity = getCurrentIdentity();
  const qc = useQueryClient();
  const { data, isLoading, isError, error, refetch } = useAnnouncements();

  if (identity?.role !== "superadmin") {
    return (
      <PageShell>
        <PageHeader title="Announcements" />
        <Empty>Superadmin scope required.</Empty>
      </PageShell>
    );
  }

  function refresh() {
    qc.invalidateQueries({ queryKey: ["announcements", "list"] });
  }

  return (
    <PageShell>
      <PageHeader
        title="Announcements"
        subtitle={data ? `${data.total.toLocaleString()} on file` : "—"}
      />

      <CreateForm onCreated={refresh} />

      <div className={styles.gap} />

      <Card>
        <SectionTitle>History</SectionTitle>
        <p className={styles.helpText}>
          Banners shown to every user across the app. Disable to hide
          without deleting; delete to remove permanently.
        </p>
        {isLoading && <TableSkeleton rows={3} cols={4} />}
        {isError && (
          <ErrorState
            message={error instanceof Error ? error.message : "Could not load"}
            onRetry={() => { void refetch(); }}
          />
        )}
        {data && data.rows.length === 0 && !isLoading && (
          <EmptyState title="No announcements yet." />
        )}
        {data && data.rows.length > 0 && (
          <AnnouncementsTable rows={data.rows} onChanged={refresh} />
        )}
      </Card>
    </PageShell>
  );
}

function CreateForm({ onCreated }: { onCreated: () => void }) {
  const [message, setMessage] = useState("");
  const [level, setLevel] =
    useState<CreateAnnouncementBody["level"]>("info");
  const [expiresDays, setExpiresDays] = useState("0");
  const [broadcast, setBroadcast] = useState(false);
  // Local form field for the optional schedule. Empty = "start
  // now". Stored as `<input type="datetime-local">` returns a
  // local string ("2026-05-15T14:00") so we convert to ISO+UTC
  // at submit.
  const [scheduleLocal, setScheduleLocal] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErr(null); setBusy(true);
    try {
      await createAnnouncement({
        message: message.trim(),
        level,
        expires_days: Number(expiresDays) || 0,
        broadcast,
        // Convert "2026-05-15T14:00" (browser-local) to a real
        // ISO datetime so the server interprets the correct UTC
        // instant. Empty stays empty.
        start_at_iso: scheduleLocal
          ? new Date(scheduleLocal).toISOString()
          : "",
      });
      setMessage(""); setExpiresDays("0"); setBroadcast(false);
      setScheduleLocal("");
      onCreated();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not post.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <SectionTitle>Post a new banner</SectionTitle>
      <form onSubmit={onSubmit} className={styles.form}>
        <Field label="Message">
          <Textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Maintenance window Friday 9pm–11pm CT"
            rows={2}
            required
            style={{ minHeight: "3.5rem" }}
          />
        </Field>
        <div className={styles.fieldGrid}>
          <Field label="Level">
            <Select
              value={level}
              onChange={(e) =>
                setLevel(e.target.value as CreateAnnouncementBody["level"])
              }
            >
              {LEVELS.map((l) => (
                <option key={l} value={l}>{l}</option>
              ))}
            </Select>
          </Field>
          <Field label="Expires (days)">
            <Input
              type="number"
              min="0"
              max="365"
              value={expiresDays}
              onChange={(e) => setExpiresDays(e.target.value)}
              placeholder="0 = no expiry"
            />
          </Field>
          <Field label="Schedule for later (optional)">
            <Input
              type="datetime-local"
              value={scheduleLocal}
              onChange={(e) => setScheduleLocal(e.target.value)}
            />
          </Field>
          <Field label="Email blast">
            <label className={styles.checkRow}>
              <input
                type="checkbox"
                checked={broadcast}
                onChange={(e) => setBroadcast(e.target.checked)}
              />
              <span>Also email opted-in users</span>
            </label>
          </Field>
        </div>
        {err && <Alert tone="error">{err}</Alert>}
        <div className={styles.submitRow}>
          <Button
            type="submit"
            tone="primary"
            busy={busy}
            disabled={busy || !message.trim()}
          >
            {busy ? "Posting…" : "Post banner"}
          </Button>
        </div>
      </form>
    </Card>
  );
}

function AnnouncementsTable({
  rows, onChanged,
}: {
  rows: AnnouncementRow[];
  onChanged: () => void;
}) {
  return (
    <Table>
      <thead>
        <tr>
          {["Message", "Level", "Status", "Posted", "Expires", "Actions"].map(
            (h, i) => (
              <th key={i} style={thStyle}>{h}</th>
            ),
          )}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <Row key={r.id} row={r} onChanged={onChanged} />
        ))}
      </tbody>
    </Table>
  );
}

function Row({ row, onChanged }: { row: AnnouncementRow; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function onToggle() {
    setErr(null); setBusy(true);
    try {
      await toggleAnnouncement(row.id, !row.is_active);
      onChanged();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not toggle.");
    } finally {
      setBusy(false);
    }
  }

  async function onDelete() {
    if (!confirm("Delete this announcement permanently?")) return;
    setErr(null); setBusy(true);
    try {
      await deleteAnnouncement(row.id);
      onChanged();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not delete.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <tr>
      <td style={{ ...tdStyle, verticalAlign: "top" }} className={styles.cellWide}>
        {row.message}
      </td>
      <td style={{ ...tdStyle, verticalAlign: "top" }}>
        <Pill tone={LEVEL_TONE[row.level] ?? "neutral"}>{row.level}</Pill>
      </td>
      <td style={{ ...tdStyle, verticalAlign: "top" }}>
        {row.is_visible ? (
          <Pill tone="accent">live</Pill>
        ) : !row.is_active ? (
          <Pill tone="neutral">disabled</Pill>
        ) : isScheduledForFuture(row.starts_at) ? (
          <Pill tone="info">
            scheduled · {formatScheduleHint(row.starts_at)}
          </Pill>
        ) : (
          <Pill tone="warning">expired</Pill>
        )}
      </td>
      <td style={{ ...tdStyle, verticalAlign: "top" }}>
        <span className={styles.dateCell}>
          {row.created_at.slice(0, 10)}
        </span>
      </td>
      <td style={{ ...tdStyle, verticalAlign: "top" }}>
        {row.expires_at ? (
          <span className={styles.dateCell}>
            {row.expires_at.slice(0, 10)}
          </span>
        ) : (
          <span className={styles.dash}>—</span>
        )}
      </td>
      <td style={{ ...tdStyle, verticalAlign: "top" }}>
        <div className={styles.actionsRow}>
          <Button tone="secondary" size="sm" busy={busy} onClick={onToggle}>
            {row.is_active ? "Disable" : "Enable"}
          </Button>
          <Button tone="danger" size="sm" busy={busy} onClick={onDelete}>
            Delete
          </Button>
        </div>
        {err && <span className={styles.rowError}>{err}</span>}
      </td>
    </tr>
  );
}

// True when `starts_at` is a parseable future date — drives the
// "scheduled" status pill on each table row.
function isScheduledForFuture(iso: string): boolean {
  if (!iso) return false;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return false;
  return t > Date.now();
}

// Short, human-readable hint for when the schedule will fire,
// rendered inside the scheduled status pill.
function formatScheduleHint(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const diffMs = d.getTime() - Date.now();
  const diffH = Math.round(diffMs / 3_600_000);
  if (diffH < 24) return `in ${diffH}h`;
  return d.toLocaleDateString(undefined, {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}
