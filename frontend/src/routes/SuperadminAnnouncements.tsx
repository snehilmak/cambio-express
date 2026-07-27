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
  Breadcrumbs,
  Alert, Button, Card, ConfirmDialog, Empty, Field,
  Input, PageHeader, PageShell, Pill, SectionTitle, Select, Table,
  TableStates, Textarea, tdStyle, thStyle, type PillTone,
} from "../components/ui";
import { useSuperadminStores } from "../api/superadmin";
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

      <Breadcrumbs crumbs={[{ label: "Platform" }, { label: "Announcements" }]} />

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
        <TableStates
          isLoading={isLoading} isError={isError} error={error}
          isEmpty={!data || data.rows.length === 0}
          onRetry={() => { void refetch(); }}
          emptyTitle="No announcements yet."
          rows={3} cols={4}
        />
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
  // Targeting: "all" = global (no target rows), "specific" = the
  // selected store ids. Kept as a Set for O(1) toggle.
  const [targetMode, setTargetMode] = useState<"all" | "specific">("all");
  const [targetIds, setTargetIds] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    // A "specific" targeting with no store picked is almost certainly
    // a mistake — block it rather than silently posting a global
    // banner or one nobody can see.
    const target_store_ids =
      targetMode === "specific" ? Array.from(targetIds) : [];
    if (targetMode === "specific" && target_store_ids.length === 0) {
      setErr("Pick at least one store, or switch to All stores.");
      return;
    }
    setBusy(true);
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
        target_store_ids,
      });
      setMessage(""); setExpiresDays("0"); setBroadcast(false);
      setScheduleLocal("");
      setTargetMode("all"); setTargetIds(new Set());
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
        <Field label="Audience">
          <div className={styles.targetModes}>
            <label className={styles.targetMode}>
              <input
                type="radio" name="targetMode" checked={targetMode === "all"}
                onChange={() => setTargetMode("all")}
              />
              <span>All stores</span>
            </label>
            <label className={styles.targetMode}>
              <input
                type="radio" name="targetMode" checked={targetMode === "specific"}
                onChange={() => setTargetMode("specific")}
              />
              <span>Specific stores</span>
            </label>
          </div>
          {targetMode === "specific" && (
            <StorePicker selected={targetIds} onChange={setTargetIds} />
          )}
        </Field>
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

function StorePicker({
  selected, onChange,
}: {
  selected: Set<number>;
  onChange: (next: Set<number>) => void;
}) {
  const { data, isLoading, isError } = useSuperadminStores();
  const [filter, setFilter] = useState("");

  const stores = data?.rows ?? [];
  const needle = filter.trim().toLowerCase();
  const shown = needle
    ? stores.filter(
        (s) =>
          s.name.toLowerCase().includes(needle) ||
          s.slug.toLowerCase().includes(needle),
      )
    : stores;

  function toggle(id: number) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange(next);
  }

  if (isLoading) return <p className={styles.helpText}>Loading stores…</p>;
  if (isError) return <Alert tone="error">Could not load stores.</Alert>;

  return (
    <div className={styles.storePicker}>
      <Input
        type="search"
        placeholder="Filter stores…"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />
      <div className={styles.storeList}>
        {shown.length === 0 ? (
          <span className={styles.helpText}>No stores match.</span>
        ) : (
          shown.map((s) => (
            <label key={s.store_id} className={styles.storeOption}>
              <input
                type="checkbox"
                checked={selected.has(s.store_id)}
                onChange={() => toggle(s.store_id)}
              />
              <span>{s.name}</span>
              <Pill tone="neutral">{s.plan}</Pill>
            </label>
          ))
        )}
      </div>
      <div className={styles.pickerMeta}>
        <span>{selected.size} selected</span>
        {selected.size > 0 && (
          <button
            type="button" className={styles.linkBtn}
            onClick={() => onChange(new Set())}
          >
            Clear
          </button>
        )}
      </div>
    </div>
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
          {[
            "Message", "Level", "Status", "Audience", "Posted", "Expires",
            "Broadcast", "Actions",
          ].map((h, i) => (
            <th key={i} style={thStyle}>{h}</th>
          ))}
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
  const [confirmingDelete, setConfirmingDelete] = useState(false);

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

  async function doDelete() {
    setErr(null); setBusy(true);
    try {
      await deleteAnnouncement(row.id);
      onChanged();
      setConfirmingDelete(false);
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
        <AudienceCell row={row} />
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
        <BroadcastCell row={row} />
      </td>
      <td style={{ ...tdStyle, verticalAlign: "top" }}>
        <div className={styles.actionsRow}>
          <Button tone="secondary" size="sm" busy={busy} onClick={onToggle}>
            {row.is_active ? "Disable" : "Enable"}
          </Button>
          <Button tone="danger" size="sm" busy={busy}
            onClick={() => setConfirmingDelete(true)}>
            Delete
          </Button>
        </div>
        {err && <span className={styles.rowError}>{err}</span>}
        <ConfirmDialog
          open={confirmingDelete}
          title="Delete announcement"
          message="Delete this announcement permanently? Operators who haven't dismissed it yet will lose the message."
          confirmLabel="Delete"
          confirmTone="danger"
          busy={busy}
          onConfirm={() => { void doDelete(); }}
          onCancel={() => setConfirmingDelete(false)}
        />
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


// Audience cell: "All stores" for a global announcement (no
// targeting rows) or an "N stores" pill listing the target store
// names underneath. Targeting was added in PR B — pre-targeting
// rows come back with an empty list and render as global.
function AudienceCell({ row }: { row: AnnouncementRow }) {
  const names = row.target_store_names ?? [];
  if (names.length === 0) {
    return <Pill tone="neutral">All stores</Pill>;
  }
  return (
    <div>
      <Pill tone="info">
        {names.length} {names.length === 1 ? "store" : "stores"}
      </Pill>
      <div className={styles.audienceNames}>
        {names.slice(0, 3).join(", ")}
        {names.length > 3 ? ` +${names.length - 3} more` : ""}
      </div>
    </div>
  );
}

// Broadcast-state pill: shows whether "Also email all users" was
// ticked at create time and whether the fan-out has fired yet.
//
//   not requested  → "—"            (creator didn't ask for email)
//   requested + not sent → "pending"  (queued or scheduled banner not yet activated)
//   sent           → "sent · MMM dd"  (with date the broadcast landed)
function BroadcastCell({ row }: { row: AnnouncementRow }) {
  if (!row.broadcast_requested) {
    return <span className={styles.dash}>—</span>;
  }
  if (!row.broadcast_sent_at) {
    return <Pill tone="warning">pending</Pill>;
  }
  const sent = new Date(row.broadcast_sent_at);
  const stamp = Number.isNaN(sent.getTime())
    ? row.broadcast_sent_at.slice(0, 10)
    : sent.toLocaleDateString(undefined, {
        month: "short", day: "numeric",
      });
  return <Pill tone="accent">sent · {stamp}</Pill>;
}
