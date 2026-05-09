import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  generateOwnerConnectCode, revokeOwnerConnectCode, useOwnerConnectCodes,
  type OwnerConnectCodeRow,
} from "../api/owner";
import { ApiError } from "../lib/api";
import { getCurrentIdentity } from "../lib/auth";

// /app/owner/connect — owner mints 8-character invite codes that
// store admins redeem on their settings page to link a store to
// the owner's umbrella. v1 ships:
//   - one-active-code semantics: generating revokes the current
//     active code first, mirroring the legacy Flask behavior
//   - copy-to-clipboard for the active code
//   - revoke action for the active code
//   - last-10 redeemed history
//
// The 7-day TTL is enforced server-side; we just render
// `expires_at`. Backed by /api/v2/owner/connect-codes.

export default function OwnerConnect() {
  const identity = getCurrentIdentity();
  const queryClient = useQueryClient();
  const { data, isLoading, isError, error } = useOwnerConnectCodes();

  const [busy, setBusy] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // The legacy page shows the FIRST unused-unrevoked-unexpired
  // code as the "active" one; we narrow to the same shape.
  const active = useMemo<OwnerConnectCodeRow | null>(() => {
    if (!data) return null;
    return data.rows.find(
      (r) => !r.is_redeemed && !r.is_revoked && !r.is_expired,
    ) ?? null;
  }, [data]);

  const redeemed = useMemo<OwnerConnectCodeRow[]>(() => {
    if (!data) return [];
    return data.rows.filter((r) => r.is_redeemed).slice(0, 10);
  }, [data]);

  if (identity?.role !== "owner") {
    return (
      <main style={pageStyle}>
        <h1 style={titleStyle}>Connect a Store</h1>
        <p style={mutedStyle}>
          Only owners can mint store-connect codes.
        </p>
      </main>
    );
  }

  async function handleGenerate() {
    if (!confirm(
      active
        ? "Generate a new code? This will revoke the current one."
        : "Generate a new invite code? It expires in 7 days.",
    )) return;
    setBusy(true); setServerError(null);
    try {
      // Legacy contract: generating revokes any active code first.
      // The new endpoint does NOT auto-revoke (clean separation),
      // so we revoke client-side before minting.
      if (active) {
        await revokeOwnerConnectCode(active.id);
      }
      await generateOwnerConnectCode();
      queryClient.invalidateQueries({ queryKey: ["owner", "connect-codes"] });
    } catch (err) {
      setServerError(
        err instanceof ApiError ? err.message : "Could not generate code.",
      );
    } finally { setBusy(false); }
  }

  async function handleRevoke() {
    if (!active) return;
    if (!confirm(
      "Revoke this code? The store admin won't be able to redeem it. " +
      "You can generate a new one right after.",
    )) return;
    setBusy(true); setServerError(null);
    try {
      await revokeOwnerConnectCode(active.id);
      queryClient.invalidateQueries({ queryKey: ["owner", "connect-codes"] });
    } catch (err) {
      setServerError(
        err instanceof ApiError ? err.message : "Could not revoke code.",
      );
    } finally { setBusy(false); }
  }

  function handleCopy() {
    if (!active) return;
    if (navigator.clipboard) {
      navigator.clipboard.writeText(active.code);
    } else {
      const ta = document.createElement("textarea");
      ta.value = active.code; document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); } finally { ta.remove(); }
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  }

  return (
    <main style={pageStyle}>
      <header style={{ marginBottom: "1rem" }}>
        <h1 style={titleStyle}>Connect a Store</h1>
      </header>

      {serverError && <div style={alertErrorStyle}>{serverError}</div>}

      <section style={cardStyle}>
        <h2 style={cardTitleStyle}>Active invite code</h2>
        {isLoading && <p style={mutedStyle}>Loading…</p>}
        {isError && (
          <p style={errorStyle}>
            Couldn't load codes.
            {error instanceof Error ? ` ${error.message}` : ""}
          </p>
        )}
        {!isLoading && !active && (
          <>
            <p style={leadStyle}>
              No active code. Generate one to give to a store admin —
              they'll enter it on their store's Settings → Owner Access
              page to link their store to your umbrella. Codes are
              valid for 7 days.
            </p>
            <button
              type="button" onClick={handleGenerate}
              disabled={busy} style={btnPrimaryStyle}
            >
              {busy ? "Generating…" : "Generate Invite Code"}
            </button>
          </>
        )}
        {active && (
          <>
            <p style={leadStyle}>
              Share this code with the store admin you want to connect.
              They enter it on their store's Settings → Owner Access
              page. Code expires on{" "}
              <strong>{formatDate(active.expires_at)}</strong>.
            </p>
            <div style={codeRowStyle}>
              <input
                type="text" readOnly value={active.code}
                style={codeInputStyle}
                onFocus={(e) => e.currentTarget.select()}
              />
              <button
                type="button" onClick={handleCopy} style={btnOutlineStyle}
              >
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
            <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
              <button
                type="button" onClick={handleRevoke}
                disabled={busy} style={btnOutlineStyle}
              >
                Revoke
              </button>
              <button
                type="button" onClick={handleGenerate}
                disabled={busy} style={btnOutlineStyle}
              >
                {busy ? "Generating…" : "Generate New Code"}
              </button>
            </div>
          </>
        )}
      </section>

      <section style={{ ...cardStyle, marginTop: "1rem" }}>
        <div style={{ display: "flex", alignItems: "baseline" }}>
          <h2 style={{ ...cardTitleStyle, flex: 1 }}>Recently redeemed</h2>
          <span style={{ color: "var(--db-text-muted, #a3a3a3)", fontSize: "0.78rem" }}>
            Last 10
          </span>
        </div>
        {redeemed.length > 0 ? (
          <table style={tableStyle}>
            <thead>
              <tr>
                <th style={thStyle}>Code</th>
                <th style={thStyle}>Store</th>
                <th style={thStyle}>Redeemed</th>
              </tr>
            </thead>
            <tbody>
              {redeemed.map((r) => (
                <tr key={r.id}>
                  <td style={{ ...cellStyle, ...mono }}>{r.code}</td>
                  <td style={cellStyle}>{r.used_by_store_name || "—"}</td>
                  <td style={{ ...cellStyle, color: "var(--db-text-muted, #a3a3a3)" }}>
                    {formatDate(r.used_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p style={emptyStyle}>
            No codes redeemed yet. Stores you've connected will show
            up here.
          </p>
        )}
      </section>

      <p style={fineStyle}>
        To disconnect a store, head to your{" "}
        <a href="/app/dashboard" style={inlineLinkStyle}>Dashboard</a>{" "}
        or{" "}
        <a href="/app/owner/locations" style={inlineLinkStyle}>Locations</a>{" "}
        page — only the owner can break the link, store admins can't.
      </p>
    </main>
  );
}


function formatDate(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const month = d.toLocaleString("en-US", { month: "short", timeZone: "UTC" });
  const day   = String(d.getUTCDate()).padStart(2, "0");
  const yr    = d.getUTCFullYear();
  return `${month} ${day}, ${yr}`;
}


const pageStyle: React.CSSProperties = {
  flex: 1, display: "flex", flexDirection: "column",
  padding: "2rem 1.5rem", maxWidth: "40rem",
  margin: "0 auto", width: "100%", boxSizing: "border-box",
};

const titleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "clamp(1.5rem, 3.5vw, 2rem)",
  fontWeight: 600, margin: 0,
};

const cardStyle: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem", padding: "1.25rem",
};

const cardTitleStyle: React.CSSProperties = {
  margin: "0 0 0.6rem", fontSize: "1rem", fontWeight: 600,
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
};

const leadStyle: React.CSSProperties = {
  margin: "0 0 1rem", color: "var(--db-text-muted, #a3a3a3)",
  fontSize: "0.85rem", lineHeight: 1.55,
};

const codeRowStyle: React.CSSProperties = {
  display: "flex", gap: "0.6rem", alignItems: "center",
  marginBottom: "0.85rem",
};

const codeInputStyle: React.CSSProperties = {
  flex: 1,
  fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
  fontSize: "1.4rem", letterSpacing: "0.25em",
  fontWeight: 600, textAlign: "center",
  padding: "0.65rem 0.75rem",
  background: "var(--db-bg-input, #0d0d0d)",
  color: "var(--db-text, #e5e5e5)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem",
};

const btnPrimaryStyle: React.CSSProperties = {
  padding: "0.65rem 1.1rem",
  fontWeight: 600, fontSize: "0.92rem",
  background: "var(--db-neon, #3fff00)",
  color: "var(--db-neon-ink, #001a0f)",
  border: "none", borderRadius: "0.5rem",
  cursor: "pointer",
};

const btnOutlineStyle: React.CSSProperties = {
  padding: "0.55rem 0.95rem",
  fontWeight: 500, fontSize: "0.85rem",
  background: "transparent",
  color: "var(--db-text, #e5e5e5)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem",
  cursor: "pointer",
};

const tableStyle: React.CSSProperties = {
  width: "100%", borderCollapse: "collapse",
  fontSize: "0.88rem",
};

const thStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "0.55rem 0.7rem",
  color: "var(--db-text-muted, #a3a3a3)",
  fontWeight: 500,
  fontSize: "0.72rem",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  borderBottom: "1px solid var(--db-border, #262626)",
};

const cellStyle: React.CSSProperties = {
  padding: "0.6rem 0.7rem",
  borderBottom: "1px solid var(--db-border-subtle, #1f1f1f)",
};

const mono: React.CSSProperties = {
  fontFamily: "var(--db-font-mono, 'JetBrains Mono', monospace)",
};

const emptyStyle: React.CSSProperties = {
  margin: "0", color: "var(--db-text-muted, #a3a3a3)",
  fontSize: "0.88rem",
};

const fineStyle: React.CSSProperties = {
  marginTop: "1rem", color: "var(--db-text-muted, #a3a3a3)",
  fontSize: "0.78rem", lineHeight: 1.55,
};

const inlineLinkStyle: React.CSSProperties = {
  color: "var(--db-neon, #3fff00)",
  textDecoration: "none",
};

const mutedStyle: React.CSSProperties = {
  marginTop: "1rem", color: "var(--db-text-muted, #a3a3a3)",
};

const errorStyle: React.CSSProperties = {
  marginTop: "1rem", color: "var(--db-negative, #ff4d6d)",
};

const alertErrorStyle: React.CSSProperties = {
  padding: "0.6rem 0.85rem",
  marginBottom: "1rem",
  background: "rgba(255,77,109,0.08)",
  border: "1px solid rgba(255,77,109,0.3)",
  borderRadius: "0.5rem",
  color: "var(--db-negative, #ff4d6d)",
  fontSize: "0.88rem",
};
