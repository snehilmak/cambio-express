import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  postTicketMessage, reopenTicket, useTicketMessages,
  type TicketRow,
} from "../api/support";
import { fmtDateTime } from "../lib/formatters";
import { ApiError } from "../lib/api";
import { Alert, Button, Loading, Textarea } from "./ui";
import styles from "./TicketThread.module.css";

/** Chat-style conversation thread for one support ticket, shared by
 *  the store-side Support page and the superadmin ticket queue.
 *
 *  - The original ticket body renders as the first bubble.
 *  - Replies are allowed while the ticket is open / in progress /
 *    resolved; a CLOSED ticket swaps the reply box for a single
 *    "Reopen ticket" button.
 *  - `viewerKind` decides which bubbles read as "mine" (right,
 *    accent): "user" on the store side, "staff" on the platform side.
 */
export function TicketThread({
  ticket, viewerKind,
}: {
  ticket: TicketRow;
  viewerKind: "user" | "staff";
}) {
  const qc = useQueryClient();
  const thread = useTicketMessages(ticket.id, true);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const closed = ticket.status === "closed";

  async function refresh() {
    // Prefix-matches the list, detail, and thread queries.
    await qc.invalidateQueries({ queryKey: ["tickets"] });
  }

  async function onSend() {
    const text = draft.trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    try {
      await postTicketMessage(ticket.id, text);
      setDraft("");
      await refresh();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not send the reply.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function onReopen() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await reopenTicket(ticket.id);
      await refresh();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not reopen the ticket.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.thread}>
      <Bubble
        mine={viewerKind === "user"}
        author={ticket.submitted_by}
        at={ticket.created_at}
        body={ticket.body}
      />
      {thread.isLoading && <Loading />}
      {(thread.data?.messages ?? []).map((m) => (
        <Bubble
          key={m.id}
          mine={m.author_kind === viewerKind}
          staff={m.author_kind === "staff"}
          author={m.author_name || (m.author_kind === "staff" ? "Support" : "")}
          at={m.created_at}
          body={m.body}
        />
      ))}

      {error && <Alert tone="error">{error}</Alert>}

      {closed ? (
        <div className={styles.reopenRow}>
          <span className={styles.closedNote}>
            This ticket is closed. Still having the issue?
          </span>
          <Button
            type="button" tone="secondary" size="sm"
            busy={busy} disabled={busy} onClick={onReopen}
          >
            Reopen ticket
          </Button>
        </div>
      ) : (
        <div className={styles.replyRow}>
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Write a reply…"
            rows={2}
            maxLength={5000}
            disabled={busy}
          />
          <Button
            type="button" size="sm"
            busy={busy} disabled={busy || !draft.trim()}
            onClick={onSend}
          >
            Send
          </Button>
        </div>
      )}
    </div>
  );
}

function Bubble({
  mine, staff, author, at, body,
}: {
  mine: boolean;
  staff?: boolean;
  author: string;
  at: string;
  body: string;
}) {
  const cls = [
    styles.bubble,
    mine ? styles.bubbleMine : styles.bubbleTheirs,
    staff ? styles.bubbleStaff : "",
  ].filter(Boolean).join(" ");
  return (
    <div className={mine ? styles.rowMine : styles.rowTheirs}>
      <div className={cls}>
        <div className={styles.bubbleMeta}>
          {author || "—"} · {at ? fmtDateTime(at) : ""}
        </div>
        <p className={styles.bubbleBody}>{body}</p>
      </div>
    </div>
  );
}
