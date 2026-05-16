import { Fragment, useEffect, useState } from "react";
import type { ReactNode } from "react";

import { useActiveAnnouncements } from "../api/announcements";
import type { ActiveAnnouncementRow } from "../api/announcements";

// Global banner zone for /api/v2/announcements/active. Renders
// inside <AppShell> above the routed page content so every authed
// surface shows the same notice stack.
//
// Dismissal is local-only — clicking the close button writes the
// banner id into localStorage under DISMISS_KEY. We don't round-
// trip to the server because (a) the banner state is per-device
// (a cashier dismissing on the iPad shouldn't hide it on the back-
// office laptop) and (b) it keeps the endpoint stateless. Re-
// posting the same banner gets a new id, so superadmins can re-
// surface a notice by re-posting if dismissal patterns suggest
// users missed it.

const DISMISS_KEY = "dinerobook.announcements.dismissed";

function loadDismissed(): Set<number> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = window.localStorage.getItem(DISMISS_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.filter((n): n is number => typeof n === "number"));
  } catch {
    return new Set();
  }
}

function saveDismissed(s: Set<number>): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      DISMISS_KEY, JSON.stringify(Array.from(s)),
    );
  } catch {
    /* quota / serialization errors silently ignored — dismissal
       is a UX nicety, not a correctness requirement. */
  }
}

// Linkify bare http(s):// URLs without pulling in a markdown
// parser — the only "rich text" we want in banners is clickable
// links ("click here: https://docs.dinerobook.com/migration"),
// and matching whole http(s) tokens covers ~100% of that need.
// Trailing sentence punctuation (.,;:!?)) is stripped from the
// link so "see https://x.com/post." doesn't include the period.
// React renders the text/Anchor children as escaped string nodes,
// so there's no HTML-injection surface to worry about.

const URL_REGEX = /\bhttps?:\/\/[^\s<]+/gi;

function renderWithLinks(message: string): ReactNode {
  const nodes: ReactNode[] = [];
  let cursor = 0;
  for (const match of message.matchAll(URL_REGEX)) {
    const start = match.index ?? 0;
    if (start > cursor) {
      nodes.push(
        <Fragment key={`t-${cursor}`}>{message.slice(cursor, start)}</Fragment>,
      );
    }
    let url = match[0];
    let trailing = "";
    while (url.length > 0 && ".,;:!?)".includes(url[url.length - 1] ?? "")) {
      trailing = url[url.length - 1] + trailing;
      url = url.slice(0, -1);
    }
    nodes.push(
      <a
        key={`u-${start}`}
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        style={{ color: "inherit", textDecoration: "underline" }}
      >
        {url}
      </a>,
    );
    if (trailing) {
      nodes.push(
        <Fragment key={`tp-${start}`}>{trailing}</Fragment>,
      );
    }
    cursor = start + match[0].length;
  }
  if (cursor < message.length) {
    nodes.push(
      <Fragment key={`t-${cursor}-end`}>{message.slice(cursor)}</Fragment>,
    );
  }
  return nodes.length > 0 ? nodes : message;
}

const palette: Record<string, { bg: string; border: string; fg: string }> = {
  info:    { bg: "rgba(99,166,255,0.12)", border: "rgba(99,166,255,0.35)", fg: "#9ec5ff" },
  warning: { bg: "rgba(255,184,0,0.12)",  border: "rgba(255,184,0,0.35)",  fg: "#ffd766" },
  error:   { bg: "rgba(255,59,48,0.12)",  border: "rgba(255,59,48,0.35)",  fg: "#ff8a82" },
  success: { bg: "rgba(63,255,0,0.10)",   border: "rgba(63,255,0,0.30)",   fg: "#7cff5c" },
};

export function AnnouncementBanner() {
  const { data } = useActiveAnnouncements();
  const [dismissed, setDismissed] = useState<Set<number>>(loadDismissed);

  // The localStorage read is synchronous + cheap; nothing else
  // needs to fire on mount. Keeps the component a pure render of
  // server-state ∩ local-dismissal.
  useEffect(() => {
    saveDismissed(dismissed);
  }, [dismissed]);

  const rows = (data?.rows ?? []).filter((r) => !dismissed.has(r.id));
  if (rows.length === 0) return null;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "0.4rem",
        padding: "0.6rem 1rem 0",
      }}
    >
      {rows.map((row) => (
        <BannerRow
          key={row.id}
          row={row}
          onDismiss={() =>
            setDismissed((prev) => {
              const next = new Set(prev);
              next.add(row.id);
              return next;
            })
          }
        />
      ))}
    </div>
  );
}

function BannerRow({
  row, onDismiss,
}: {
  row: ActiveAnnouncementRow;
  onDismiss: () => void;
}) {
  const c = palette[row.level] ?? palette.info;
  return (
    <div
      role={row.level === "error" || row.level === "warning" ? "alert" : "status"}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.75rem",
        padding: "0.55rem 0.85rem",
        background: c.bg,
        border: `1px solid ${c.border}`,
        borderRadius: "0.5rem",
        color: c.fg,
        fontSize: "0.88rem",
        lineHeight: 1.45,
      }}
    >
      <span style={{ flex: 1, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
        {renderWithLinks(row.message)}
      </span>
      <button
        type="button"
        aria-label="Dismiss announcement"
        onClick={onDismiss}
        style={{
          appearance: "none",
          background: "transparent",
          border: "none",
          color: c.fg,
          cursor: "pointer",
          fontSize: "1rem",
          lineHeight: 1,
          padding: "0.25rem 0.4rem",
          borderRadius: "0.3rem",
          opacity: 0.7,
        }}
      >
        ×
      </button>
    </div>
  );
}
