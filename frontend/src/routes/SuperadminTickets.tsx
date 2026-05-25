import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { updateTicket, useAllTickets, type TicketRow } from "../api/support";
import { ApiError } from "../lib/api";
import {
  Alert, Breadcrumbs, Button, Card, EmptyState, ErrorState,
  Field, Loading, PageHeader, PageShell, Pill, Select, Textarea,
} from "../components/ui";

const CATEGORIES = [
  { value: "", label: "All categories" },
  { value: "bug", label: "Bug" },
  { value: "feature", label: "Feature" },
  { value: "question", label: "Question" },
  { value: "feedback", label: "Feedback" },
];

const STATUSES = [
  { value: "", label: "All statuses" },
  { value: "open", label: "Open" },
  { value: "in_progress", label: "In progress" },
  { value: "resolved", label: "Resolved" },
  { value: "closed", label: "Closed" },
];

const STATUS_TONES: Record<string, "neutral" | "accent" | "warning" | "success" | "negative"> = {
  open: "accent",
  in_progress: "warning",
  resolved: "success",
  closed: "neutral",
};

const PRIORITY_TONES: Record<string, "negative" | "warning" | "info" | "neutral"> = {
  P1: "negative",
  P2: "warning",
  P3: "info",
  P4: "neutral",
};

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short", day: "numeric", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

export default function SuperadminTickets() {
  const [statusFilter, setStatusFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const tickets = useAllTickets(statusFilter || undefined, categoryFilter || undefined);

  return (
    <PageShell maxWidth="80rem">
      <Breadcrumbs crumbs={[
        { label: "Superadmin" },
        { label: "Support tickets" },
      ]} />
      <PageHeader
        title="Support tickets"
        subtitle={`${tickets.data?.total ?? 0} tickets across all stores`}
        actions={(
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              {STATUSES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </Select>
            <Select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
              {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
            </Select>
          </div>
        )}
      />

      {tickets.isLoading && <Loading />}
      {tickets.isError && (
        <ErrorState
          message="Could not load tickets."
          onRetry={() => { void tickets.refetch(); }}
        />
      )}

      {tickets.data && tickets.data.tickets.length === 0 && (
        <EmptyState>No tickets match the current filters.</EmptyState>
      )}

      {tickets.data && tickets.data.tickets.map((t) => (
        <TicketCard key={t.id} ticket={t} />
      ))}
    </PageShell>
  );
}

function TicketCard({ ticket: t }: { ticket: TicketRow }) {
  const qc = useQueryClient();
  const [replying, setReplying] = useState(false);
  const [reply, setReply] = useState(t.admin_reply || "");
  const [newStatus, setNewStatus] = useState(t.status);
  const [newPriority, setNewPriority] = useState(t.priority || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, string> = {};
      if (newStatus !== t.status) body.status = newStatus;
      if (newPriority && newPriority !== (t.priority || "")) body.priority = newPriority;
      if (reply.trim() && reply.trim() !== (t.admin_reply || "").trim()) {
        body.admin_reply = reply.trim();
      }
      if (Object.keys(body).length > 0) {
        await updateTicket(t.id, body);
        void qc.invalidateQueries({ queryKey: ["tickets"] });
      }
      setReplying(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update ticket.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <div style={{ padding: "1rem 1.25rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem", flexWrap: "wrap" }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.35rem" }}>
              <span style={{ fontWeight: 700, fontSize: "0.95rem" }}>{t.subject}</span>
              <Pill tone={STATUS_TONES[t.status] ?? "neutral"}>
                {t.status.replace("_", " ")}
              </Pill>
              {t.priority && (
                <Pill tone={PRIORITY_TONES[t.priority] ?? "neutral"}>
                  {t.priority}
                </Pill>
              )}
            </div>
            <div style={{ fontSize: "0.78rem", color: "var(--db-text-muted)" }}>
              {t.submitted_by} · {t.store_name || `Store #${t.store_id}`} · {formatDate(t.created_at)}
              {" · "}
              <span style={{ textTransform: "capitalize" }}>{t.category}</span>
            </div>
          </div>
          <Button tone="secondary" size="sm" onClick={() => setReplying((v) => !v)}>
            {replying ? "Cancel" : "Respond"}
          </Button>
        </div>

        <p style={{ margin: "0.75rem 0 0", whiteSpace: "pre-wrap", fontSize: "0.88rem" }}>{t.body}</p>

        {t.admin_reply && !replying && (
          <div style={{
            marginTop: "0.75rem",
            padding: "0.75rem 1rem",
            background: "var(--db-surface-2, #141414)",
            border: "1px solid var(--db-border, #262626)",
            borderRadius: "0.5rem",
          }}>
            <div style={{ fontSize: "0.72rem", color: "var(--db-text-muted)", marginBottom: "0.25rem" }}>
              Reply by {t.replied_by} · {t.replied_at ? formatDate(t.replied_at) : ""}
            </div>
            <p style={{ margin: 0, whiteSpace: "pre-wrap", fontSize: "0.85rem" }}>{t.admin_reply}</p>
          </div>
        )}

        {error && <Alert tone="error">{error}</Alert>}

        {replying && (
          <form onSubmit={onSave} style={{ marginTop: "0.75rem", display: "flex", flexDirection: "column", gap: "0.65rem" }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.65rem" }}>
              <Field label="Status">
                <Select value={newStatus} onChange={(e) => setNewStatus(e.target.value)}>
                  <option value="open">Open</option>
                  <option value="in_progress">In progress</option>
                  <option value="resolved">Resolved</option>
                  <option value="closed">Closed</option>
                </Select>
              </Field>
              <Field label="Priority">
                <Select value={newPriority} onChange={(e) => setNewPriority(e.target.value)}>
                  <option value="">— None —</option>
                  <option value="P1">P1 — Critical</option>
                  <option value="P2">P2 — High</option>
                  <option value="P3">P3 — Medium</option>
                  <option value="P4">P4 — Low</option>
                </Select>
              </Field>
            </div>
            <Field label="Reply to user">
              <Textarea
                value={reply}
                onChange={(e) => setReply(e.target.value)}
                rows={3}
                placeholder="Type your response…"
              />
            </Field>
            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <Button type="submit" busy={busy} disabled={busy}>
                {busy ? "Saving…" : "Save"}
              </Button>
            </div>
          </form>
        )}
      </div>
    </Card>
  );
}
