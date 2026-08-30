import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";
import { formatDate } from "../lib/datetime";
import {
  Breadcrumbs, Card, EmptyState, ErrorState, Input,
  Loading, Pager, PageHeader, PageShell, Pill, Section,
  Select, Table, tdStyle, thStyle, type PillTone,
} from "../components/ui";
import styles from "./SuperadminEmailLog.module.css";

interface EmailEventRow {
  id: number;
  to_addr: string;
  event_type: string;
  bounce_type: string;
  message_id: string;
  created_at: string;
}

interface SuppressedRow {
  user_id: number;
  username: string;
  email: string;
  bounced_at: string;
}

interface EmailLogData {
  rows: EmailEventRow[];
  total: number;
  page: number;
  total_pages: number;
  suppressed: SuppressedRow[];
}

const EVENT_TYPES = [
  { value: "", label: "All events" },
  { value: "email.sent", label: "Sent" },
  { value: "email.delivered", label: "Delivered" },
  { value: "email.bounced", label: "Bounced" },
  { value: "email.complained", label: "Complained" },
  { value: "email.opened", label: "Opened" },
  { value: "email.clicked", label: "Clicked" },
];

const EVENT_TONES: Record<string, PillTone> = {
  "email.sent": "neutral",
  "email.delivered": "success",
  "email.bounced": "negative",
  "email.complained": "negative",
  "email.opened": "accent",
  "email.clicked": "accent",
  "email.delivery_delayed": "warning",
};

function useEmailLog(opts: { q?: string; event_type?: string; page?: number }) {
  const identity = getCurrentIdentity();
  const params = new URLSearchParams();
  if (opts.q) params.set("q", opts.q);
  if (opts.event_type) params.set("event_type", opts.event_type);
  if (opts.page && opts.page > 1) params.set("page", String(opts.page));
  const qs = params.toString() ? `?${params}` : "";
  return useQuery<EmailLogData>({
    enabled: identity?.role === "superadmin",
    queryKey: ["superadmin", "email-log", opts.q, opts.event_type, opts.page],
    queryFn: () => api<EmailLogData>(`/api/v2/superadmin/email-log${qs}`),
  });
}

export default function SuperadminEmailLog() {
  const [q, setQ] = useState("");
  const [eventType, setEventType] = useState("");
  const [page, setPage] = useState(1);
  const { data, isLoading, isError, error, refetch } =
    useEmailLog({ q: q || undefined, event_type: eventType || undefined, page });

  return (
    <PageShell gap="1.25rem">
      <Breadcrumbs crumbs={[{ label: "Platform" }, { label: "Email log" }]} />
      <PageHeader
        title="Email Log"
        subtitle={data ? `${data.total.toLocaleString()} events` : "—"}
        actions={(
          <div className={styles.filterRow}>
            <Input
              type="search"
              value={q}
              placeholder="Search email address…"
              onChange={(e) => { setQ(e.target.value); setPage(1); }}
              className={styles.searchInput}
            />
            <Select
              value={eventType}
              onChange={(e) => { setEventType(e.target.value); setPage(1); }}
            >
              {EVENT_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </Select>
          </div>
        )}
      />

      {isLoading && <Loading />}
      {isError && (
        <ErrorState
          message={error instanceof Error ? error.message : "Could not load email log"}
          onRetry={() => { void refetch(); }}
        />
      )}

      {data && (
        <>
          <Card>
            {data.rows.length === 0 && !isLoading ? (
              <EmptyState title="No email events match the filters." />
            ) : (
              <Table>
                <thead>
                  <tr>
                    <th style={thStyle}>Recipient</th>
                    <th style={thStyle}>Event</th>
                    <th style={thStyle}>Bounce</th>
                    <th style={thStyle}>Message ID</th>
                    <th style={thStyle}>Time</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((e) => (
                    <tr key={e.id}>
                      <td style={tdStyle}>{e.to_addr}</td>
                      <td style={tdStyle}>
                        <Pill tone={EVENT_TONES[e.event_type] ?? "neutral"}>
                          {e.event_type.replace("email.", "")}
                        </Pill>
                      </td>
                      <td style={tdStyle}>
                        {e.bounce_type ? (
                          <Pill tone="negative">{e.bounce_type}</Pill>
                        ) : (
                          <span className={styles.monoMuted}>—</span>
                        )}
                      </td>
                      <td style={tdStyle}>
                        <span className={styles.monoMuted}>
                          {e.message_id ? e.message_id.slice(0, 16) + "…" : "—"}
                        </span>
                      </td>
                      <td style={tdStyle}>
                        <span className={styles.monoMuted}>
                          {e.created_at.slice(0, 16).replace("T", " ")}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Card>

          {data.total_pages > 1 && (
            <Pager page={data.page} totalPages={data.total_pages} onPage={setPage} />
          )}

          {data.suppressed.length > 0 && (
            <Section title={`Suppressed addresses (${data.suppressed.length})`}>
              <Card>
                <div className={styles.suppressedList}>
                  {data.suppressed.map((s) => (
                    <div key={s.user_id} className={styles.suppressedRow}>
                      <div>
                        <strong>{s.username}</strong>
                        <span className={styles.monoMuted}> · {s.email}</span>
                      </div>
                      <span className={styles.monoMuted}>
                        Bounced {formatDate(s.bounced_at)}
                      </span>
                    </div>
                  ))}
                </div>
              </Card>
            </Section>
          )}
        </>
      )}
    </PageShell>
  );
}
