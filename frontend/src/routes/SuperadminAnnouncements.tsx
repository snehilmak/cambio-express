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
  Button, Card, Empty, Field, inputStyle, monoStyle, PageHeader,
  PageShell, Pill, SectionTitle, tokens,
  type PillTone,
} from "../components/ui";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";

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
  const { data, isLoading, isError, error } = useAnnouncements();

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

      <div style={{ height: "1rem" }} />

      <Card>
        <SectionTitle>History</SectionTitle>
        <p
          style={{
            margin: "0.25rem 0 1rem",
            color: tokens.textMuted,
            fontSize: "0.85rem",
          }}
        >
          Banners shown to every user across the app. Disable to hide
          without deleting; delete to remove permanently.
        </p>
        {isLoading && <Empty>Loading…</Empty>}
        {isError && (
          <Empty error>
            {error instanceof Error ? error.message : "Could not load"}
          </Empty>
        )}
        {data && data.rows.length === 0 && !isLoading && (
          <Empty>No announcements yet.</Empty>
        )}
        {data && data.rows.length > 0 && (
          <Table rows={data.rows} onChanged={refresh} />
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
      });
      setMessage(""); setExpiresDays("0"); setBroadcast(false);
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
      <form
        onSubmit={onSubmit}
        style={{ display: "flex", flexDirection: "column", gap: "0.75rem", marginTop: "0.75rem" }}
      >
        <Field label="Message">
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Maintenance window Friday 9pm–11pm CT"
            rows={2}
            required
            style={{ ...inputStyle, resize: "vertical", minHeight: "3.5rem" }}
          />
        </Field>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(11rem, 1fr))",
            gap: "0.75rem",
          }}
        >
          <Field label="Level">
            <select
              value={level}
              onChange={(e) =>
                setLevel(e.target.value as CreateAnnouncementBody["level"])
              }
              style={inputStyle}
            >
              {LEVELS.map((l) => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
          </Field>
          <Field label="Expires (days)">
            <input
              type="number"
              min="0"
              max="365"
              value={expiresDays}
              onChange={(e) => setExpiresDays(e.target.value)}
              style={inputStyle}
              placeholder="0 = no expiry"
            />
          </Field>
          <Field label="Email blast">
            <label
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.5rem",
                padding: "0.55rem 0",
                fontSize: "0.95rem",
              }}
            >
              <input
                type="checkbox"
                checked={broadcast}
                onChange={(e) => setBroadcast(e.target.checked)}
              />
              <span>Also email opted-in users</span>
            </label>
          </Field>
        </div>
        {err && (
          <p
            role="alert"
            style={{ color: tokens.negative, fontSize: "0.9rem", margin: 0 }}
          >
            {err}
          </p>
        )}
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
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

function Table({
  rows, onChanged,
}: {
  rows: AnnouncementRow[];
  onChanged: () => void;
}) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.92rem" }}>
        <thead>
          <tr>
            {["Message", "Level", "Status", "Posted", "Expires", "Actions"].map(
              (h, i) => (
                <th
                  key={i}
                  style={{
                    textAlign: "left",
                    padding: "0.6rem 0.75rem",
                    color: tokens.textMuted,
                    fontWeight: 500,
                    fontSize: "0.78rem",
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                    borderBottom: `1px solid ${tokens.border}`,
                  }}
                >
                  {h}
                </th>
              ),
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <Row key={r.id} row={r} onChanged={onChanged} />
          ))}
        </tbody>
      </table>
    </div>
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
      <td style={{ ...cellStyle, maxWidth: "32rem" }}>{row.message}</td>
      <td style={cellStyle}>
        <Pill tone={LEVEL_TONE[row.level] ?? "neutral"}>{row.level}</Pill>
      </td>
      <td style={cellStyle}>
        {row.is_visible ? (
          <Pill tone="accent">live</Pill>
        ) : row.is_active ? (
          <Pill tone="warning">inactive window</Pill>
        ) : (
          <Pill tone="neutral">disabled</Pill>
        )}
      </td>
      <td style={cellStyle}>
        <span style={{ ...monoStyle, fontSize: "0.85rem", color: tokens.textMuted }}>
          {row.created_at.slice(0, 10)}
        </span>
      </td>
      <td style={cellStyle}>
        {row.expires_at ? (
          <span style={{ ...monoStyle, fontSize: "0.85rem", color: tokens.textMuted }}>
            {row.expires_at.slice(0, 10)}
          </span>
        ) : (
          <span style={{ color: tokens.textMuted }}>—</span>
        )}
      </td>
      <td style={cellStyle}>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <Button tone="secondary" busy={busy} onClick={onToggle}>
            {row.is_active ? "Disable" : "Enable"}
          </Button>
          <Button tone="danger" busy={busy} onClick={onDelete}>
            Delete
          </Button>
        </div>
        {err && (
          <span style={{ color: tokens.negative, fontSize: "0.8rem", marginLeft: "0.5rem" }}>
            {err}
          </span>
        )}
      </td>
    </tr>
  );
}

const cellStyle: React.CSSProperties = {
  padding: "0.7rem 0.75rem",
  borderBottom: `1px solid ${tokens.borderSubtle}`,
  verticalAlign: "top",
};
