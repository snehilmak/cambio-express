import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { createTicket, TICKET_STATUS_TONES, useMyTickets, type TicketRow } from "../api/support";
import { fmtDateTime } from "../lib/formatters";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import {
  Alert, Breadcrumbs, Button, Card, EmptyState, ErrorState, Field,
  Input, Loading, PageHeader, PageShell, Pill, Section, Select,
  Table, tdStyle, Textarea, thStyle,
} from "../components/ui";
import styles from "./SupportTickets.module.css";

const CATEGORIES = [
  { value: "bug", label: "Bug report" },
  { value: "feature", label: "Feature request" },
  { value: "question", label: "Question" },
  { value: "feedback", label: "General feedback" },
];



export default function SupportTickets() {
  const identity = getCurrentIdentity();
  if (identity?.role === "superadmin") {
    return <Navigate to="/superadmin/tickets" replace />;
  }
  return <SupportTicketsInner />;
}

function SupportTicketsInner() {
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
          <Button size="sm" onClick={() => setShowForm((v) => !v)}>
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
              <div className={styles.formGrid}>
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
              <div className={styles.formActions}>
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
            <Table>
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
            </Table>
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
        className={styles.clickableRow}
      >
        <td style={tdStyle}>{t.subject}</td>
        <td style={tdStyle}>{CATEGORIES.find((c) => c.value === t.category)?.label ?? t.category}</td>
        <td style={tdStyle}>
          <Pill tone={TICKET_STATUS_TONES[t.status] ?? "neutral"}>
            {t.status.replace("_", " ")}
          </Pill>
        </td>
        <td style={tdStyle}>{fmtDateTime(t.created_at)}</td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={4} className={styles.expandedBody}>
            <p className={styles.ticketBody}>{t.body}</p>
            {t.admin_reply && (
              <div className={styles.replyBox}>
                <div className={styles.replyMeta}>
                  Reply from {t.replied_by} · {t.replied_at ? fmtDateTime(t.replied_at) : ""}
                </div>
                <p className={styles.replyBody}>{t.admin_reply}</p>
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

