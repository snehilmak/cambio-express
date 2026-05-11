import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  useCustomerSearch,
  type CustomerRow,
} from "../api/customers";
import { getCurrentIdentity } from "../lib/auth";

// Customer search at /app/customers. Live-search box; results
// split into "exact matches" (phone/full-name match) and
// "suggestions" (fuzzy near-misses) — same shape the legacy
// /api/customers/search returns.
//
// Search query lives in the URL query string so refresh + back
// preserve state, just like the transfers list.
export default function Customers() {
  const identity = getCurrentIdentity();
  const [searchParams, setSearchParams] = useSearchParams();
  const q = searchParams.get("q") ?? "";

  const [draft, setDraft] = useState(q);
  // 300ms debounce + 2-char minimum (CLAUDE.md "Table search UX").
  useEffect(() => {
    if (draft === q) return;
    const id = window.setTimeout(() => {
      const next = draft.length === 0 || draft.length >= 2 ? draft : q;
      const params = new URLSearchParams(searchParams);
      if (next) params.set("q", next);
      else params.delete("q");
      setSearchParams(params, { replace: true });
    }, 300);
    return () => window.clearTimeout(id);
  }, [draft, q, searchParams, setSearchParams]);
  // eslint-disable-next-line react-hooks/set-state-in-effect -- mirror URL search param into local debounced input when URL changes externally (browser back, link arrival)
  useEffect(() => { setDraft(q); }, [q]);

  const { data, isFetching, isError, error } = useCustomerSearch(q);

  if (identity?.store_id == null) {
    return (
      <main style={pageStyle}>
        <h1 style={titleStyle}>Customers</h1>
        <p style={emptyStyle}>
          Sign in as a store admin to search this store's customers.
        </p>
      </main>
    );
  }

  return (
    <main style={pageStyle}>
      <header style={{ marginBottom: "1.5rem" }}>
        <h1 style={titleStyle}>Customers</h1>
        <p
          style={{
            margin: "0.35rem 0 0",
            color: "var(--db-text-muted, #a3a3a3)",
          }}
        >
          {q.length >= 2
            ? data
              ? `${data.matches.length} match${
                  data.matches.length === 1 ? "" : "es"
                } · ${data.suggestions.length} suggestion${
                  data.suggestions.length === 1 ? "" : "s"
                }`
              : "Searching…"
            : "Type at least 2 characters to search."}
        </p>
      </header>

      <section style={{ ...cardStyle, marginBottom: "1rem" }}>
        <label
          style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}
        >
          <span
            style={{
              fontSize: "0.78rem",
              color: "var(--db-text-muted, #a3a3a3)",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
            }}
          >
            Search
          </span>
          <input
            type="search"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Name, phone, …"
            style={inputStyle}
          />
        </label>
        {isFetching && (
          <p
            style={{
              margin: "0.5rem 0 0",
              fontSize: "0.85rem",
              color: "var(--db-text-muted, #a3a3a3)",
            }}
          >
            Searching…
          </p>
        )}
      </section>

      {isError && (
        <p style={{ ...emptyStyle, color: "var(--db-negative, #ff3b30)" }}>
          {error instanceof Error ? error.message : "Search failed"}
        </p>
      )}

      {data && data.matches.length > 0 && (
        <Section title="Matches">
          <CustomerTable rows={data.matches} />
        </Section>
      )}

      {data && data.suggestions.length > 0 && (
        <Section title="Suggestions">
          <CustomerTable rows={data.suggestions} />
        </Section>
      )}

      {data &&
        data.matches.length === 0 &&
        data.suggestions.length === 0 &&
        q.length >= 2 &&
        !isFetching && (
          <p style={emptyStyle}>No customers match "{q}".</p>
        )}
    </main>
  );
}

function Section({
  title, children,
}: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ ...cardStyle, marginBottom: "1rem" }}>
      <h2
        style={{
          fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
          fontSize: "0.95rem",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          color: "var(--db-text-muted, #a3a3a3)",
          margin: "0 0 1rem",
        }}
      >
        {title}
      </h2>
      {children}
    </section>
  );
}

function CustomerTable({ rows }: { rows: CustomerRow[] }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table
        style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.92rem" }}
      >
        <thead>
          <tr>
            {["Name", "Phone", "DOB", "Address", "Home store"].map((h) => (
              <th key={h} style={thStyle}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.id}>
              <td style={cellStyle}>
                <strong>{c.full_name}</strong>
              </td>
              <td style={cellStyle}>
                <span
                  style={{
                    fontFamily:
                      "var(--db-font-mono, 'JetBrains Mono', monospace)",
                    fontSize: "0.9rem",
                  }}
                >
                  {c.phone_country} {c.phone_number || "—"}
                </span>
              </td>
              <td style={cellStyle}>
                <span
                  style={{
                    fontFamily:
                      "var(--db-font-mono, 'JetBrains Mono', monospace)",
                    fontSize: "0.85rem",
                    color: "var(--db-text-muted, #a3a3a3)",
                  }}
                >
                  {c.dob || "—"}
                </span>
              </td>
              <td style={cellStyle}>{c.address || "—"}</td>
              <td style={cellStyle}>
                {c.home_store_name ? (
                  <span style={{ color: "var(--db-text-muted, #a3a3a3)" }}>
                    {c.home_store_name}
                  </span>
                ) : (
                  <span style={{ color: "var(--db-text-muted, #a3a3a3)" }}>
                    (this store)
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const pageStyle: React.CSSProperties = {
  flex: 1,
  display: "flex",
  flexDirection: "column",
  padding: "2.5rem 1.5rem",
  maxWidth: "70rem",
  margin: "0 auto",
  width: "100%",
  boxSizing: "border-box",
};

const titleStyle: React.CSSProperties = {
  fontFamily: "var(--db-font-display, 'Space Grotesk', sans-serif)",
  fontSize: "clamp(1.75rem, 4vw, 2.5rem)",
  fontWeight: 600,
  margin: 0,
};

const cardStyle: React.CSSProperties = {
  background: "var(--db-surface-2, #141414)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.75rem",
  padding: "1.25rem",
};

const inputStyle: React.CSSProperties = {
  background: "var(--db-surface, #0a0a0a)",
  border: "1px solid var(--db-border, #262626)",
  borderRadius: "0.5rem",
  padding: "0.55rem 0.75rem",
  color: "var(--db-text, #f5f5f5)",
  fontFamily: "var(--db-font-body, 'Inter', system-ui, sans-serif)",
  fontSize: "0.95rem",
  outline: "none",
  width: "100%",
  boxSizing: "border-box",
};

const thStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "0.6rem 0.75rem",
  color: "var(--db-text-muted, #a3a3a3)",
  fontWeight: 500,
  fontSize: "0.78rem",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  borderBottom: "1px solid var(--db-border, #262626)",
};

const cellStyle: React.CSSProperties = {
  padding: "0.7rem 0.75rem",
  borderBottom: "1px solid var(--db-border-subtle, #1f1f1f)",
};

const emptyStyle: React.CSSProperties = {
  margin: 0,
  padding: "2rem 0",
  textAlign: "center",
  color: "var(--db-text-muted, #a3a3a3)",
};
