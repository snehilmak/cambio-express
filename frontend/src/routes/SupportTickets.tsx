import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { createTicket, useMyTickets, type TicketRow } from "../api/support";
import { ApiError } from "../lib/api";
import {
  Alert, Breadcrumbs, Button, Card, EmptyState, ErrorState, Field,
  Input, Loading, PageHeader, PageShell, Pill, Section, Select,
  Textarea,
} from "../components/ui";

const CATEGORIES = [
  { value: "bug", label: "Bug report" },
  { value: "feature", label: "Feature request" },
  { value: "question", label: "Question" },
  { value: "feedback", label: "General feedback" },
];

const STATUS_TONES: Record<string, "neutral" | "accent" | "warning" | "success" | "negative"> = {
  open: "accent",
  in_progress: "warning",
  resolved: "success",
  closed: "neutral",
};

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short", day: "numeric", year: "numeric",
    });
  } catch { return iso; }
}

export default function SupportTickets() {
  const tickets = useMyTickets();
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [category, setCategory] = useState("question");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!subject.trim() || !body.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await createTicket({ category, subject: subject.trim(), body: body.trim() });
      setSubject("");
      setBody("");
      setShowForm(false);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 4000);
      void qc.invalidateQueries({ queryKey: ["tickets"] });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit ticket.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageShell maxWidth="56rem">
      <Breadcrumbs crumbs={[
        { label: "Account", to: "/settings" },
        { label: "Support tickets" },
      ]} />
      <PageHeader
        title="Support tickets"
        subtitle="Report bugs, request features, or ask questions."
        actions={
          <Button onClick={() => setShowForm((v) => !v)}>
            {showForm ? "Cancel" : "+ New ticket"}
          </Button>
        }
      />

      {success && <Alert tone="success">Ticket submitted — we'll get back to you soon.</Alert>}
      {error && <Alert tone="error">{error}</Alert>}

      {showForm && (
        <Card>
          <Section title="Submit a ticket">
            <form onSubmit={onSubmit} style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                <Field label="Category">
                  <Select value={category} onChange={(e) => setCategory(e.target.value)}>
                    {CATEGORIES.map((c) => (
                      <option key={c.value} value={c.value}>{c.label}</option>
                    ))}
                  </Select>
                </Field>
                <Field label="Subject">
                  <Input
                    type="text"
                    value={subject}
                    onChange={(e) => setSubject(e.target.value)}
                    placeholder="Brief summary"
                    maxLength={200}
                    required
                  />
                </Field>
              </div>
              <Field label="Description">
                <Textarea
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  placeholder="Describe the issue, idea, or question in detail…"
                  rows={5}
                  maxLength={5000}
                  required
                />
              </Field>
              <div style={{ display: "flex", justifyContent: "flex-end" }}>
                <Button type="submit" busy={busy} disabled={busy || !subject.trim() || !body.trim()}>
                  {busy ? "Submitting…" : "Submit ticket"}
                </Button>
              </div>
            </form>
          </Section>
        </Card>
      )}

      {tickets.isLoading && <Loading />}
      {tickets.isError && (
        <ErrorState
          message="Could not load tickets."
          onRetry={() => { void tickets.refetch(); }}
        />
      )}

      {tickets.data && tickets.data.tickets.length === 0 && !showForm && (
        <EmptyState title="No tickets yet" body='Click "+ New ticket" to submit your first one.' />
      )}

      {tickets.data && tickets.data.tickets.length > 0 && (
        <Card>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={thStyle}>Subject</th>
                  <th style={thStyle}>Category</th>
                  <th style={thStyle}>Status</th>
                  <th style={thStyle}>Created</th>
                </tr>
              </thead>
              <tbody>
                {tickets.data.tickets.map((t) => (
                  <TicketRowView key={t.id} ticket={t} />
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </PageShell>
  );
}

function TicketRowView({ ticket: t }: { ticket: TicketRow }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <>
      <tr
        onClick={() => setExpanded((v) => !v)}
        style={{ cursor: "pointer", borderBottom: "1px solid var(--db-border, #262626)" }}
      >
        <td style={tdStyle}>{t.subject}</td>
        <td style={tdStyle}>{CATEGORIES.find((c) => c.value === t.category)?.label ?? t.category}</td>
        <td style={tdStyle}>
          <Pill tone={STATUS_TONES[t.status] ?? "neutral"}>
            {t.status.replace("_", " ")}
          </Pill>
        </td>
        <td style={tdStyle}>{formatDate(t.created_at)}</td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={4} style={{ padding: "1rem 1.25rem", background: "var(--db-surface-2, #141414)" }}>
            <p style={{ margin: "0 0 0.5rem", whiteSpace: "pre-wrap" }}>{t.body}</p>
            {t.admin_reply && (
              <div style={{
                marginTop: "0.75rem",
                padding: "0.75rem 1rem",
                background: "var(--db-surface, #0a0a0a)",
                border: "1px solid var(--db-border, #262626)",
                borderRadius: "0.5rem",
              }}>
                <div style={{ fontSize: "0.78rem", color: "var(--db-text-muted)", marginBottom: "0.35rem" }}>
                  Reply from {t.replied_by} · {t.replied_at ? formatDate(t.replied_at) : ""}
                </div>
                <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{t.admin_reply}</p>
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

const thStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "0.75rem 1.25rem",
  fontSize: "0.72rem",
  fontWeight: 700,
  textTransform: "uppercase",
  letterSpacing: "0.06em",
  color: "var(--db-text-muted)",
  borderBottom: "1px solid var(--db-border, #262626)",
};

const tdStyle: React.CSSProperties = {
  padding: "0.75rem 1.25rem",
  fontSize: "0.88rem",
};
