import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { TICKET_STATUS_TONES, updateTicket, useAllTickets, type TicketRow } from "../api/support";
import { TicketThread } from "../components/TicketThread";
import { fmtDateTime } from "../lib/formatters";
import { ApiError } from "../lib/api";
import {
  Alert, Breadcrumbs, Button, Card, EmptyState, ErrorState,
  Field, Loading, PageHeader, PageShell, Pill, Select,
  useToast,
} from "../components/ui";
import styles from "./SuperadminTickets.module.css";

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


const PRIORITY_TONES: Record<string, "negative" | "warning" | "info" | "neutral"> = {
  P1: "negative",
  P2: "warning",
  P3: "info",
  P4: "neutral",
};


export default function SuperadminTickets() {
  const [statusFilter, setStatusFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const tickets = useAllTickets(statusFilter || undefined, categoryFilter || undefined);

  return (
    <PageShell>
      <Breadcrumbs crumbs={[
        { label: "Superadmin" },
        { label: "Support tickets" },
      ]} />
      <PageHeader
        title="Support tickets"
        subtitle={`${tickets.data?.total ?? 0} tickets across all stores`}
        actions={(
          <div className={styles.filterRow}>
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
        <EmptyState title="No tickets match the current filters." />
      )}

      {tickets.data && tickets.data.tickets.map((t) => (
        <TicketCard key={t.id} ticket={t} />
      ))}
    </PageShell>
  );
}

function TicketCard({ ticket: t }: { ticket: TicketRow }) {
  const qc = useQueryClient();
  const toast = useToast();
  // Collapsed by default — expanding shows the conversation thread
  // (which owns replies) plus the status/priority controls.
  const [expanded, setExpanded] = useState(false);
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
      if (Object.keys(body).length > 0) {
        await updateTicket(t.id, body);
        void qc.invalidateQueries({ queryKey: ["tickets"] });
        toast({ message: "Ticket updated.", tone: "success" });
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update ticket.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <div className={styles.cardInner}>
        <div className={styles.headerRow}>
          <div className={styles.headerLeft}>
            <div className={styles.titleRow}>
              <span className={styles.subject}>{t.subject}</span>
              <Pill tone={TICKET_STATUS_TONES[t.status] ?? "neutral"}>
                {t.status.replace("_", " ")}
              </Pill>
              {t.priority && (
                <Pill tone={PRIORITY_TONES[t.priority] ?? "neutral"}>
                  {t.priority}
                </Pill>
              )}
            </div>
            <div className={styles.meta}>
              {t.submitted_by} · {t.store_name || `Store #${t.store_id}`} · {fmtDateTime(t.created_at)}
              {" · "}
              <span className={styles.metaCat}>{t.category}</span>
            </div>
          </div>
          <Button tone="secondary" size="sm" onClick={() => setExpanded((v) => !v)}>
            {expanded ? "Collapse" : "Open conversation"}
          </Button>
        </div>

        {!expanded && <p className={styles.body}>{t.body}</p>}

        {error && <Alert tone="error">{error}</Alert>}

        {expanded && (
          <>
            {/* Replies live in the thread (staff replies dual-write
                the legacy admin_reply column server-side). */}
            <TicketThread ticket={t} viewerKind="staff" />

            <form onSubmit={onSave} className={styles.formInner}>
              <div className={styles.formGrid}>
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
                <div className={styles.formActions}>
                  <Button
                    type="submit" tone="secondary" busy={busy}
                    disabled={
                      busy ||
                      (newStatus === t.status &&
                        (newPriority || "") === (t.priority || ""))
                    }
                  >
                    {busy ? "Saving…" : "Update status"}
                  </Button>
                </div>
              </div>
            </form>
          </>
        )}
      </div>
    </Card>
  );
}
